"""Conditional position guidance and funding arithmetic, never a fitted forecast."""

from .rules import matching_rules

VENUES = {'hyperliquid': 'Hyperliquid', 'okx': 'OKX'}
VERSION = 'position-playbook-v1'


def direction(config, observations, comparisons):
    venues = {o.venue for o in observations}
    changes = [c for c in comparisons if c['venue'] in venues]
    if len(venues) < config.minimum_venues:
        return 'unavailable'
    if len({c['venue'] for c in changes}) != len(changes) or {c['venue'] for c in changes} != venues:
        return 'unconfirmed'
    matched = matching_rules(config, observations, changes)
    if 'price_oi_up' in matched:
        return 'bullish_continuation'
    if 'price_oi_down' in matched:
        return 'bearish_continuation'
    return 'unconfirmed'


def funding_budget(observations):
    """A standard 10,000 quote-unit notional; positive long cash flow is a receipt."""
    return [{'venue': o.venue, 'quote_currency': o.quote_currency,
             'notional': 10000, 'interval_hours': o.funding_interval_hours,
             'long_cashflow_interval': -10000 * o.funding_rate,
             'short_cashflow_interval': 10000 * o.funding_rate,
             'long_cashflow_8h': -o.funding_bps_8h,
             'short_cashflow_8h': o.funding_bps_8h}
            for o in sorted(observations, key=lambda o: o.venue)]


def build_playbook(config, rule, observations, comparisons):
    bias = direction(config, observations, comparisons)
    if bias == 'bullish_continuation':
        read = ('Bullish continuation candidate: another leg higher is the scenario to test. '
                'Price and coin-unit OI are rising across the covered venues; this does not identify who initiated the contracts.')
        position = ('Long: Keep the continuation thesis conditional on the price/OI rule holding; reassess adds if it fades.\n'
                    'Short: This pattern opposes a fresh fade. Avoid adding solely because funding is high.\n'
                    'New entry: Wait for a price-defined entry and stop; this expansion alert alone is not an entry trigger.')
    elif bias == 'bearish_continuation':
        read = ('Bearish continuation candidate: another leg lower is the scenario to test. '
                'Price is falling as coin-unit OI builds across the covered venues; short initiation is not established.')
        position = ('Long: Recheck your exit/invalidation plan before adding into the selloff.\n'
                    'Short: Keep the continuation thesis conditional on the price/OI rule holding; reassess adds if it fades.\n'
                    'New entry: Wait for a price-defined entry and stop; this expansion alert alone is not an entry trigger.')
    else:
        read = 'Direction unconfirmed by the shared price/OI rule. No directional entry is supported by this funding condition alone.'
        position = ('Long: Check the funding debit or credit below against your holding plan.\n'
                    'Short: Check the opposite cash flow; a credit does not protect against an adverse price move.\n'
                    'New entry: Wait for price confirmation. A funding extreme or gap alone is not a buy/sell trigger.')
    if rule == 'positive_funding':
        read += ' Longs are paying elevated estimated carry; high funding alone does not establish a top.'
    elif rule == 'negative_funding':
        read += ' Shorts are paying elevated estimated carry; negative funding alone does not establish a bottom.'
    carry = None
    if rule == 'funding_divergence' and len(observations) >= 2:
        low, high = min(observations, key=lambda o: o.funding_bps_8h), max(observations, key=lambda o: o.funding_bps_8h)
        gap = high.funding_bps_8h - low.funding_bps_8h
        if gap > 0:
            carry = {'long_venue': low.venue, 'short_venue': high.venue, 'gap_bps_8h': gap}
            position = (f'Long: {VENUES[low.venue]} has more favorable normalized funding.\n'
                        f'Short: {VENUES[high.venue]} has more favorable normalized funding.\n'
                        f'Switching: The gross funding difference is {gap:.2f} bps / 8h eq. '
                        'Compare it with round-trip fees, spread, slippage and basis before moving.\n'
                        + ('New entry: Treat the gap as a venue-cost comparison; wait for a separate price trigger.'
                           if bias == 'unconfirmed' else
                           'New entry: Use the directional scenario above, but wait for a price-defined entry and stop.'))
        else:
            position = 'Funding is tied on the normalized basis. There is no current funding advantage for either side between these venues.'
    return {'version': VERSION, 'direction': bias, 'rule': rule, 'read': read,
            'position': position, 'carry': carry, 'funding_budget': funding_budget(observations)}


def budget_text(observations):
    def flow(value):
        return ('receive ' if value > 0 else 'pay ' if value < 0 else '') + f'{abs(value):.2f}'
    lines = []
    for row in funding_budget(observations):
        lines.append(f"{VENUES[row['venue']]} · Long {flow(row['long_cashflow_8h'])} / Short {flow(row['short_cashflow_8h'])} {row['quote_currency']} / 8h eq.")
    return '\n'.join(lines) + '\nPer 10,000 quote-unit notional at unchanged rates, before fees. Actual intervals/settlement amounts differ.'


def followup_action(rule, condition, closed_reason):
    if condition == 'unavailable':
        return 'Pause new decisions based on this alert. Use your existing risk limits; missing data cannot confirm an exit or reversal.'
    if closed_reason and closed_reason != 'condition_faded':
        return 'Tracking has ended. Do not treat this expired watch as a fresh entry or a continuing hold instruction.'
    if condition == 'faded':
        if rule == 'price_oi_up':
            return ('Long: Cancel new adds justified only by this expansion pattern and reassess your original exit rule. '
                    'A fade alone is not a short trigger.')
        if rule == 'price_oi_down':
            return ('Short: Cancel new adds justified only by this expansion pattern and reassess your original exit rule. '
                    'A fade alone is not a long trigger.')
        if rule == 'funding_divergence':
            return 'Re-price the carry comparison before moving venues. The gap no longer meets the original threshold; do not act on the old spread.'
        return 'Recalculate carrying costs before changing exposure. The funding extreme has cooled; that does not establish a price reversal.'
    if rule == 'price_oi_up':
        return 'Long: The continuation condition remains intact; keep your exit rule active. Short: Do not add a fade on this evidence alone. No new entry trigger is confirmed.'
    if rule == 'price_oi_down':
        return 'Short: The continuation condition remains intact; keep your exit rule active. Long: Recheck downside exposure before adding. No new entry trigger is confirmed.'
    return 'Use the current carry budget below, not the original quote. Keep direction and holding costs separate when deciding whether to add or reduce exposure.'
