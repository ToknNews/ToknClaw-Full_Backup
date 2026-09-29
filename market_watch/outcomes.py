"""Read-only, as-of-safe mark outcomes for complete archived alert cohorts."""

from collections import Counter
import hashlib
import json
import math
from statistics import median

from .config import Config
from .models import Observation
from .playbooks import direction

HORIZONS = (15, 60, 240)
TOLERANCE_SECONDS = 180
METHOD = 'alert-mark-outcomes-v1'
SIGNAL_KEYS = ('minimum_venues', 'lookback_minutes', 'baseline_tolerance_seconds',
               'price_change_pct', 'oi_change_pct', 'funding_extreme_bps_8h',
               'funding_spread_bps_8h', 'max_age_seconds', 'max_price_disagreement_pct')
RULES = {'price_oi_up', 'price_oi_down', 'positive_funding', 'negative_funding', 'funding_divergence'}


def _event_spec(row):
    evidence = json.loads(row['evidence'])
    cfg = Config(**evidence['config'])
    rule, asset = evidence['rule'], evidence['asset']
    if rule not in RULES:
        raise ValueError('unsupported rule')
    originals = [Observation(**o) for o in evidence['observations']]
    if (len(originals) < cfg.minimum_venues or len({o.venue for o in originals}) != len(originals)
            or any(o.asset != asset or o.venue not in cfg.venues
                   or not o.fresh(row['created_at'], cfg.max_age_seconds)
                   or o.fetched_at > row['created_at'] or o.observed_at > row['created_at'] for o in originals)):
        raise ValueError('invalid original cohort')
    comparisons = evidence['comparisons']
    if not isinstance(comparisons, list) or len({c['venue'] for c in comparisons}) != len(comparisons):
        raise ValueError('invalid comparisons')
    for c in comparisons:
        if c['venue'] not in {o.venue for o in originals}:
            raise ValueError('invalid comparison venue')
        for key in ('price_pct', 'oi_base_pct'):
            if isinstance(c[key], bool) or not isinstance(c[key], (int, float)) or not math.isfinite(c[key]):
                raise ValueError('invalid comparison value')
    # Separate directional funding setups from flat/mixed/unconfirmed funding setups.
    bias = direction(cfg, originals, comparisons)
    spec = {'asset': asset, 'rule': rule, 'rule_version': cfg.rule_version,
            'direction': bias,
            'settings': {key: getattr(cfg, key) for key in SIGNAL_KEYS},
            'venues': sorted([o.venue, o.instrument, o.quote_currency] for o in originals),
            'comparison_venues': sorted(c['venue'] for c in comparisons)}
    key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:20]
    return key, spec, originals


def _sample(store, original, target, as_of):
    rows = store.db.execute('''SELECT observed_at,payload FROM observations
        WHERE venue=? AND asset=? AND instrument=? AND observed_at>=? AND observed_at<=?
        ORDER BY observed_at''', (original.venue, original.asset, original.instrument, target,
                                min(target + TOLERANCE_SECONDS, as_of)))
    for row in rows:
        try:
            o = Observation(**json.loads(row['payload']))
        except (ValueError, TypeError, KeyError):
            continue
        if (o.venue != original.venue or o.asset != original.asset or o.instrument != original.instrument
                or o.observed_at != row['observed_at'] or o.fetched_at > as_of
                or o.fetched_at > target + TOLERANCE_SECONDS
                or not o.fresh(o.fetched_at, TOLERANCE_SECONDS)):
            continue
        return o
    return None


def report(store, as_of, days=30, include_details=False):
    if isinstance(as_of, bool) or not isinstance(as_of, (int, float)) or not math.isfinite(as_of) or as_of <= 0:
        raise ValueError('invalid report time')
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError('outcome days must be between 1 and 365')
    groups, excluded, records = {}, [], []
    total = 0
    rows = store.db.execute('''SELECT id,created_at,evidence FROM events
        WHERE kind='alert' AND audience='paid' AND created_at>=? AND created_at<=?
        ORDER BY created_at,id''', (as_of - days * 86400, as_of))
    for row in rows:
        total += 1
        try:
            key, spec, originals = _event_spec(row)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            excluded.append({'event_id': row['id'], 'reason': 'invalid_or_unsupported_alert_evidence'})
            continue
        group = groups.setdefault(key, {'cohort_id': key, **spec, 'alerts': 0, '_buckets': {}})
        group['alerts'] += 1
        record = {'event_id': row['id'], 'created_at': row['created_at'], 'cohort_id': key, 'outcomes': []}
        for original in originals:
            for minutes in HORIZONS:
                target = row['created_at'] + minutes * 60
                sample = _sample(store, original, target, as_of) if as_of >= target else None
                state = 'measured' if sample else 'pending' if as_of < target + TOLERANCE_SECONDS else 'missing'
                bucket = group['_buckets'].setdefault((original.venue, minutes),
                                                       {'states': Counter(), 'returns': []})
                bucket['states'][state] += 1
                item = {'venue': original.venue, 'quote_currency': original.quote_currency,
                        'horizon_minutes': minutes, 'state': state, 'target_at': target}
                if sample:
                    movement = (sample.mark_price / original.mark_price - 1) * 100
                    if not math.isfinite(movement):
                        bucket['states'][state] -= 1
                        bucket['states']['missing'] += 1
                        item['state'] = 'missing'
                    else:
                        bucket['returns'].append(movement)
                        item.update(mark_change_pct=movement, original_mark=original.mark_price,
                                    original_observed_at=original.observed_at,
                                    observed_mark=sample.mark_price, observed_at=sample.observed_at,
                                    fetched_at=sample.fetched_at, sample_delay_seconds=sample.observed_at-target)
                record['outcomes'].append(item)
        if include_details:
            records.append(record)
    cohorts = []
    for group in groups.values():
        buckets = group.pop('_buckets')
        group['outcomes'] = []
        for (venue, minutes), bucket in sorted(buckets.items()):
            values, counts = bucket['returns'], bucket['states']
            group['outcomes'].append({'venue': venue, 'horizon_minutes': minutes,
                                     **{state: counts[state] for state in ('measured', 'pending', 'missing')},
                                     'median_mark_change_pct': median(values) if values else None,
                                     'min_mark_change_pct': min(values) if values else None,
                                     'max_mark_change_pct': max(values) if values else None,
                                     'positive_mark_changes': sum(x > 0 for x in values),
                                     'negative_mark_changes': sum(x < 0 for x in values),
                                     'flat_mark_changes': sum(x == 0 for x in values)})
        cohorts.append(group)
    output = {'method': METHOD, 'as_of': as_of, 'lookback_days': days,
              'horizons_minutes': list(HORIZONS), 'sampling_tolerance_seconds': TOLERANCE_SECONDS,
              'total_alerts': total, 'included_alerts': total-len(excluded),
              'excluded_alerts': excluded, 'cohorts': cohorts,
              'interpretation': ('Descriptive mark changes from alert creation, not fills, trading returns or win rates. '
                                 'No fees, realized funding or slippage deducted. Overlapping alerts are not independent. '
                                 'Extremes are across endpoint outcomes, not intratrade highs/lows. '
                                 'No out-of-sample edge has been established; do not use these counts as forecast probabilities.')}
    if include_details:
        output['events'] = records
    return output
