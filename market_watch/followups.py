"""Persistent, receipt-gated follow-through for newly created market alerts."""

import json

from .config import Config
from .engine import assess, change, comparisons_for, deadline
from .models import Event, Observation
from .presentation import followup_card
from .rules import matching_rules


def start_watch(config, store, event, original_id):
    if not config.followup_enabled or event.kind != 'alert' or event.audience != 'paid':
        return
    evidence = event.evidence
    originals = [Observation(**row) for row in evidence['observations']]
    spec = {'config': evidence['config'], 'observations': evidence['observations'],
            'comparison_venues': [row['venue'] for row in evidence['comparisons']]}
    watermarks = {obs.venue: [obs.observed_at, obs.fetched_at] for obs in originals}
    store.start_watch(original_id, evidence['asset'], evidence['rule'], event.created_at, spec, watermarks)


def evaluate_watch(config, store, track, spec, watermarks, observations, errors, now):
    originals = {row['venue']: Observation(**row) for row in spec['observations']}
    accepted, _ = assess(config, observations, errors, now)
    group = sorted((obs for obs in accepted if obs.asset == track['asset'] and obs.venue in originals),
                   key=lambda obs: obs.venue)
    # Require the entire original cohort, even if the configured minimum was smaller.
    if {obs.venue for obs in group} != set(originals):
        return 'unavailable', 'coverage_unavailable', [], [], [], watermarks
    if any(obs.instrument != originals[obs.venue].instrument for obs in group):
        return 'unavailable', 'instrument_changed', [], [], [], watermarks
    if any(obs.observed_at <= watermarks[obs.venue][0] or obs.fetched_at <= watermarks[obs.venue][1]
           for obs in group):
        return 'unavailable', 'no_new_reading', [], [], [], watermarks
    watermarks = {obs.venue: [obs.observed_at, obs.fetched_at] for obs in group}
    comparisons = comparisons_for(config, store, group)
    if track['rule'].startswith('price_oi'):
        cohort = set(spec['comparison_venues'])
        comparisons = [row for row in comparisons if row['venue'] in cohort]
        if {row['venue'] for row in comparisons} != cohort or len(comparisons) < config.minimum_venues:
            return 'unavailable', 'baseline_unavailable', [], [], [], watermarks
    since = [{'venue': obs.venue,
              'price_pct': change(obs.mark_price, originals[obs.venue].mark_price),
              'oi_base_pct': change(obs.oi_base, originals[obs.venue].oi_base),
              'funding_delta_bps_8h': obs.funding_bps_8h - originals[obs.venue].funding_bps_8h}
             for obs in group]
    condition = 'holding' if track['rule'] in matching_rules(config, group, comparisons) else 'faded'
    return condition, 'fresh_check', group, comparisons, since, watermarks


def advance_watches(config, store, observations, errors, routes, now):
    """Called inside the same transaction as observations, new alerts and the outbox."""
    result = []
    for track in store.due_watches(now, include_all=not config.followup_enabled):
        spec = json.loads(track['spec'])
        frozen = Config(**spec['config'])
        watermarks = json.loads(track['watermarks'])
        reason = ''
        # No stale catch-up publishing after a missed closing checkpoint.
        publish = True
        if not config.followup_enabled:
            reason, publish = 'disabled', False
        elif now > track['horizon_at'] + frozen.max_age_seconds:
            reason, publish = 'late_expiry', False
        if reason:
            condition, assessment, group, comparisons, since = 'unavailable', reason, [], [], []
        else:
            condition, assessment, group, comparisons, since, watermarks = evaluate_watch(
                frozen, store, track, spec, watermarks, observations, errors, now)
            if now >= track['horizon_at']:
                reason = 'horizon_elapsed'
            elif condition == 'faded':
                reason = 'condition_faded'
            elif condition != track['state'] and track['update_count'] >= frozen.followup_max_updates - 1:
                reason = 'update_limit'
        closed = bool(reason)
        state = ('faded' if reason == 'condition_faded' else 'expired') if closed else condition
        changed = closed or state != track['state']
        detail = {
            'original_id': track['original_id'], 'original_created_at': track['original_at'],
            'asset': track['asset'], 'rule': track['rule'], 'config': spec['config'],
            'horizon_at': track['horizon_at'], 'checked_at': now,
            'condition': condition, 'closed_reason': reason, 'assessment': assessment,
            'recovered': track['state'] == 'unavailable' and condition in ('holding', 'faded'),
            'observations': [obs.to_dict() for obs in group], 'comparisons': comparisons,
            'since_original': since,
        }
        count = track['update_count']
        if changed:
            count += 1
            detail['sequence'] = count
            text, presentation = followup_card(frozen, detail, group)
            detail['presentation'] = presentation
            event = Event('followup:' + track['original_id'] + ':' + str(count), 'followup', 'paid',
                          now, deadline(frozen, group, now), text, detail)
            child_id = store.add_followup(event, track['original_id'], count, routes if publish else [])
            result.append({'id': child_id, 'kind': event.kind, 'audience': event.audience, 'text': text})
        store.update_watch(track['original_id'], state, count, now,
                           min(now + frozen.followup_check_minutes * 60, track['horizon_at']),
                           closed, watermarks, detail)
    return result
