"""Tokn setup cards: decision levels first, evidence second, no invented probabilities."""

from datetime import datetime, timezone

from .branding import TOKN_BLUE
from .presentation import card, local_stamp, money, percent, price

LABELS = {'forming': 'SETUP FORMING', 'armed': 'BREAKOUT CONFIRMED',
          'triggered': 'RETEST CONFIRMED', 'target_1': 'FIRST LEVEL REACHED',
          'completed': 'SECOND LEVEL REACHED', 'invalidated': 'THESIS INVALIDATED',
          'expired': 'WATCH ENDED', 'ambiguous': 'OUTCOME UNCLEAR',
          'unavailable': 'TRACKING INCOMPLETE', 'cancelled': 'WATCH CANCELLED',
          'paused': 'ENTRY CHECKS PAUSED', 'resumed': 'CHECKS RESTORED'}
REASONS = {
    'entry_window_elapsed': 'The untriggered setup expired. No late entry signal is issued.',
    'tracking_window_elapsed': 'The monitoring window ended. This is not an instruction to close a position.',
    'move_extended_before_entry': 'Price reached the first reference target before a valid entry condition. The move was not chased.',
    'both_boundaries_same_bar': 'The same candle crossed the invalidation and next target. Their order is unknown; no winning outcome is assigned.',
    'boundary_in_issuance_bar': 'A boundary traded in a candle that overlaps card issuance. OHLC cannot establish whether the touch happened after this notification; no favorable outcome is assigned.',
    'missed_candle': 'A monitoring gap prevents a complete account of this setup. No catch-up entry or favorable outcome is inferred.',
    'disabled': 'Setup tracking was disabled by the operator.',
    'asset_removed': 'This asset was removed from setup coverage.',
    'update_limit': 'The update limit was reached. Monitoring ended without assuming a trade exit.',
}


