"""One collector cycle, one archive transaction, then optional external delivery."""

from contextlib import contextmanager
import fcntl
from pathlib import Path

from .engine import assess, health_event, market_alerts, summaries


@contextmanager
def process_lock(database):
    path = Path(str(database) + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('another Market Watch process is running') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run_cycle(config, store, observations, errors, routes, now):
    accepted, issues = assess(config, observations, errors, now)
    with store.db:
        store.add_observations(accepted)
        events = health_event(config, store, issues, now)
        events += market_alerts(config, store, accepted, now)
        events += summaries(config, store, accepted, issues, now)
        result = []
        for event in events:
            target_routes = [r for r in routes if r.audience == event.audience]
            event_id = store.add_event(event, target_routes)
            result.append({'id': event_id, 'kind': event.kind, 'audience': event.audience, 'text': event.text})
        store.record_cycle(now, issues, len(accepted))
    return {'observations': len(accepted), 'issues': issues, 'events': result}
