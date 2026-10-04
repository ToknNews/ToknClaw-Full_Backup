"""Prospective execution-cost screen; estimates, never fills or trading returns."""

from copy import deepcopy
import math

POLICY_VERSION = 'execution-costs-v1'
FEE_REFERENCE = 'https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees'


def policy_for(config):
    return {'version': POLICY_VERSION,
            'fee_bps_per_side': config.setup_fee_bps_per_side,
            'slippage_bps_per_side': config.setup_slippage_bps_per_side,
            'min_atr_bps': config.setup_min_atr_bps,
            'min_risk_bps': config.setup_min_risk_bps,
            'min_target_2_net_rr': config.setup_min_net_rr,
            'fee_reference': FEE_REFERENCE, 'fee_reference_checked': '2026-10-04',
            'funding_included': False,
            'model': 'Per-unit fee plus execution allowance on entry and each hypothetical exit notional; no fills.'}


def economics(spec, entry, policy):
    """USD per one base unit. Each target is a separate full-exit scenario."""
    sign = 1 if spec['side'] == 'long' else -1
    rate = (policy['fee_bps_per_side'] + policy['slippage_bps_per_side']) / 10000
    stop = spec['invalidation']
    stop_cost = (entry + stop) * rate
    gross_risk = sign * (entry - stop)
    risk = gross_risk + stop_cost
    result = {'entry': entry, 'gross_risk': gross_risk, 'stop_cost': stop_cost,
              'net_risk': risk, 'risk_bps': gross_risk / entry * 10000}
    for index in (1, 2):
        target = spec['target_' + str(index)]
        gross = sign * (target - entry)
        cost = (entry + target) * rate
        result['target_' + str(index)] = {
            'gross_reward': gross, 'estimated_cost': cost, 'net_reward': gross - cost,
            'net_rr': (gross - cost) / risk,
            'gross_move_bps': gross / entry * 10000,
            'cost_bps': cost / entry * 10000}
    return result


def screen_candidate(spec, config):
    """Return a fresh qualified spec or rejection evidence. Never modify issued specs."""
    policy = policy_for(config)
    if any(not math.isfinite(spec[key]) or spec[key] <= 0 for key in
           ('trigger', 'entry_limit', 'invalidation', 'target_1', 'target_2', 'atr')):
        return None, {'policy': policy, 'reasons': ['invalid_price_levels']}
    at_trigger = economics(spec, spec['trigger'], policy)
    atr_bps = spec['atr'] / spec['trigger'] * 10000
    reasons = []
    if at_trigger['target_1']['net_reward'] <= 0 or at_trigger['target_2']['net_reward'] <= 0:
        reasons.append('targets_do_not_cover_costs')
    if atr_bps < policy['min_atr_bps']:
        reasons.append('volatility_too_small')
    if at_trigger['risk_bps'] < policy['min_risk_bps']:
        reasons.append('invalidation_too_close')
    if at_trigger['target_2']['net_rr'] < policy['min_target_2_net_rr']:
        reasons.append('net_reward_risk_too_low')
    evidence = {'policy': policy, 'atr_bps': atr_bps, 'at_trigger': at_trigger, 'reasons': reasons}
    if reasons:
        return None, evidence
    # Solve net target-2 reward >= m * net stop risk for entry, separately for
    # each direction. This narrows the original band; targets/stop never move.
    sign = 1 if spec['side'] == 'long' else -1
    rate = (policy['fee_bps_per_side'] + policy['slippage_bps_per_side']) / 10000
    minimum = policy['min_target_2_net_rr']
    boundary = ((sign - rate) * (spec['target_2'] + minimum * spec['invalidation'])
                / ((sign + rate) * (1 + minimum)))
    qualified = deepcopy(spec)
    qualified['structural_entry_limit'] = spec['entry_limit']
    qualified['entry_limit'] = (min if sign == 1 else max)(spec['entry_limit'], boundary)
    # Defend the boundary against harmless floating-point cancellation.
    qualified['entry_limit'] = (max if sign == 1 else min)(spec['trigger'], qualified['entry_limit'])
    evidence['at_entry_limit'] = economics(qualified, qualified['entry_limit'], policy)
    qualified['cost_screen'] = evidence
    return qualified, evidence


def confirmation_economics(spec, entry):
    """Old watches have no policy: preserve their original rules and identity."""
    screen = spec.get('cost_screen')
    if not screen:
        return None
    return economics(spec, entry, screen['policy'])