def setup_card(config, track, stage, detail, now):
    spec = track['spec']
    side, sign = spec['side'], 1 if spec['side'] == 'long' else -1
    direction = 'above' if sign == 1 else 'below'
    other = 'short' if sign == 1 else 'long'
    trigger, stop = price(spec['trigger']), price(spec['invalidation'])
    status = track['stage'] if stage in {'paused', 'resumed'} else stage
    read = {
        'forming': f"Watching for {side} continuation through the prior {config.setup_range_bars * 5}m range. Price must close {direction} {trigger} with volume, then retest. No entry condition yet.",
        'armed': f"The volume-backed break is confirmed. The next test is whether the old range boundary holds on a later candle. Wait for the retest; the breakout alone is not an entry.",
        'triggered': f"A later five-minute candle retested the boundary and closed {direction} {trigger}. The indicative quote was inside the entry band at this check. The continuation scenario is active.",
        'target_1': 'Price touched the first reference target after the trigger. Review partial-profit or protection rules; the second level remains a reference, not a promised move.',
        'completed': 'Price touched the second reference target after the trigger. This setup is now closed in the tracker.',
        'invalidated': f'Price traded through {stop}. The original continuation thesis no longer qualifies; further adds based on it have lost their basis.',
    }.get(status, REASONS.get(detail.get('reason'), 'The setup is closed. No fresh entry condition is active.'))
    if stage == 'paused':
        read = 'Entry checks are paused because required data or liquidity checks are incomplete. Existing levels are historical references; no fresh entry is confirmed.'
    elif stage == 'resumed':
        read = 'Fresh checks are available again. ' + read
    if stage == 'paused' or status in {'unavailable', 'ambiguous'}:
        action = 'Waiting: stand aside until a new valid setup.\nPosition open: check the venue and your own protective orders; this feed cannot confirm the missing path.'
    elif status in {'forming', 'armed'}:
        action = (f'Waiting: prepare the {side} scenario; require the full break/retest sequence.\n'
                  f'Already {side}: use {stop} as this thesis\'s invalidation reference.\n'
                  f'Already {other}: a confirmed retest would challenge the position; reassess exposure then.')
    elif status == 'triggered':
        action = (f'Waiting: consider the {side} scenario only inside the entry band; skip if price has moved beyond it.\n'
                  f'Already {side}: continuation conditions passed; keep invalidation explicit.\n'
                  f'Already {other}: the break held on retest; review reducing opposing exposure.')
    elif status == 'invalidated':
        action = (f'Already {side}: reassess remaining exposure against your exit plan.\n'
                  'Waiting: cancel this entry idea. A failed setup does not automatically authorize the opposite trade.')
    elif status in {'target_1', 'completed'}:
        action = 'Position open: review your pre-planned profit protection.\nWaiting: this is an outcome update, not a new entry invitation.'
    else:
        action = 'Waiting: retire this setup and wait for a fresh one.\nPosition open: follow your position plan; a monitoring deadline is not a forced exit.'
    lower, upper = sorted((spec['trigger'], spec['entry_limit']))
    levels = (f"Entry band · {price(lower)}–{price(upper)} USD\n"
              f"Retest zone · {price(spec['retest_low'])}–{price(spec['retest_high'])}\n"
              f"Invalidation · {stop} (price touch)\n"
              f"Targets · {price(spec['target_1'])} / {price(spec['target_2'])}\n"
              'Gross targets: 1.5R / 2.5R from the trigger; entry and costs change reward/risk.')
    confirmation = (f"5m close {direction} {trigger}; breakout volume ≥ {config.setup_breakout_volume_ratio:.2f}× "
                    'the frozen 20-bar average. A later candle must touch the retest zone and close back through the trigger. '
                    'Current spread, visible depth and entry-band checks must pass.')
    context = detail.get('context') or {}
    evidence = []
    candle = detail.get('candle')
    if candle:
        when = datetime.fromtimestamp(candle['open_at'] + 300, timezone.utc).strftime('%H:%M UTC')
        evidence.append(f"Closed candle · {price(candle['close'])} USD at {when}")
    if detail.get('volume_ratio') is not None:
        evidence.append(f"Volume · {detail['volume_ratio']:.2f}× frozen baseline")
    for venue, quote in [('hyperliquid', 'USD'), ('okx', 'USDT')]:
        row = context.get(venue) or {}
        label = 'Hyperliquid' if venue == 'hyperliquid' else 'OKX'
        if row.get('change_15m_pct') is not None:
            evidence.append(f"{label} · 15m {percent(row['change_15m_pct'])} ({quote})")
        if row.get('oi_change_pct') is not None:
            evidence.append(f"{label} · OI {percent(row['oi_change_pct'])} / ~{config.lookback_minutes}m")
        if row.get('funding_bps_8h') is not None:
            evidence.append(f"{label} · funding {row['funding_bps_8h']:+.2f} bps / 8h eq.")
    book = context.get('book')
    if book:
        evidence.append(f"Book · {book['spread_bps']:.2f} bps spread; visible bid/ask depth "
                        f"{money(book['bid_depth_usd'])}/{money(book['ask_depth_usd'])} within 10 bps")
    spot = context.get('spot')
    if spot:
        evidence.append(f"Coinbase spot · {price(spot['last'])} USD (separate market)")
    missing = context.get('missing', [])
    if missing:
        evidence.append('Unavailable context · ' + ', '.join(missing))
    fields = [('The setup', read), ('Decision levels · Hyperliquid', levels),
              ('Position playbook', action)]
    cost_screen = spec.get('cost_screen')
    if cost_screen:
        policy = cost_screen['policy']
        estimates = detail.get('execution_costs') or cost_screen['at_trigger']
        reference = 'At indicative quote' if detail.get('execution_costs') else 'At planned trigger'
        fields.insert(2, ('Room after costs',
            f"{reference} · T1 {estimates['target_1']['net_rr']:.2f}:1 / T2 {estimates['target_2']['net_rr']:.2f}:1 reward/risk\n"
            f"Entry band capped to retain ≥{policy['min_target_2_net_rr']:.2f}:1 to T2.\n"
            f"Assumed each side · {policy['fee_bps_per_side']:g} bps fee + {policy['slippage_bps_per_side']:g} bps execution allowance.\n"
            'Estimated costs reduce reward and increase stop risk. Funding excluded.'))
    else:
        fields.insert(2, ('Cost coverage', 'Legacy setup · issued before cost screening. Reward/risk is before costs.'))
    if status in {'forming', 'armed'} and stage != 'paused':
        fields.append(('What confirms it', confirmation))
    fields.append(('Evidence at this check', '\n'.join(evidence) or 'No fresh market evidence is available.'))
    if detail.get('reason') in REASONS:
        fields.append(('Why this update', REASONS[detail['reason']]))
    if detail.get('indicative_quote') is not None:
        value = f"Indicative quote {price(detail['indicative_quote'])} USD · not a fill."
        if not cost_screen:
            value += f" Target-2 reward/risk {detail['remaining_reward_risk']:.2f}R before costs."
        fields.append(('At confirmation', value))
    color = (0xFBBF24 if stage in {'paused', 'ambiguous', 'unavailable'} else
             0x94A3B8 if status in {'expired', 'cancelled', 'invalidated'} else TOKN_BLUE)
    expiry = datetime.fromtimestamp(spec['entry_expires_at'], timezone.utc).strftime('%H:%M UTC')
    description = (f"{side.upper()} SCENARIO · 5m break / retest · Hyperliquid\n"
                   + local_stamp(now, config.timezone) + f"\nSetup ref · {track['id']} · Entry window ends {expiry}")
    footer = ('Rule-based research; edge untested. No orders or fills. Levels fixed at issuance. '
              'Targets before costs. Cost estimates are allowances, not guaranteed fills. '
              'Funding excluded from reward/risk. Book depth is partial.')
    return card(spec['asset'] + ' · ' + LABELS[stage], description, fields, color, now, footer)
