"""Pure, versioned breakout/retest rules. Levels never move after issuance."""

from dataclasses import asdict
from statistics import mean

from .setup_data import INTERVAL

TERMINAL = {'completed', 'invalidated', 'expired', 'ambiguous', 'unavailable', 'cancelled'}


def complete_window(rows, count, expected):
    selected = rows[-count:]
    return (len(selected) == count and selected[-1].close_at == expected
            and all(b.open_at - a.open_at == INTERVAL for a, b in zip(selected, selected[1:])))


def features(rows, config, expected):
    needed = max(20, config.setup_range_bars, config.setup_atr_bars + 1) + 1
    if not complete_window(rows, needed, expected):
        return None
    previous, current = rows[:-1], rows[-1]
    atr_rows = previous[-config.setup_atr_bars - 1:]
    atr = mean(max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close))
               for a, b in zip(atr_rows, atr_rows[1:]))
    volume = mean(row.volume_base for row in previous[-20:])
    if atr <= 0 or volume <= 0:
        return None
    bounds = previous[-config.setup_range_bars:]
    return {'atr': atr, 'volume_baseline': volume,
            'volume_ratio': current.volume_base / volume,
            'mean_close_20': mean(row.close for row in previous[-20:]),
            'range_high': max(row.high for row in bounds),
            'range_low': min(row.low for row in bounds),
            'range_start': bounds[0].open_at, 'range_end': bounds[-1].close_at}


def candidate(config, asset, rows, now):
    """An inside-range heads-up, never retroactively create an already-triggered setup."""
    if not rows:
        return None
    f = features(rows, config, rows[-1].close_at)
    if not f:
        return None
    current = rows[-1]
    width = f['range_high'] - f['range_low']
    if not 2 <= width / f['atr'] <= 6 or not f['range_low'] < current.close < f['range_high']:
        return None
    distance_up = (f['range_high'] - current.close) / width
    distance_down = (current.close - f['range_low']) / width
    if distance_up <= 0.20 and current.close > f['mean_close_20']:
        side, sign, level = 'long', 1, f['range_high']
    elif distance_down <= 0.20 and current.close < f['mean_close_20']:
        side, sign, level = 'short', -1, f['range_low']
    else:
        return None
    trigger = level + sign * 0.10 * f['atr']
    invalidation = level - sign * 0.75 * f['atr']
    risk = abs(trigger - invalidation)
    if sign * (current.close - invalidation) <= 0.10 * f['atr']:
        return None
    return {'version': config.setup_version, 'asset': asset, 'venue': 'hyperliquid',
            'instrument': asset, 'quote': 'USD', 'timeframe': '5m', 'side': side,
            'created_at': now, 'entry_expires_at': now + config.setup_expiry_minutes * 60,
            'trigger': trigger, 'invalidation': invalidation,
            'retest_low': level - 0.20 * f['atr'], 'retest_high': level + 0.20 * f['atr'],
            'entry_limit': trigger + sign * 0.60 * f['atr'],
            'target_1': trigger + sign * 1.5 * risk, 'target_2': trigger + sign * 2.5 * risk,
            'reference_risk': risk, 'level': level, **f,
            'formation_candle': current.to_dict(),
            'formation_history': [row.to_dict() for row in rows[-max(21, config.setup_range_bars + 1,
                                                                         config.setup_atr_bars + 2):]],
            'config': asdict(config)}


def book_gate(book, config, now):
    if not book or not -5 <= now - book['observed_at'] <= 60 or not -5 <= now - book['received_at'] <= 60:
        return 'book_unavailable'
    if book['spread_bps'] > config.setup_max_spread_bps:
        return 'spread_too_wide'
    if min(book['bid_depth_usd'], book['ask_depth_usd']) < config.setup_min_visible_depth_usd:
        return 'visible_depth_too_small'
    return ''


def transition(spec, track, candle, book, now):
    """Evaluate one subsequent closed bar. Trigger is a condition, not a fill."""
    stage, side = track['stage'], spec['side']
    sign = 1 if side == 'long' else -1
    low, high, close = candle.low, candle.high, candle.close
    stopped = low <= spec['invalidation'] if sign == 1 else high >= spec['invalidation']
    target_1 = high >= spec['target_1'] if sign == 1 else low <= spec['target_1']
    target_2 = high >= spec['target_2'] if sign == 1 else low <= spec['target_2']
    detail = {'candle': candle.to_dict(), 'volume_ratio': candle.volume_base / spec['volume_baseline']}
    if stage in {'triggered', 'target_1'}:
        # No favorable ordering assumed when both boundaries traded inside one bar.
        next_target = target_2 if stage == 'target_1' else target_1
        if stopped and next_target:
            return 'ambiguous', 'both_boundaries_same_bar', detail
        # The first following bar can start before this card was issued. A touch
        # anywhere in that bar cannot be timed relative to notification from OHLC.
        if candle.open_at < track['triggered_at'] and (stopped or next_target):
            return 'ambiguous', 'boundary_in_issuance_bar', detail
        if stopped:
            return 'invalidated', 'invalidation_touched', detail
        if target_2:
            return 'completed', 'second_reference_target_touched', detail
        if target_1 and stage != 'target_1':
            return 'target_1', 'first_reference_target_touched', detail
        return stage, 'structure_still_open', detail
    if now >= spec['entry_expires_at']:
        return 'expired', 'entry_window_elapsed', detail
    if stopped:
        return 'invalidated', 'setup_failed_before_trigger', detail
    if target_1:
        return 'expired', 'move_extended_before_entry', detail
    confirmed = sign * (close - spec['trigger']) >= 0
    if stage == 'forming':
        if confirmed and detail['volume_ratio'] >= spec['config']['setup_breakout_volume_ratio']:
            return 'armed', 'volume_backed_breakout', detail
        return stage, 'waiting_for_breakout', detail
    retested = low <= spec['retest_high'] and high >= spec['retest_low']
    within_entry = sign * (close - spec['entry_limit']) <= 0
    quote = book['ask'] if sign == 1 else book['bid']
    quote_ok = sign * (quote - spec['trigger']) >= 0 and sign * (quote - spec['entry_limit']) <= 0
    if confirmed and retested and within_entry and quote_ok and sign * (close - candle.open) > 0:
        detail.update(trigger_close=close, indicative_quote=quote,
                      remaining_reward_risk=abs(spec['target_2'] - quote) / abs(quote - spec['invalidation']))
        return 'triggered', 'retest_closed_and_quote_in_band', detail
    return stage, 'waiting_for_retest_without_chasing', detail
