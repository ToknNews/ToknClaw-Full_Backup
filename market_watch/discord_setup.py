"""Operator-only Discord setup and a single, receipt-tracked connection test."""

import argparse
import getpass
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
import warnings

from .delivery import routes_from_env, send
from .http import JsonClient, RemoteError
from .service import process_lock
from .storage import Store


ENVIRONMENT = Path('/etc/tokn-market-watch.env')
TEST_DATABASE = Path('/var/lib/tokn-market-watch-setup/discord-test.sqlite3')
KEYS = (
    'MARKET_WATCH_DATABASE', 'MARKET_WATCH_ENABLE_DELIVERY',
    'MARKET_WATCH_DELIVERY_ARGS', 'MARKET_WATCH_DISCORD_PAID_WEBHOOK',
    'MARKET_WATCH_DISCORD_FREE_WEBHOOK', 'MARKET_WATCH_TELEGRAM_BOT_TOKEN',
    'MARKET_WATCH_TELEGRAM_PAID_CHAT_ID', 'MARKET_WATCH_TELEGRAM_FREE_CHAT_ID',
)
TEST_MESSAGE = (
    'TOKN MARKET WATCH | CONNECTION TEST\n'
    'The server reached this Discord channel. This is a setup test, not a market alert.\n'
    'Scheduled market publishing is still disabled.'
)


def read_environment(path, *, require_collection_only=True):
    """Read our unquoted environment schema without executing shell content."""
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'r') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ValueError('environment file must be a private regular file (mode 600)')
        original = handle.read()
    values = {}
    for line in original.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if (not separator or key not in KEYS or key in values
                or any(c.isspace() or c in "'\"`$\\\x00" for c in value)):
            raise ValueError('unsupported environment format; keep the supplied unquoted schema')
        values[key] = value
    if set(values) != set(KEYS):
        raise ValueError('environment file is missing expected settings')
    if (values['MARKET_WATCH_ENABLE_DELIVERY'] not in {'0', '1'}
            or values['MARKET_WATCH_DELIVERY_ARGS'] not in {'', '--send'}):
        raise ValueError('unsupported publishing switch values')
    if require_collection_only and (values['MARKET_WATCH_ENABLE_DELIVERY'] != '0'
            or values['MARKET_WATCH_DELIVERY_ARGS']):
        raise ValueError('setup requires collection-only mode: delivery=0 and empty delivery args')
    return original, values


def replace_environment(path, original, values, reason):
    """Write a complete private replacement, retaining the previous file."""
    replacement = '# Private runtime settings. Do not commit this file.\n'
    replacement += '\n'.join(key + '=' + values[key] for key in KEYS) + '\n'
    # Preserve the complete old file before atomically replacing it.
    backup_fd, backup_name = tempfile.mkstemp(prefix=path.name + '.before-' + reason + '-', dir=path.parent)
    with os.fdopen(backup_fd, 'w') as backup:
        backup.write(original)
        backup.flush()
        os.fsync(backup.fileno())
    new_fd, new_name = tempfile.mkstemp(prefix=path.name + '.new-', dir=path.parent)
    try:
        with os.fdopen(new_fd, 'w') as replacement_file:
            replacement_file.write(replacement)
            replacement_file.flush()
            os.fsync(replacement_file.fileno())
        os.replace(new_name, path)
    finally:
        if os.path.exists(new_name):
            os.unlink(new_name)
    return backup_name


def configure(path, webhook):
    original, values = read_environment(path)
    webhook = webhook.strip()
    if any(c.isspace() or ord(c) < 32 for c in webhook):
        raise ValueError('webhook must be a single URL without embedded whitespace')
    values['MARKET_WATCH_DISCORD_PAID_WEBHOOK'] = webhook
    routes = routes_from_env(values)
    if not any(r.platform == 'discord' and r.audience == 'paid' for r in routes):
        raise ValueError('a private test-channel Discord webhook is required')
    backup = replace_environment(path, original, values, 'discord')
    return {'configured': True, 'scheduled_publishing': False, 'backup': backup}


