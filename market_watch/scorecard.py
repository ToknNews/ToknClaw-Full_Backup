"""Operator-only shadow evidence counts from one read-only SQLite snapshot."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from statistics import median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

METHOD = 'setup-shadow-scorecard-v1'
INTERVAL = 300
TERMINAL = {'completed', 'invalidated', 'expired', 'ambiguous', 'unavailable', 'cancelled'}
ACTIVE = {'forming', 'armed', 'triggered', 'target_1'}
LEVELS = ('trigger', 'entry_limit', 'structural_entry_limit', 'invalidation',
          'target_1', 'target_2', 'atr', 'reference_risk')
LIMITS = [
    'Archived shadow setups only; publication intent is frozen at formation, not a delivery receipt.',
    'Counts describe sampled conditions, not fills, realized P&L, win rates or proven profit.',
    'Target touches do not establish intrabar ordering or an executable exit.',
    'Estimated economics are archived hypothetical inputs; funding, fills and actual costs are not measured.',
    'Carry-in watches are separate from new formations; repeated updates never add setups.',
    'Screen counts describe recorded asset/decision buckets, not all market opportunities or independent trials.',
    'No archived sample means unknown coverage, not a passing or rejected candidate.',
    'No sample size alone establishes an edge; all results remain descriptive.',
]


def instant(value):
    """Require an explicit UTC offset, avoiding ambiguous/nonexistent local wall times."""
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError('scorecard timestamps require ISO 8601 with an explicit UTC offset') from None


def _number(value):
    return type(value) in (float, int) and math.isfinite(value)


def _object(raw):
    def invalid(_):
        raise ValueError('nonfinite archive number')
    result = json.loads(raw, parse_constant=invalid)
    if not isinstance(result, dict):
        raise ValueError('invalid archive object')
    return result


def _key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()[:20]


def _cohort(spec):
    config = spec['config']
    screen = spec.get('cost_screen')
    policy = screen['policy'] if screen is not None else None
    if policy is not None and (not isinstance(policy, dict) or not isinstance(policy.get('version'), str)):
        raise ValueError('invalid frozen policy')
    return {'setup_version': spec['version'],
            'cost_policy_version': policy['version'] if policy else 'legacy',
            'asset': spec['asset'], 'side': spec['side'], 'venue': spec['venue'],
            'instrument': spec['instrument'], 'quote': spec['quote'], 'timeframe': spec['timeframe'],
            'frozen_setup_settings': {k: v for k, v in config.items() if k.startswith('setup_')},
            'frozen_cost_policy': policy}


def _history(root, rows, cutoff):
    """Reconstruct only emitted evidence. Never consult mutable setups.payload or replay candles."""
    stage, reason, paused = 'forming', 'range_edge_approach', False
    pause_reason = None
    times, issues = {}, set()
    previous_sequence, last_at = -1, root['created_at']
    confirmation = None
    spec = root['spec']
    for row in rows:
        if row['created_at'] >= cutoff:
            continue
        try:
            evidence = _object(row['evidence'])
            sequence = row['sequence']
            current = evidence['stage']
            if (type(sequence) is not int or sequence != previous_sequence + 1
                    or evidence['sequence'] != sequence or evidence['setup_id'] != root['id']
                    or evidence['checked_at'] != row['created_at'] or evidence['spec'] != spec
                    or not isinstance(evidence.get('reason', ''), str)
                    or current not in ACTIVE | TERMINAL | {'paused', 'resumed'}):
                raise ValueError('inconsistent event evidence')
            previous_sequence = sequence
            last_at = row['created_at']
            if current == 'paused':
                paused = True
                pause_reason = evidence.get('reason', 'reason_unrecorded')
            elif current == 'resumed':
                paused = False
                pause_reason = None
            else:
                if current in {'target_1', 'completed'} and 'triggered' not in times:
                    issues.add('outcome_without_archived_retest')
                if stage in TERMINAL and current != stage:
                    issues.add('event_after_terminal')
                stage, reason = current, evidence.get('reason', 'reason_unrecorded')
                paused = False
                pause_reason = None
                times.setdefault(current, row['created_at'])
                if current == 'triggered' and confirmation is None:
                    confirmation = evidence.get('execution_costs')
        except (ValueError, TypeError, KeyError, AttributeError):
            issues.add('missing_or_inconsistent_event_sequence')
            # Continue counting observed evidence, but never present a clean outcome.
            if type(row['sequence']) is int:
                previous_sequence = row['sequence']
    return {'stage': stage, 'reason': reason, 'checks_paused': paused,
            'pause_reason': pause_reason,
            'first_stage_at': times, 'last_event_at': last_at,
            'evidence_issues': sorted(issues), 'confirmation_estimate': confirmation}


def _records(db, start, end):
    rows = db.execute('''SELECT e.id,e.created_at,e.kind,e.evidence,l.setup_id,l.sequence
        FROM events e LEFT JOIN setup_events l ON l.event_id=e.id
        WHERE e.kind IN ('setup','setup_update') AND e.created_at<?
        ORDER BY e.created_at,l.sequence,e.id''', (end,)).fetchall()
    histories = defaultdict(list)
    excluded, roots = [], []
    for row in rows:
        if row['setup_id'] is None:
            excluded.append({'event_id': row['id'], 'reason': 'unlinked_setup_event'})
            continue
        histories[row['setup_id']].append(row)
        if row['kind'] == 'setup':
            roots.append(row)
    output, prior_closed = [], 0
    root_ids = {row['id'] for row in roots}
    for setup_id in sorted(set(histories) - root_ids):
        excluded.append({'setup_id': setup_id, 'reason': 'missing_initial_event'})
    for row in roots:
        try:
            evidence = _object(row['evidence'])
            spec = evidence['spec']
            if (row['setup_id'] != row['id'] or row['sequence'] != 0
                    or evidence['stage'] != 'forming' or spec['created_at'] != row['created_at']
                    or type(spec['config'].get('setup_publish')) is not bool
                    or any(not _number(spec[k]) or spec[k] <= 0 for k in LEVELS
                           if k != 'structural_entry_limit' or k in spec)):
                raise ValueError('invalid formation evidence')
            cohort = _cohort(spec)
            if spec['config']['setup_publish']:
                excluded.append({'setup_id': row['id'], 'reason': 'live_publication_intent'})
                continue
        except (ValueError, TypeError, KeyError, AttributeError):
            excluded.append({'setup_id': row['id'], 'reason': 'invalid_formation_evidence'})
            continue
        root = {'id': row['id'], 'created_at': row['created_at'], 'spec': spec}
        if row['created_at'] < start:
            before = _history(root, histories[row['id']], start)
            if before['stage'] in TERMINAL and not before['evidence_issues']:
                prior_closed += 1
                continue
        state = _history(root, histories[row['id']], end)
        output.append({'setup_id': row['id'], 'created_at': row['created_at'],
                       'population': 'formed_in_window' if row['created_at'] >= start else 'carry_in',
                       'cohort_id': _key(cohort), 'cohort': cohort, **state,
                       'levels': {k: spec[k] for k in LEVELS if k in spec},
                       'formation_estimate': spec.get('cost_screen'),
                       'phase': ('after_retest' if 'triggered' in state['first_stage_at']
                                 else 'unknown_retest' if state['evidence_issues'] else 'before_retest')})
    return output, excluded, prior_closed


def _summary(records, start):
    result = {'distinct_setups': len(records), 'breakout_confirmed_by_cutoff': 0,
              'retest_confirmed_by_cutoff': 0, 'breakout_confirmed_in_window': 0,
              'retest_confirmed_in_window': 0, 'target_1_event_observed': 0,
              'target_2_event_observed': 0, 'target_1_then_invalidation': 0,
              'evidence_unavailable': 0, 'before_retest': {}, 'after_retest': {}, 'unknown_retest': {}}
    for phase in ('before_retest', 'after_retest', 'unknown_retest'):
        selected = [r for r in records if r['phase'] == phase]
        states, reasons, active_reasons, pauses = Counter(), Counter(), Counter(), Counter()
        for r in selected:
            state = 'evidence_unavailable' if r['evidence_issues'] else r['stage']
            states[state] += 1
            if state in TERMINAL:
                reasons[state + ':' + r['reason']] += 1
            elif state in ACTIVE:
                active_reasons[state + ':' + r['reason']] += 1
                if r['checks_paused']:
                    pauses[r['pause_reason']] += 1
        result[phase] = {'denominator_distinct_setups': len(selected),
                         'active_at_cutoff': sum(states[s] for s in ACTIVE),
                         'checks_paused_at_cutoff': sum(r['checks_paused'] for r in selected
                                                       if not r['evidence_issues'] and r['stage'] in ACTIVE),
                         'state_counts': dict(sorted(states.items())),
                         'active_last_event_reasons': dict(sorted(active_reasons.items())),
                         'pause_reasons': dict(sorted(pauses.items())),
                         'terminal_reasons': dict(sorted(reasons.items()))}
    clean_paths = 0
    for r in records:
        times = r['first_stage_at']
        for label, stage in [('breakout', 'armed'), ('retest', 'triggered')]:
            result[label + '_confirmed_by_cutoff'] += stage in times
            result[label + '_confirmed_in_window'] += stage in times and times[stage] >= start
        result['target_1_event_observed'] += 'target_1' in times
        result['target_2_event_observed'] += 'completed' in times
        result['target_1_then_invalidation'] += 'target_1' in times and r['stage'] == 'invalidated'
        result['evidence_unavailable'] += bool(r['evidence_issues'])
        clean_paths += (r['phase'] == 'after_retest' and not r['evidence_issues']
                        and r['stage'] in {'completed', 'invalidated'})
    result['observed_closed_retest_paths'] = clean_paths
    result['sample_state'] = 'descriptive_only' if clean_paths else 'insufficient_sample'
    return result


def _estimate_summary(records):
    output = {}
    for name, getter in (
        ('formation', lambda r: (r['formation_estimate'] or {}).get('at_trigger')),
        ('entry_limit', lambda r: (r['formation_estimate'] or {}).get('at_entry_limit')),
        ('confirmation', lambda r: r['confirmation_estimate']),
    ):
        for target in ('target_1', 'target_2'):
            values = []
            for record in records:
                estimate = getter(record)
                target_estimate = estimate.get(target) if isinstance(estimate, dict) else None
                value = target_estimate.get('net_rr') if isinstance(target_estimate, dict) else None
                if _number(value):
                    values.append(value)
            output[name + '_' + target + '_net_rr'] = {
                'available': len(values), 'unavailable': len(records) - len(values),
                'min': min(values) if values else None, 'median': median(values) if values else None,
                'max': max(values) if values else None}
    return output


def _screening(db, start, end):
    buckets, invalid, raw_attempts, outside = {}, 0, 0, 0
    for row in db.execute('SELECT id,collected_at,payload FROM setup_samples WHERE collected_at>=? '
                          'AND collected_at<? ORDER BY collected_at,id', (start, end)):
        try:
            payload = _object(row['payload'])
            close, health = payload['requested_close'], payload['health']
            screen = health['screen']
            if (not _number(close) or close % INTERVAL or close > row['collected_at']
                    or not isinstance(screen, dict) or type(health.get('publishing')) is not bool
                    or not isinstance(health.get('screen_details', {}), dict)
                    or not isinstance(health.get('primary_issues', {}), dict)
                    or ('cost_policy' in health and not isinstance(health['cost_policy'], dict))):
                raise ValueError('invalid sample')
            if not start <= close < end:
                outside += 1
                continue
            for asset, decision in screen.items():
                if not isinstance(asset, str) or not isinstance(decision, str):
                    raise ValueError('invalid screen')
            for asset, decision in screen.items():
                raw_attempts += 1
                buckets[(asset, close)] = {'asset': asset, 'decision': decision,
                    'collected_at': row['collected_at'], 'health': health,
                    'detail': health.get('screen_details', {}).get(asset, {})}
        except (ValueError, TypeError, KeyError, AttributeError):
            invalid += 1
    groups, assets = {}, defaultdict(list)
    live, unknown_details = 0, 0
    for (asset, close), item in sorted(buckets.items()):
        health, detail = item['health'], item['detail']
        assets[asset].append((close, item['collected_at'], bool(health.get('primary_issues', {}).get(asset))))
        if health['publishing']:
            live += 1
            continue
        policy = health.get('cost_policy')
        spec = {'asset': asset, 'sample_cost_policy': policy,
                'policy_version': policy.get('version', 'unrecorded') if isinstance(policy, dict) else 'unrecorded'}
        key = _key(spec)
        group = groups.setdefault(key, {'cohort_id': key, **spec, 'asset_decision_buckets': 0,
            'screen_counts': Counter(), 'cost_screened_buckets': 0, 'cost_rejected_buckets': 0,
            'cost_accepted_buckets': 0, 'multi_reason_counts': Counter()})
        group['asset_decision_buckets'] += 1
        group['screen_counts'][item['decision']] += 1
        if not isinstance(detail, dict):
            unknown_details += 1
            continue
        if 'reasons' in detail and 'policy' in detail:
            reasons = detail['reasons']
            if (not isinstance(reasons, list) or any(not isinstance(r, str) for r in reasons)
                    or detail['policy'] != policy):
                unknown_details += 1
                continue
            group['cost_screened_buckets'] += 1
            group['cost_rejected_buckets'] += bool(reasons)
            group['cost_accepted_buckets'] += not reasons
            group['multi_reason_counts'].update(set(reasons))
    expected = max(0, math.ceil(end / INTERVAL) - math.ceil(start / INTERVAL))
    coverage = []
    for asset, values in sorted(assets.items()):
        closes = [v[0] for v in values]
        # Include leading and trailing unobserved buckets, not only internal gaps.
        edges = [math.ceil(start / INTERVAL) * INTERVAL - INTERVAL, *closes,
                 (math.ceil(end / INTERVAL) - 1) * INTERVAL + INTERVAL]
        coverage.append({'asset': asset, 'expected_5m_buckets': expected,
                         'sampled_buckets': len(values), 'unobserved_buckets': expected - len(values),
                         'largest_unobserved_run_buckets': max(int((b-a)/INTERVAL)-1 for a,b in zip(edges,edges[1:])),
                         'buckets_with_primary_issue': sum(v[2] for v in values),
                         'first_decision_close': min(closes), 'last_decision_close': max(closes),
                         'last_collected_at': max(v[1] for v in values)})
    for group in groups.values():
        for field in ('screen_counts', 'multi_reason_counts'):
            group[field] = dict(sorted(group[field].items()))
    return {'deduplication': 'Last archived attempt before cutoff per asset/requested_close; no pooling retries.',
            'raw_asset_attempts': raw_attempts, 'distinct_asset_decision_buckets': len(buckets),
            'superseded_retry_attempts': raw_attempts-len(buckets), 'invalid_sample_rows': invalid,
            'rows_for_decision_closes_outside_window': outside, 'live_buckets_excluded': live,
            'invalid_screen_details': unknown_details, 'coverage_by_observed_asset': coverage,
            'asset_universe_limit': 'Only assets present in archived screens are known; absent assets and disabled periods are not reconstructed.',
            'cohorts': [groups[k] for k in sorted(groups)]}


def report(path, start, end, display_timezone, include_details=False):
    """An explicit half-open window; BEGIN pins all reads to one archive snapshot."""
    if (not _number(start) or not _number(end) or start < 0 or end <= start
            or end-start > 365*86400):
        raise ValueError('scorecard requires an increasing window of at most 365 days')
    try:
        zone = ZoneInfo(display_timezone)
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise ValueError('scorecard requires a valid IANA timezone') from None
    if not Path(path).is_file():
        raise ValueError('scorecard requires an existing archive; no file was created')
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=20)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        if db.execute('PRAGMA user_version').fetchone()[0] != 3:
            raise ValueError('scorecard requires existing setup archive schema 3; no migration was performed')
        records, excluded, prior_closed = _records(db, start, end)
        screening = _screening(db, start, end)
        cohorts = []
        for key in sorted({r['cohort_id'] for r in records}):
            selected = [r for r in records if r['cohort_id'] == key]
            cohorts.append({'cohort_id': key, **selected[0]['cohort'],
                'populations': {p: _summary([r for r in selected if r['population'] == p], start)
                                for p in ('formed_in_window', 'carry_in')},
                'frozen_estimated_economics': _estimate_summary(selected)})
        output = {'method': METHOD, 'audience': 'operator_only', 'publication_mode': 'shadow',
            'window': {'start_inclusive': start, 'cutoff_exclusive': end, 'timezone': display_timezone,
                       'start_local': datetime.fromtimestamp(start, zone).isoformat(),
                       'cutoff_local': datetime.fromtimestamp(end, zone).isoformat(),
                       'cutoff_utc': datetime.fromtimestamp(end, timezone.utc).isoformat()},
            'populations': {p: _summary([r for r in records if r['population'] == p], start)
                            for p in ('formed_in_window', 'carry_in')},
            'prior_closed_setups_outside_population': prior_closed,
            'excluded_evidence': excluded,
            'excluded_evidence_scope': 'Retained setup-event prefix before cutoff, including older originals; entries are not a distinct-setup denominator.',
            'cohorts': cohorts, 'screening': screening,
            'sample_state_definition': 'insufficient_sample means no unambiguous completed/invalidated post-retest path in that population; descriptive_only never means statistical sufficiency.',
            'limitations': LIMITS}
        if include_details:
            output['setups'] = [{k: v for k, v in r.items() if k != 'cohort'} for r in records]
        return output
    finally:
        db.rollback()
        db.close()
