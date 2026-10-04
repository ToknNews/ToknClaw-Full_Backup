"""Python 3.10+ CLI. Default operation never sends a message."""

import argparse
from contextlib import nullcontext
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from .config import load_config
from .delivery import dispatch, routes_from_env
from .http import JsonClient
from .outcomes import report as outcome_report
from .service import process_lock, run_cycle
from .sources import collect
from .setup_data import collect_setup_data
from .storage import Store


def main(argv=None):
    parser = argparse.ArgumentParser(description='Tokn Market Watch: isolated market alerts')
    parser.add_argument('--config', help='non-secret JSON configuration')
    parser.add_argument('--database', help='explicit archive path; overrides configuration')
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run', help='collect one cycle, archive and preview; sending is opt-in')
    run.add_argument('--send', action='store_true', help='also requires MARKET_WATCH_ENABLE_DELIVERY=1')
    sub.add_parser('status', help='show source health and redacted delivery status')
    sub.add_parser('check', help='exit nonzero if sources, collector cadence or delivery are unhealthy')
    export = sub.add_parser('export', help='export archived events as JSON; may contain paid content')
    export.add_argument('--limit', type=int, default=100)
    outcomes = sub.add_parser('outcomes', help='read-only historical alert mark changes, not trading returns')
    outcomes.add_argument('--days', type=int, default=30)
    outcomes.add_argument('--details', action='store_true', help='include every included alert and its horizon samples')
    setups = sub.add_parser('setups', help='read-only setup history and source coverage; not trading performance')
    setups.add_argument('--limit', type=int, default=20)
    backup = sub.add_parser('backup', help='consistent SQLite backup; destination must not exist')
    backup.add_argument('destination')
    resolve = sub.add_parser('resolve-delivery', help='resolve an uncertain send after checking the channel')
    resolve.add_argument('id', type=int)
    resolve.add_argument('--action', choices=['sent', 'discarded'], required=True)
    resolve.add_argument('--remote-id')
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        config = load_config(args.config)
        db = args.database or os.environ.get('MARKET_WATCH_DATABASE') or config.database
        config = replace(config, database=db)
        routes = routes_from_env(os.environ) if args.command == 'run' else []
        if args.command == 'run' and args.send:
            if os.environ.get('MARKET_WATCH_ENABLE_DELIVERY') != '1':
                raise ValueError('sending requires MARKET_WATCH_ENABLE_DELIVERY=1')
            if not any(r.audience == 'paid' for r in routes):
                raise ValueError('configure at least one paid destination before sending')
        if args.command == 'setups' and not 1 <= args.limit <= 100:
            raise ValueError('setup limit must be between 1 and 100')
        if args.command == 'export' and not 1 <= args.limit <= 10000:
            raise ValueError('export limit must be between 1 and 10000')
        readonly = args.command in {"status", "check", "export", "backup", "outcomes", "setups"}
        if readonly and not Path(db).is_file():
            raise ValueError("archive not initialized; collect a cycle first")
        with (nullcontext() if readonly else process_lock(db)):
            store = Store(db, readonly=readonly)
            try:
                client = JsonClient(config.request_timeout_seconds)
                if args.command == 'run':
                    observations, errors = collect(config, client)
                    setup_batch = collect_setup_data(config, client, store)
                    output = run_cycle(config, store, observations, errors, routes, time.time(), setup_batch)
                    output['sending_enabled'] = args.send
                    if args.send:
                        output['delivery'] = dispatch(store, routes, client)
                    print(json.dumps(output, indent=2, allow_nan=False))
                    setup_issues = output['setups']['health'].get('primary_issues', {})
                    return 0 if not output['issues'] and not setup_issues else 2
                if args.command == 'outcomes':
                    with store.db:
                        store.db.execute('BEGIN')
                        output = outcome_report(store, time.time(), args.days, args.details)
                elif args.command == 'setups':
                    output = store.setup_status(args.limit)
                elif args.command == 'export':
                    output = store.export_events(args.limit)
                elif args.command == 'resolve-delivery':
                    store.resolve_delivery(args.id, args.action, args.remote_id, time.time())
                    output = {'resolved': args.id, 'status': args.action}
                elif args.command == 'backup':
                    path = Path(args.destination)
                    # Exclusive create prevents accidental overwrite of an existing backup.
                    with path.open('xb'):
                        pass
                    with sqlite3.connect(str(path)) as dest:
                        store.db.backup(dest)
                    output = {'backup_created': True}
                else:
                    output = store.status(time.time())
                print(json.dumps(output, indent=2, allow_nan=False))
                if args.command == 'check':
                    age = output['cycle_age_seconds']
                    setup_health = output['setups']['health']
                    setup_bad = config.setup_enabled and (
                        setup_health.get('status') not in {'ready'}
                        or time.time() - setup_health.get('checked_at', 0) > 600)
                    bad = output['source_issues'] or output['unresolved'] or age is None or age > config.max_age_seconds or setup_bad
                    return 2 if bad else 0
            finally:
                store.close()
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        # Exceptions from external services never contain their response bodies or tokens.
        # Only known validation/runtime messages are safe to print.
        message = str(exc) if type(exc) in (ValueError, RuntimeError) else 'local configuration or storage error'
        print(json.dumps({'error': message}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