def set_publishing(path, database, *, enabled):
    """Explicitly activate only a tested Discord paid route, or pause publishing."""
    original, values = read_environment(path, require_collection_only=False)
    if enabled:
        routes = routes_from_env(values)
        if len(routes) != 1 or routes[0].platform != 'discord' or routes[0].audience != 'paid':
            raise ValueError('enable requires exactly one private Discord paid/test route')
        if not database.is_file():
            raise ValueError('send and verify the private-channel connection test first')
        store = Store(database, readonly=True)
        try:
            receipt = store.get_meta('discord-connection-test:' + routes[0].name)
        finally:
            store.close()
        if not receipt or receipt.get('status') != 'sent' or not receipt.get('message_id'):
            raise ValueError('this webhook has no successful connection-test receipt')
    flag, arguments = ('1', '--send') if enabled else ('0', '')
    if values['MARKET_WATCH_ENABLE_DELIVERY'] == flag and values['MARKET_WATCH_DELIVERY_ARGS'] == arguments:
        return {'scheduled_publishing': enabled, 'already_configured': True}
    values['MARKET_WATCH_ENABLE_DELIVERY'] = flag
    values['MARKET_WATCH_DELIVERY_ARGS'] = arguments
    backup = replace_environment(path, original, values, 'enable' if enabled else 'disable')
    return {'scheduled_publishing': enabled, 'backup': backup}


def connection_test(route, database, client, clock=time.time):
    """Persist intent before POST; never blindly repeat a successful/uncertain send."""
    with process_lock(database):
        store = Store(database)
        try:
            key = 'discord-connection-test:' + route.name
            previous = store.get_meta(key)
            if previous:
                if previous['status'] == 'sent':
                    return {**previous, 'already_sent': True}
                if previous['status'] in {'sending', 'unknown'}:
                    return {'status': 'unknown', 'check_channel_before_retry': True}
                if clock() < previous.get('retry_at', 0):
                    return {'status': 'rate_limited', 'retry_at': previous['retry_at']}
            with store.db:
                store.set_meta(key, {'status': 'sending', 'attempted_at': clock()})
            try:
                receipt = send(route, TEST_MESSAGE, client)
                result = {'status': 'sent', 'message_id': receipt, 'already_sent': False}
            except RemoteError as exc:
                result = {'status': 'unknown' if exc.ambiguous else 'failed', 'error': exc.code}
                if exc.ambiguous:
                    result['check_channel_before_retry'] = True
                if exc.code == 'http_429':
                    try:
                        delay = max(1, min(86400, float(exc.retry_after)))
                    except (ValueError, TypeError):
                        delay = 60
                    result['retry_at'] = clock() + delay
            with store.db:
                store.set_meta(key, result)
            return result
        finally:
            store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('configure', help='save a hidden webhook input; keep scheduled publishing disabled')
    test = sub.add_parser('test', help='preview or explicitly send one labeled connection test')
    test.add_argument('--send', action='store_true', help='send to the configured private test channel')
    sub.add_parser('enable', help='enable scheduled messages after verifying the tested private channel')
    sub.add_parser('disable', help='disable future scheduled publishing; preserve data collection')
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        print(json.dumps({'error': 'run this operator command with sudo'}))
        return 1
    os.umask(0o077)
    try:
        if args.command == 'configure':
            read_environment(ENVIRONMENT)
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                webhook = getpass.getpass('Paste the PRIVATE TEST CHANNEL webhook URL (hidden): ')
            output = configure(ENVIRONMENT, webhook)
        elif args.command in {'enable', 'disable'}:
            output = set_publishing(ENVIRONMENT, TEST_DATABASE, enabled=args.command == 'enable')
        else:
            _, values = read_environment(ENVIRONMENT)
            routes = [r for r in routes_from_env(values) if r.platform == 'discord' and r.audience == 'paid']
            if len(routes) != 1:
                raise ValueError('configure the private test-channel webhook first')
            if not args.send:
                output = {'sending_enabled': False, 'preview': TEST_MESSAGE}
            else:
                output = connection_test(routes[0], TEST_DATABASE, JsonClient())
        print(json.dumps(output, indent=2))
        return 0 if output.get('status', 'sent') == 'sent' else 2
    except (OSError, ValueError, RuntimeError, sqlite3.Error, EOFError,
            KeyboardInterrupt, getpass.GetPassWarning):
        # No URLs, file contents, traceback, or third-party response bodies.
        print(json.dumps({'error': 'setup failed; verify private config permissions, publishing switches, route format and test receipt'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
