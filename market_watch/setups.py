"""Transactional prospective setup tracking; never replay a missed entry into the feed."""

from .config import Config
from .engine import comparisons_for
from .models import Event, event_id
from .setup_cards import setup_card
from .setup_data import INTERVAL
from .setup_rules import TERMINAL, book_gate, candidate, complete_window, transition


def context_for(config, store, asset, batch, observations, now):
    result = {'missing': []}
    for venue in config.venues:
        rows = [row for row in store.setup_candles(venue, asset, now)
                if row.close_at <= batch.requested_close]
        source = 'hl_candles' if venue == 'hyperliquid' else 'okx_candles'
        value = {}
        if (source + ':' + asset not in batch.errors
                and complete_window(rows, 4, batch.requested_close)):
            value['change_15m_pct'] = (rows[-1].close / rows[-4].close - 1) * 100
            value['candle_close_at'] = rows[-1].close_at
        else:
            result['missing'].append(venue + ' 15m')
        group = [o for o in observations if o.asset == asset and o.venue == venue and o.fresh(now, config.max_age_seconds)]
        if group:
            value['funding_bps_8h'] = group[0].funding_bps_8h
            value['funding_interval_hours'] = group[0].funding_interval_hours
            value['observation'] = group[0].to_dict()
            comparisons = comparisons_for(config, store, group)
            if comparisons:
                value['oi_change_pct'] = comparisons[0]['oi_base_pct']
                value['comparison'] = comparisons[0]
            else:
                result['missing'].append(venue + ' OI baseline')
        else:
            result['missing'].append(venue + ' OI/funding')
        result[venue] = value
    book = batch.books.get(asset)
    if book and -5 <= now - book['observed_at'] <= 60 and -5 <= now - book['received_at'] <= 60:
        result['book'] = book
    else:
        result['missing'].append('Hyperliquid book')
    spot = batch.spots.get(asset)
    if spot and -5 <= now - spot['trade_at'] <= 120 and -5 <= now - spot['received_at'] <= 120:
        result['spot'] = spot
    elif config.setup_coinbase_enabled:
        result['missing'].append('Coinbase spot')
    return result


def _emit(store, track, stage, detail, now, routes, initial=False, publish=True):
    frozen = Config(**track['spec']['config'])
    sequence = track['sequence']
    detail = {**detail, 'setup_id': track['id'], 'stage': stage, 'sequence': sequence,
              'checked_at': now, 'spec': track['spec']}
    text, presentation = setup_card(frozen, track, stage, detail, now)
    detail['presentation'] = presentation
    key = track['event_key'] if initial else 'setup:' + track['id'] + ':' + str(sequence)
    targets = [r for r in routes if r.audience == 'paid'] if initial else store.setup_receipt_routes(track['id'], routes)
    if not publish or not frozen.setup_publish:
        targets = []
    expires = now + 120
    if stage in {'forming', 'armed', 'triggered'}:
        book = (detail.get('context') or {}).get('book')
        if book:
            expires = min(expires, book['observed_at'] + 60, book['received_at'] + 60)
    if not initial:
        store.supersede_setup(track['id'], now)
    event = Event(key, 'setup' if initial else 'setup_update', 'paid', now, expires, text, detail)
    child = store.add_event(event, targets)
    store.save_setup(track)
    store.link_setup_event(child, track['id'], sequence)
    return {'id': child, 'kind': event.kind, 'audience': 'paid', 'text': text}


def _update(store, track, stage, reason, now, routes, detail=None, publish=True):
    track['stage'] = stage
    track['sequence'] += 1
    track['updated_at'] = now
    if stage in TERMINAL:
        track['closed_at'] = now
    detail = {**(detail or {}), 'reason': reason}
    track['last_check'] = detail
    return _emit(store, track, stage, detail, now, routes, publish=publish)


