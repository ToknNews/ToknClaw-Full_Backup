"""Reproducible observations and explanations; no predictions of profit."""

from dataclasses import asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .models import Event


def stamp(now):
    return datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def deadline(config, observations, now):
    limits = [now + config.delivery_ttl_seconds]
    limits.extend(min(o.observed_at, o.fetched_at) + config.max_age_seconds for o in observations)
    return min(limits)


def change(current, previous):
    return (current / previous - 1) * 100


def assess(config, observations, errors, now):
    accepted, issues = [], dict(errors)
    expected = {(v, a) for v in config.venues for a in config.assets}
    seen = set()
    for obs in observations:
        key = (obs.venue, obs.asset)
        scope = ':'.join(key)
        if key not in expected:
            continue
        if key in seen:
            issues[scope] = 'duplicate_source_measurement'
            continue
        seen.add(key)
        if not obs.fresh(now, config.max_age_seconds):
            issues[scope] = 'stale_or_future_measurement'
        elif scope not in issues:
            accepted.append(obs)
    for venue, asset in expected - seen:
        issues.setdefault(venue + ':' + asset, 'missing_measurement')
    accepted = [o for o in accepted if o.venue + ':' + o.asset not in issues]
    for asset in config.assets:
        group = [o for o in accepted if o.asset == asset]
        if len(group) >= 2 and change(max(o.mark_price for o in group), min(o.mark_price for o in group)) > config.max_price_disagreement_pct:
            issues['cross_venue:' + asset] = 'price_disagreement'
            accepted = [o for o in accepted if o.asset != asset]
    return accepted, issues


def market_alerts(config, store, observations, now):
    events = []
    for asset in config.assets:
        group = sorted((o for o in observations if o.asset == asset), key=lambda o: o.venue)
        if len(group) < config.minimum_venues:
            continue
        funding = [o.funding_bps_8h for o in group]
        candidates = []
        comparisons = []
        for obs in group:
            base = store.baseline(obs, config.lookback_minutes * 60, config.baseline_tolerance_seconds)
            if base:
                comparisons.append({
                    'venue': obs.venue, 'baseline': base.to_dict(),
                    'price_pct': change(obs.mark_price, base.mark_price),
                    'oi_base_pct': change(obs.oi_base, base.oi_base),
                })
        if len(comparisons) >= config.minimum_venues:
            prices = [r['price_pct'] for r in comparisons]
            oi = [r['oi_base_pct'] for r in comparisons]
            if all(x >= config.oi_change_pct for x in oi):
                if all(x >= config.price_change_pct for x in prices):
                    candidates.append(('price_oi_up', 'Price and open interest rising',
                        'Rising positioning accompanies the price move. This does not identify whether new positions are longs or shorts.'))
                elif all(x <= -config.price_change_pct for x in prices):
                    candidates.append(('price_oi_down', 'Price falling; open interest rising',
                        'Positioning expanded during a price decline. This does not establish that the decline will continue.'))
        if all(x >= config.funding_extreme_bps_8h for x in funding):
            candidates.append(('positive_funding', 'Elevated positive funding',
                'Longs currently pay shorts on these venues. Positive funding alone does not establish a reversal.'))
        elif all(x <= -config.funding_extreme_bps_8h for x in funding):
            candidates.append(('negative_funding', 'Elevated negative funding',
                'Shorts currently pay longs on these venues. Negative funding alone does not establish a rebound.'))
        if len(group) >= 2 and max(funding) - min(funding) >= config.funding_spread_bps_8h:
            candidates.append(('funding_divergence', 'Funding differs across venues',
                'Rates differ on a common time basis. Fees, basis risk and changing rates may outweigh this difference.'))
        for rule, title, interpretation in candidates:
            key = config.rule_version + ':' + asset + ':' + rule
            last = store.last_event(key)
            if last is not None and now - last < config.cooldown_minutes * 60:
                continue
            if store.alert_count(now - 3600) + len(events) >= config.max_alerts_per_hour:
                return events
            lines = ['TOKN MARKET WATCH | ' + asset, title, stamp(now)]
            for obs in group:
                lines.append(f'{obs.venue}: mark {obs.mark_price:,.2f} {obs.quote_currency}; OI ${obs.oi_usd / 1e6:,.1f}m; funding {obs.funding_bps_8h:+.2f} bps/8h equiv. As of {stamp(obs.observed_at)}.')
            if comparisons:
                for row in comparisons:
                    lines.append(f"{row['venue']} ~{config.lookback_minutes}m: price {row['price_pct']:+.2f}%; OI in coin units {row['oi_base_pct']:+.2f}%.")
            lines += [interpretation, 'Source: current public venue estimates; funding can change.',
                      'Monitoring only. No entry, leverage or return recommendation.']
            evidence = {'rule': rule, 'config': asdict(config), 'observations': [o.to_dict() for o in group], 'comparisons': comparisons}
            events.append(Event(key, 'alert', 'paid', now, deadline(config, group, now),
                                '\n'.join(lines), evidence))
    return events


