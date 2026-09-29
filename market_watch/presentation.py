"""Deterministic Tokn cards and matching plain text; no generated market claims."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


BRAND = 'TOKN / MARKET WATCH'
COLORS = {'up': 0x38BDF8, 'down': 0xFB7185, 'funding': 0xFBBF24,
          'spread': 0xA78BFA, 'brief': 0x38BDF8, 'sample': 0x94A3B8,
          'degraded': 0xFBBF24, 'recovered': 0x34D399}
VENUES = {'hyperliquid': 'Hyperliquid', 'okx': 'OKX'}
FOOTER = 'OI changes use coin units. Funding: 8h equivalent estimates. Market monitoring only.'
ALERT_COPY = {
    'price_oi_up': ('PRICE ↑ / OI ↑', 'up',
        'Price up. Positioning up.',
        'Open interest is expanding alongside price. This does not identify whether new positions are longs or shorts.',
        'Watch whether price and open interest keep rising together.'),
    'price_oi_down': ('PRICE ↓ / OI ↑', 'down',
        'Price down. Positioning up.',
        'Open interest is expanding during the drop. That alone does not establish continued downside.',
        'Watch whether open interest keeps expanding as price falls, or the pattern breaks.'),
    'positive_funding': ('LONGS PAYING UP', 'funding',
        'Positive funding is elevated across the covered venues.',
        'At these estimated rates, longs pay shorts. Positive funding alone does not establish a reversal.',
        'Watch whether funding cools or stays elevated alongside price and open interest.'),
    'negative_funding': ('SHORTS PAYING UP', 'funding',
        'Negative funding is elevated across the covered venues.',
        'At these estimated rates, shorts pay longs. Negative funding alone does not establish a rebound.',
        'Watch whether funding moves toward zero or stays negative as price changes.'),
    'funding_divergence': ('FUNDING SPLIT', 'spread',
        'The venues are pricing funding differently.',
        'Rates differ on the same 8h basis. Fees, basis moves and changing rates can outweigh the gap.',
        'Watch whether the funding gap widens or narrows across fresh readings.'),
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


def alert_card(config, rule, asset, observations, comparisons, now):
    headline, accent, hook, interpretation, watch = ALERT_COPY[rule]
    changes = {row['venue']: row for row in comparisons}
    coverage = f'{len(observations)}/{len(config.venues)} fresh venues'
    context = f'~{config.lookback_minutes}m window' if rule.startswith('price_oi') else 'Current funding estimates'
    fields = [(VENUES[obs.venue], venue_lines(obs, changes.get(obs.venue), config.lookback_minutes))
              for obs in sorted(observations, key=lambda row: row.venue)]
    if rule == 'funding_divergence':
        gap = max(o.funding_bps_8h for o in observations) - min(o.funding_bps_8h for o in observations)
        fields.append(('Funding gap · 8h equivalent', f'{gap:.2f} bps · 1 bp = 0.01 percentage points'))
    fields += [('The read', interpretation), ('Watch next', watch)]
    return card(asset + ' · ' + headline,
                hook + '\n' + context + ' · ' + coverage + '\n' + local_stamp(now, config.timezone),
                fields, COLORS[accent], now)


def brief_card(config, audience, covered, observations, comparisons, issues, now):
    fields, available = [], 0
    for asset in covered:
        group = sorted((o for o in observations if o.asset == asset), key=lambda row: row.venue)
        if len(group) < config.minimum_venues:
            fields.append((asset, f'{len(group)}/{len(config.venues)} fresh venues · analysis paused.'))
            continue
        available += 1
        changes = {r['venue']: r for r in comparisons.get(asset, [])}
        blocks = [VENUES[o.venue] + '\n' + venue_lines(o, changes.get(o.venue), config.lookback_minutes) for o in group]
        if len(changes) < len(group):
            blocks.append(f'~{config.lookback_minutes}m changes appear when a valid baseline is available.')
        fields.append((asset, '\n\n'.join(blocks)))
    local = datetime.fromtimestamp(now, ZoneInfo(config.timezone))
    title = ('AM BRIEF' if local.hour < 12 else 'PM BRIEF') if audience == 'paid' else 'FREE LOOK · ' + ' / '.join(covered)
    description = local_stamp(now, config.timezone) + f'\nCoverage · {available}/{len(covered)} assets ready'
    if issues:
        description += '\nSome source measurements are unavailable; affected data is withheld.'
    if audience == 'free':
        fields.append(('Inside the full feed', 'BTC, ETH and SOL coverage · positioning alerts · twice-daily briefs.'))
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