def advance_setups(config, store, batch, observations, routes, now):
    """Run inside run_cycle's archive transaction. Optional context never becomes price evidence."""
    events, active = [], store.active_setups()
    # Disabling publishing also withdraws queued setup cards, without changing old receipts.
    if not config.setup_publish or not config.setup_enabled:
        store.withdraw_setup_deliveries(now)
    for track in list(active):
        spec = track['spec']
        frozen = Config(**spec['config'])
        reason = ''
        if not config.setup_enabled:
            reason = 'disabled'
        elif spec['asset'] not in config.assets:
            reason = 'asset_removed'
        elif track['stage'] in {'forming', 'armed'} and now >= spec['entry_expires_at']:
            reason = 'entry_window_elapsed'
        elif track.get('triggered_at') and now >= track['triggered_at'] + frozen.setup_tracking_hours * 3600:
            reason = 'tracking_window_elapsed'
        if reason:
            stage = 'cancelled' if reason in {'disabled', 'asset_removed'} else 'expired'
            events.append(_update(store, track, stage, reason, now, routes,
                                  publish=config.setup_enabled and config.setup_publish))
            active.remove(track)
    if not config.setup_enabled:
        store.set_meta('setup_health', {'status': 'disabled', 'primary_issues': {}, 'checked_at': now})
        return events
    if batch is None:
        return events
    revisions = store.add_setup_candles(batch.candles)
    for scope in revisions:
        venue, asset = scope.split(':')
        batch.errors[('hl_candles' if venue == 'hyperliquid' else 'okx_candles') + ':' + asset] = 'closed_candle_revised'
    health = {'status': 'ready', 'checked_at': now, 'candle_close_at': batch.requested_close,
              'primary_issues': {}, 'optional_issues': {}, 'screen': {},
              'publishing': config.setup_publish}
    active_by_asset = {t['spec']['asset']: t for t in active}
    for asset in config.assets:
        track = active_by_asset.get(asset)
        frozen = Config(**track['spec']['config']) if track else config
        rows = store.setup_candles('hyperliquid', asset, now, frozen.setup_history_bars)
        source_error = batch.errors.get('hl_candles:' + asset)
        if not source_error and (not rows or rows[-1].close_at != batch.requested_close
                                 or not 0 <= now - rows[-1].close_at <= frozen.setup_max_delay_seconds):
            source_error = 'closed_candle_missing_or_late'
        context = context_for(frozen, store, asset, batch, observations, now)
        book = context.get('book')
        liquidity = book_gate(book, frozen, now)
        if source_error:
            health['primary_issues'][asset] = source_error
        elif liquidity == 'book_unavailable':
            health['primary_issues'][asset] = batch.errors.get('hl_book:' + asset, liquidity)
        optional = {k: v for k, v in batch.errors.items() if k.endswith(':' + asset)
                    and k.startswith(('okx_', 'coinbase_'))}
        if 'okx' in frozen.venues and 'change_15m_pct' not in context.get('okx', {}):
            optional.setdefault('okx_candles:' + asset, 'incomplete_context_window')
        if frozen.setup_coinbase_enabled and 'spot' not in context:
            optional.setdefault('coinbase_spot:' + asset, 'spot_reference_unavailable')
        health['optional_issues'].update(optional)
        if track:
            if source_error:
                if not track.get('paused'):
                    track['paused'] = True
                    track['sequence'] += 1
                    events.append(_emit(store, track, 'paused', {'reason': source_error, 'context': context},
                                        now, routes, publish=config.setup_publish))
                continue
            latest = rows[-1]
            if latest.close_at <= track['last_candle_close']:
                continue
            if latest.close_at - track['last_candle_close'] != INTERVAL:
                events.append(_update(store, track, 'unavailable', 'missed_candle', now, routes,
                                      {'context': context}, publish=config.setup_publish))
                continue
            stage, reason, detail = transition(track['spec'], track, latest,
                                               book or {'bid': -1, 'ask': -1}, now)
            detail['context'] = context
            track['last_candle_close'] = latest.close_at
            track['last_check'] = {**detail, 'reason': reason}
            track['updated_at'] = now
            entry_blocked = bool(liquidity) and track['stage'] in {'forming', 'armed'} and stage not in TERMINAL
            if entry_blocked:
                health['screen'][asset] = liquidity
                track['last_check'] = {**detail, 'reason': liquidity}
                if not track.get('paused'):
                    track['paused'] = True
                    track['sequence'] += 1
                    events.append(_emit(store, track, 'paused', track['last_check'], now, routes,
                                        publish=config.setup_publish))
            else:
                recovered = track.get('paused', False)
                track['paused'] = False
                if stage != track['stage']:
                    if stage == 'triggered':
                        track['triggered_at'] = now
                    events.append(_update(store, track, stage, reason, now, routes, detail,
                                          publish=config.setup_publish))
                elif recovered:
                    track['sequence'] += 1
                    events.append(_emit(store, track, 'resumed', detail, now, routes, publish=config.setup_publish))
            if track['sequence'] >= 12 and track['stage'] not in TERMINAL:
                events.append(_update(store, track, 'expired', 'update_limit', now, routes,
                                      publish=config.setup_publish))
            store.save_setup(track)
            continue
        if source_error or liquidity:
            health['screen'][asset] = source_error or liquidity
            continue
        last_closed = store.setup_last_closed(asset)
        if last_closed is not None and now - last_closed < config.setup_cooldown_minutes * 60:
            health['screen'][asset] = 'cooldown'
            continue
        if store.setup_created_count(now - 3600) >= config.setup_max_new_per_hour:
            health['screen'][asset] = 'hourly_setup_limit'
            continue
        spec = candidate(config, asset, rows, now)
        if not spec:
            health['screen'][asset] = 'no_qualifying_range'
            continue
        sign = 1 if spec['side'] == 'long' else -1
        live_near_edge = abs(book['mid'] - spec['level']) <= 0.25 * (spec['range_high'] - spec['range_low'])
        if (not spec['range_low'] < book['mid'] < spec['range_high'] or not live_near_edge
                or sign * (book['mid'] - spec['invalidation']) <= 0):
            health['screen'][asset] = 'live_price_left_range'
            continue
        key = 'setup:' + config.setup_version + ':' + asset + ':' + str(int(rows[-1].close_at))
        if store.last_event(key) is not None:
            continue
        root = event_id(key, now)
        track = {'id': root, 'event_key': key, 'spec': spec, 'stage': 'forming', 'sequence': 0,
                 'last_candle_close': rows[-1].close_at, 'updated_at': now, 'paused': False}
        detail = {'context': context, 'candle': rows[-1].to_dict(),
                  'volume_ratio': spec['volume_ratio'], 'reason': 'range_edge_approach'}
        track['last_check'] = detail
        events.append(_emit(store, track, 'forming', detail, now, routes, initial=True,
                            publish=config.setup_publish))
        health['screen'][asset] = 'forming'
    if health['primary_issues']:
        health['status'] = 'degraded'
    store.setup_sample(now, {'requested_close': batch.requested_close, 'books': batch.books,
                             'spots': batch.spots, 'errors': batch.errors, 'health': health})
    store.set_meta('setup_health', health)
    prior_poll = store.get_meta('setup_poll') or {}
    store.set_meta('setup_poll', {'close': batch.requested_close, 'at': prior_poll.get('at', now),
                                 'complete': not health['primary_issues'] or now - batch.requested_close > config.setup_max_delay_seconds})
    return events
