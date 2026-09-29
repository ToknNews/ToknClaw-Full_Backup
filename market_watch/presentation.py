"""Deterministic Tokn cards and matching plain text; no generated market claims."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .rules import matching_rules


BRAND = 'TOKN / MARKET WATCH'
COLORS = {'up': 0x38BDF8, 'down': 0xFB7185, 'funding': 0xFBBF24,
          'spread': 0xA78BFA, 'brief': 0x38BDF8, 'sample': 0x94A3B8,
          'degraded': 0xFBBF24, 'recovered': 0x34D399}
VENUES = {'hyperliquid': 'Hyperliquid', 'okx': 'OKX'}
FOOTER = 'Snapshot criteria, not entry/exit levels. OI: coin units. Funding: 8h equivalent estimates.'
ALERT_COPY = {
    'price_oi_up': ('PRICE ↑ / OI ↑', 'up',
        'Price is climbing. Open interest is building with it.',
        'There are more open contracts during the rally. This adds positioning context, '
        'but does not identify whether buyers or sellers initiated them.',
        'For a continuation thesis, look for the same pattern in a fresh reading. '
        'A price retrace with OI still elevated is a reason to reassess.'),
    'price_oi_down': ('PRICE ↓ / OI ↑', 'down',
        'The selloff is adding open contracts.',
        'Price is falling while open interest expands. New short pressure is one possible '
        'explanation; these inputs cannot establish it.',
        'For downside continuation, check whether price keeps falling while OI expands. '
        'A price rebound with OI still elevated changes that read.'),
    'positive_funding': ('LONGS PAYING UP', 'funding',
        'Longs face elevated estimated funding costs.',
        'Longs would pay shorts at the displayed estimates. That affects carry cost; '
        'it does not time a reversal.',
        'Before holding through settlement, check the venue’s actual funding interval and '
        'current rate. Reassess the carry cost if rates cool.'),
    'negative_funding': ('SHORTS PAYING UP', 'funding',
        'Shorts face elevated estimated funding costs.',
        'Shorts would pay longs at the displayed estimates. That affects carry cost; '
        'it does not time a rebound.',
        'Before holding through settlement, check the venue’s actual funding interval and '
        'current rate. Reassess the carry cost if rates move toward zero.'),
    'funding_divergence': ('FUNDING SPLIT', 'spread',
        'Same asset. Different estimated funding costs.',
        'Venue choice changes the estimated carry cost. The displayed gap is a comparison, '
        'not locked-in arbitrage.',
        'Compare actual settlement intervals, fees and basis before using the gap. '
        'Recheck both rates together; either can change before settlement.'),
}


def local_stamp(now, zone):
    return datetime.fromtimestamp(now, ZoneInfo(zone)).strftime('%b %d, %Y · %I:%M %p %Z')


def price(value):
    return f'{value:.4e}' if value >= 1e9 else f'{value:,.2f}' if value >= 1 else f'{value:,.6f}'


def money(value):
    if value >= 1e15:
        return f'${value:.2e}'
    for divisor, suffix in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if value >= divisor:
            return f'${value / divisor:,.2f}{suffix}'
    return f'${value:,.2f}'


def percent(value, digits=2):
    return f'{value:+.2e}%' if abs(value) >= 1e6 else f'{value:+.{digits}f}%'


def venue_lines(obs, comparison=None, window=15):
    rows = [f'Mark {price(obs.mark_price)} {obs.quote_currency}']
    if comparison is not None:
        rows.append(f'~{window}m · Price {percent(comparison["price_pct"])} · OI {percent(comparison["oi_base_pct"])}')
    rows.append(f'OI notional {money(obs.oi_usd)} · Funding {percent(obs.funding_bps_8h / 100, 4)} / 8h eq.')
    basis = 'Received' if obs.timestamp_basis == 'receipt' else 'As of'
    rows.append(basis + ' ' + datetime.fromtimestamp(obs.observed_at, timezone.utc).strftime('%m-%d %H:%M:%S UTC'))
    return '\n'.join(rows)


def _units(value):
    return len(value.encode('utf-16-le')) // 2


def validate_presentation(presentation):
    """Validate the restricted, link-free embed schema before external delivery."""
    if not isinstance(presentation, dict) or set(presentation) != {'format', 'discord'}:
        raise ValueError('invalid presentation')
    if presentation['format'] != 'tokn-card-v1' or not isinstance(presentation['discord'], dict):
        raise ValueError('invalid presentation')
    embed = presentation['discord']
    if set(embed) != {'author', 'title', 'description', 'fields', 'footer', 'timestamp', 'color'}:
        raise ValueError('invalid presentation')
    if (not isinstance(embed['author'], dict) or set(embed['author']) != {'name'}
            or not isinstance(embed['footer'], dict) or set(embed['footer']) != {'text'}
            or not isinstance(embed['fields'], list) or len(embed['fields']) > 25
            or type(embed['color']) is not int or not 0 <= embed['color'] <= 0xFFFFFF):
        raise ValueError('invalid presentation')
    parts = [(embed['title'], 256), (embed['description'], 4096),
             (embed['author']['name'], 256), (embed['footer']['text'], 2048)]
    for field in embed['fields']:
        if (not isinstance(field, dict) or set(field) != {'name', 'value', 'inline'}
                or type(field['inline']) is not bool):
            raise ValueError('invalid presentation')
        parts.extend([(field['name'], 256), (field['value'], 1024)])
    if any(not isinstance(text, str) or not text or _units(text) > limit for text, limit in parts):
        raise ValueError('invalid presentation size')
    if sum(_units(text) for text, _ in parts) > 6000:
        raise ValueError('invalid presentation size')
    if not isinstance(embed['timestamp'], str):
        raise ValueError('invalid presentation timestamp')
    parsed = datetime.fromisoformat(embed['timestamp'].replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('invalid presentation timestamp')
    return embed


def card(title, description, fields, color, now, footer=FOOTER):
    embed = {
        'author': {'name': BRAND}, 'title': title, 'description': description,
        'color': color, 'timestamp': datetime.fromtimestamp(now, timezone.utc).isoformat(),
        'fields': [{'name': name, 'value': value, 'inline': False} for name, value in fields],
        'footer': {'text': footer},
    }
    presentation = {'format': 'tokn-card-v1', 'discord': embed}
    validate_presentation(presentation)
    text = BRAND + '\n' + title + '\n' + description
    for name, value in fields:
        text += '\n\n' + name + '\n' + value
    text += '\n\n' + footer
    return text, presentation


def recheck_rule(config, rule):
    """Describe the existing rule, without inventing entries or future outcomes."""
    minimum = config.minimum_venues
    if rule in {'price_oi_up', 'price_oi_down'}:
        direction = f'≥ {config.price_change_pct:+}%' if rule == 'price_oi_up' else f'≤ {-config.price_change_pct:+}%'
        return (f'Price {direction} and OI ≥ {config.oi_change_pct:+}% on every compared venue '
                f'(~{config.lookback_minutes}m; at least {minimum} valid baselines). '
                'A fresh comparison outside either threshold breaks this pattern. '
                'Missing coverage leaves it unconfirmed.')
    if rule in {'positive_funding', 'negative_funding'}:
        threshold = config.funding_extreme_bps_8h / 100
        condition = f'≥ {threshold:+}%' if rule == 'positive_funding' else f'≤ {-threshold:+}%'
        return (f'Funding {condition} / 8h eq. on every covered venue '
                f'(at least {minimum} fresh venues). A fresh rate outside that threshold '
                'ends the shared funding condition. Missing coverage leaves it unconfirmed.')
    if rule == 'funding_divergence':
        return (f'Highest minus lowest funding ≥ {config.funding_spread_bps_8h} bps / 8h eq. '
                f'(at least {max(2, minimum)} fresh venues). A smaller gap no longer qualifies. '
                'Missing coverage leaves it unconfirmed.')
    raise ValueError('unsupported alert rule')


def alert_card(config, rule, asset, observations, comparisons, now, reference=None):
    headline, accent, hook, interpretation, watch = ALERT_COPY[rule]
    changes = {row['venue']: row for row in comparisons}
    coverage = f'{len(observations)}/{len(config.venues)} fresh venues'
    context = (f'~{config.lookback_minutes}m window · {len(changes)} valid baselines'
               if rule.startswith('price_oi') else 'Current funding estimates')
    fields = [('The read', interpretation), ('Your next check', watch),
              ('Recheck rule', recheck_rule(config, rule))]
    fields += [(VENUES[obs.venue], venue_lines(obs, changes.get(obs.venue), config.lookback_minutes))
               for obs in sorted(observations, key=lambda row: row.venue)]
    if rule == 'funding_divergence':
        gap = max(o.funding_bps_8h for o in observations) - min(o.funding_bps_8h for o in observations)
        fields.append(('Funding gap · 8h equivalent', f'{gap:.2f} bps · 1 bp = 0.01 percentage points'))
    description = hook + '\n' + context + ' · ' + coverage + '\n' + local_stamp(now, config.timezone)
    if reference:
        description += '\nWatch ref · ' + reference
    return card(asset + ' · ' + headline, description, fields, COLORS[accent], now)


def brief_read(config, group, comparisons):
    """Current rule context only: no ranking, forecast or cross-asset evidence."""
    if len(group) < config.minimum_venues:
        return 'Coverage incomplete. Analysis paused.'
    venues = {o.venue for o in group}
    changes = [r for r in comparisons if r['venue'] in venues]
    rules = matching_rules(config, group, changes)
    if len(changes) < config.minimum_venues:
        parts = ['Price/OI read needs a valid baseline.']
    elif 'price_oi_up' in rules:
        parts = ['Rally + rising OI. Watch for persistence.']
    elif 'price_oi_down' in rules:
        parts = ['Selloff + rising OI. Watch for persistence.']
    else:
        parts = ['No shared price/OI trigger at the configured thresholds.']
    if 'positive_funding' in rules:
        parts.append('Longs face elevated funding costs.')
    elif 'negative_funding' in rules:
        parts.append('Shorts face elevated funding costs.')
    if 'funding_divergence' in rules:
        parts.append('Funding differs across venues.')
    return ' '.join(parts)


def brief_card(config, audience, covered, observations, comparisons, issues, now):
    fields, reads, available = [], [], 0
    for asset in covered:
        group = sorted((o for o in observations if o.asset == asset), key=lambda row: row.venue)
        reads.append(asset + ' · ' + brief_read(config, group, comparisons.get(asset, [])))
        if len(group) < config.minimum_venues:
            fields.append((asset, f'{len(group)}/{len(config.venues)} fresh venues · analysis paused.'))
            continue
        available += 1
        changes = {r['venue']: r for r in comparisons.get(asset, [])}
        blocks = [VENUES[o.venue] + '\n' + venue_lines(o, changes.get(o.venue), config.lookback_minutes) for o in group]
        if len(changes) < len(group):
            blocks.append(f'~{config.lookback_minutes}m changes appear when a valid baseline is available.')
        fields.append((asset, '\n\n'.join(blocks)))
    fields.insert(0, ('At a glance', '\n'.join(reads)))
    local = datetime.fromtimestamp(now, ZoneInfo(config.timezone))
    title = ('AM BRIEF' if local.hour < 12 else 'PM BRIEF') if audience == 'paid' else 'FREE LOOK · ' + ' / '.join(covered)
    description = ('Start with what changed. Then check the evidence.\n' + local_stamp(now, config.timezone)
                   + f'\nCoverage · {available}/{len(covered)} assets ready')
    if issues:
        description += '\nSome source measurements are unavailable; affected data is withheld.'
    if audience == 'free':
        fields.append(('Inside the full feed', 'BTC, ETH and SOL · live condition alerts · what to check next · morning and evening briefs.'))
    return card(title, description, fields, COLORS['brief' if audience == 'paid' else 'sample'], now)


def health_card(config, issues, now):
    if issues:
        rows = []
        for scope in sorted(issues):
            venue, _, asset = scope.partition(':')
            label = (asset + ' · ' if asset else '') + VENUES.get(venue, 'Cross-venue checks' if venue == 'cross_venue' else 'Source checks')
            reason = issues[scope]
            detail = ('stale or future reading' if reason == 'stale_or_future_measurement'
                      else 'venue prices disagree' if reason == 'price_disagreement'
                      else 'current data unavailable or invalid')
            rows.append(label + ' — ' + detail)
        fields = [('Affected coverage', '\n'.join(rows)),
                  ('What changes', 'Affected readings are withheld. Assets with sufficient fresh coverage continue.')]
        return card('DATA CHECK · COVERAGE LIMITED', local_stamp(now, config.timezone), fields,
                    COLORS['degraded'], now, 'Data-status update · No market signal')
    return card('DATA CHECK · COVERAGE RESTORED', local_stamp(now, config.timezone),
                [('Status', 'Configured source coverage has recovered. Fresh measurements are available.')],
                COLORS['recovered'], now, 'Data-status update · No market signal')


def followup_card(config, detail, observations):
    condition, reason = detail['condition'], detail['closed_reason']
    if reason and reason != 'condition_faded':
        headline, accent = 'WATCH ENDED', 'sample'
        ending = {'horizon_elapsed': f"The {config.followup_horizon_minutes}-minute watch window is complete.",
                  'update_limit': 'The update limit has been reached; this watch is now closed.',
                  'late_expiry': 'The watch window ended before a timely closing check was available.',
                  'disabled': 'Follow-through was disabled; this watch is now closed.'}[reason]
        latest = {'holding': 'The original condition still qualifies at this check.',
                  'faded': 'The original condition no longer qualifies at this check.',
                  'unavailable': 'A valid market conclusion is unavailable.'}[condition]
        read = ending + ' ' + latest
        next_check = 'Tracking has ended for this alert. A later qualifying alert starts a separate watch.'
    elif condition == 'faded':
        headline, accent = 'CONDITION FADED', 'sample'
        read = 'Fresh readings no longer meet the original rule. This watch is closed.'
        next_check = 'Reassess the original thesis. A faded condition does not by itself establish a reversal.'
    elif condition == 'unavailable':
        headline, accent = 'CHECK PAUSED', 'degraded'
        read = 'The original condition cannot be verified with the required fresh measurements and baselines.'
        next_check = 'Treat the condition as unconfirmed until coverage returns. Missing data is not a market reversal.'
    else:
        headline = 'COVERAGE BACK · CONDITION HOLDS' if detail['recovered'] else 'CONDITION HOLDS'
        accent = 'recovered' if detail['recovered'] else 'brief'
        read = 'The original rule still qualifies at this sampled check. Conditions between checks are not established.'
        next_check = 'Keep the original scenario on watch and reassess if its conditions change.'
    fields = [('The update', read), ('Your next check', next_check)]
    if condition != 'unavailable':
        changes = {row['venue']: row for row in detail['comparisons']}
        since = {row['venue']: row for row in detail['since_original']}
        for obs in observations:
            delta = since[obs.venue]
            value = venue_lines(obs, changes.get(obs.venue), config.lookback_minutes)
            value += (f"\nSince original · Mark {percent(delta['price_pct'])} · OI {percent(delta['oi_base_pct'])}"
                      f"\nFunding change {delta['funding_delta_bps_8h']:+.2f} bps / 8h eq.")
            fields.append((VENUES[obs.venue], value))
        if detail['rule'].startswith('price_oi'):
            fields.append(('Two different comparisons',
                           f'The rule uses a rolling ~{config.lookback_minutes}m baseline. '
                           'Since-original changes use the marks and OI recorded in the initial alert. '
                           'The rolling pattern can fade while price remains above its original mark.'))
    fields.append(('Original rule', recheck_rule(config, detail['rule'])))
    elapsed = (detail['checked_at'] - detail['original_created_at']) / 60
    description = (ALERT_COPY[detail['rule']][0] + f" · Update {detail['sequence']} · +{elapsed:.1f}m\n"
                   + local_stamp(detail['checked_at'], config.timezone)
                   + '\nOriginal · ' + local_stamp(detail['original_created_at'], config.timezone)
                   + '\nWatch ref · ' + detail['original_id'])
    return card(detail['asset'] + ' · ' + headline, description, fields, COLORS[accent], detail['checked_at'],
                'Sampled condition tracking. Mark changes are not trading returns. OI: coin units. Funding: 8h equivalents.')
