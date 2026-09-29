"""Reproducible observations and explanations; no predictions of profit."""

from dataclasses import asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .models import Event, event_id
from .rules import matching_rules
from .playbooks import build_playbook
from .presentation import alert_card, brief_card, health_card


def stamp(now):
    return datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def deadline(config, observations, now):
    limits = [now + config.delivery_ttl_seconds]
    limits.extend(min(o.observed_at, o.fetched_at) + config.max_age_seconds for o in observations)
    return min(limits)


def change(current, previous):
    return (current / previous - 1) * 100


def comparisons_for(config, store, observations):
    comparisons = []
    for obs in observations:
        base = store.baseline(obs, config.lookback_minutes * 60, config.baseline_tolerance_seconds)
        if base:
            comparisons.append({
                'venue': obs.venue, 'baseline': base.to_dict(),
                'price_pct': change(obs.mark_price, base.mark_price),
                'oi_base_pct': change(obs.oi_base, base.oi_base),
            })
    return comparisons


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
        comparisons = comparisons_for(config, store, group)
        candidates = matching_rules(config, group, comparisons)
        for rule in candidates:
            key = config.rule_version + ':' + asset + ':' + rule
            last = store.last_event(key)
            if last is not None and now - last < config.cooldown_minutes * 60:
                continue
            if store.alert_count(now - 3600) + len(events) >= config.max_alerts_per_hour:
                return events
            text, presentation = alert_card(config, rule, asset, group, comparisons, now, reference=event_id(key, now))
            evidence = {'rule': rule, 'asset': asset, 'config': asdict(config), 'observations': [o.to_dict() for o in group],
                        'comparisons': comparisons, 'presentation': presentation,
                        'playbook': build_playbook(config, rule, group, comparisons)}
            events.append(Event(key, 'alert', 'paid', now, deadline(config, group, now),
                                text, evidence))
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
        visible = [o for o in observations if o.asset in covered]
        visible_issues = {key: value for key, value in issues.items()
                          if ':' not in key or key.rsplit(':', 1)[-1] in covered}
        comparisons = {asset: comparisons_for(config, store, [o for o in visible if o.asset == asset]) for asset in covered}
        text, presentation = brief_card(config, audience, covered, visible, comparisons, visible_issues, now)
        evidence = {'observations': [o.to_dict() for o in visible], 'issues': visible_issues,
                    'timezone': config.timezone, 'comparisons': comparisons, 'presentation': presentation}
        events.append(Event(key, 'summary', audience, now, deadline(config, visible, now), text, evidence))
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
    text, presentation = health_card(config, current, now)
    return [Event(key, 'health', 'paid', now, now + config.delivery_ttl_seconds, text,
                  {'issues': current, 'presentation': presentation})]