def summaries(config, store, observations, issues, now):
    local = datetime.fromtimestamp(now, ZoneInfo(config.timezone))
    if local.minute >= config.summary_grace_minutes:
        return []
    events = []
    for audience, due in [('paid', local.hour in config.summary_hours), ('free', local.hour == config.free_summary_hour)]:
        if not due:
            continue
        # Local date/hour prevents duplicate sends across the DST fall-back hour.
        key = f'summary:{audience}:{local.date()}:{local.hour}'
        if store.last_event(key) is not None:
            continue
        covered = config.assets if audience == 'paid' else config.assets[:1]
        lines = ['TOKN MARKET WATCH | ' + ('Market brief' if audience == 'paid' else 'Free market sample'), stamp(now)]
        for asset in covered:
            group = [o for o in observations if o.asset == asset]
            if len(group) < config.minimum_venues:
                lines.append(asset + ': insufficient fresh venue coverage; analysis paused.')
                continue
            lines.append(asset + ':')
            for obs in sorted(group, key=lambda o: o.venue):
                lines.append(f'  {obs.venue}: {obs.mark_price:,.2f} {obs.quote_currency}; OI ${obs.oi_usd / 1e6:,.1f}m; funding {obs.funding_bps_8h:+.2f} bps/8h equiv. As of {stamp(obs.observed_at)}.')
        if issues:
            lines.append('Coverage degraded: some measurements are unavailable or inconsistent.')
        lines += ['Funding shown on a common 8h basis; estimates can change.',
                  'Monitoring only. No trade or return recommendation.']
        if audience == 'free':
            lines.append('Sample coverage: ' + ', '.join(covered) + '. Full feed covers BTC, ETH and SOL.')
        evidence = {'observations': [o.to_dict() for o in observations if o.asset in covered], 'issues': issues, 'timezone': config.timezone}
        visible = [o for o in observations if o.asset in covered]
        events.append(Event(key, 'summary', audience, now, deadline(config, visible, now), '\n'.join(lines), evidence))
    return events


def health_event(config, store, issues, now):
    previous = store.get_meta('source_health')
    current = dict(sorted(issues.items()))
    store.set_meta('source_health', current)
    if current == previous or (previous is None and not current):
        return []
    key = 'health:' + ('degraded' if current else 'recovered')
    last = store.last_event(key)
    if last is not None and now - last < 900:
        return []
    text = 'TOKN MARKET WATCH | Data health\n' + stamp(now) + '\n'
    if current:
        text += 'Coverage degraded. Affected comparisons are paused.\n' + '\n'.join(f'{k}: {v}' for k, v in current.items())
    else:
        text += 'Configured venue coverage has recovered. Fresh measurements are available.'
    return [Event(key, 'health', 'paid', now, now + config.delivery_ttl_seconds, text, {'issues': current})]
