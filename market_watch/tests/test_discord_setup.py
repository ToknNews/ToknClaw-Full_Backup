"""Setup checks never use real credentials or make external requests."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_watch import discord_setup
from market_watch.delivery import routes_from_env
from market_watch.http import RemoteError
from market_watch.storage import Store


WEBHOOK = 'https://discord.com/api/webhooks/123456/test-only-token'


class Client:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, url, payload):
        self.calls.append((url, payload))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class DiscordSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.env'
        self.original = (Path(discord_setup.__file__).parent / 'market-watch.env.example').read_text()
        self.path.write_text(self.original)
        self.path.chmod(0o600)
        self.database = Path(self.temp.name) / 'setup.sqlite3'
        self.route = routes_from_env({'MARKET_WATCH_DISCORD_PAID_WEBHOOK': WEBHOOK})[0]
        self.old_umask = os.umask(0o077)
        self.addCleanup(os.umask, self.old_umask)

    def test_configure_preserves_settings_and_private_backup(self):
        result = discord_setup.configure(self.path, WEBHOOK)
        _, values = discord_setup.read_environment(self.path)
        self.assertEqual(values['MARKET_WATCH_DISCORD_PAID_WEBHOOK'], WEBHOOK)
        self.assertEqual(values['MARKET_WATCH_ENABLE_DELIVERY'], '0')
        self.assertEqual(values['MARKET_WATCH_DELIVERY_ARGS'], '')
        self.assertEqual(values['MARKET_WATCH_DATABASE'], '/var/lib/tokn-market-watch/state.sqlite3')
        backup = Path(result['backup'])
        self.assertEqual(backup.read_text(), self.original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_invalid_destination_does_not_change_configuration(self):
        for webhook in ('', 'https://example.com/api/webhooks/123/token', WEBHOOK + '\nfoo'):
            with self.subTest(webhook=webhook), self.assertRaises(ValueError):
                discord_setup.configure(self.path, webhook)
            self.assertEqual(self.path.read_text(), self.original)

    def test_active_publisher_is_not_reconfigured(self):
        for setting in ('MARKET_WATCH_ENABLE_DELIVERY=1', 'MARKET_WATCH_DELIVERY_ARGS=--send'):
            key = setting.split('=')[0]
            old = key + ('=0' if key.endswith('ENABLE_DELIVERY') else '=')
            updated = self.original.replace(old, setting)
            self.path.write_text(updated)
            with self.assertRaises(ValueError):
                discord_setup.configure(self.path, WEBHOOK)
            self.assertEqual(self.path.read_text(), updated)

    def test_environment_rejects_shell_content_and_duplicate_keys(self):
        for line in ('UNKNOWN=secret', 'MARKET_WATCH_DATABASE=$(anything)', 'MARKET_WATCH_DATABASE=/other'):
            self.path.write_text(self.original + '\n' + line + '\n')
            with self.assertRaises(ValueError):
                discord_setup.read_environment(self.path)

    def test_environment_must_be_private_and_not_symlinked(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            discord_setup.read_environment(self.path)
        self.path.chmod(0o600)
        link = self.path.parent / 'linked.env'
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            discord_setup.read_environment(link)

    def test_preview_has_no_network_or_receipt_database_side_effect(self):
        discord_setup.configure(self.path, WEBHOOK)
        with patch.object(discord_setup, 'ENVIRONMENT', self.path), \
                patch.object(discord_setup.os, 'geteuid', return_value=0), \
                patch.object(discord_setup, 'connection_test') as send_test, \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(discord_setup.main(['test']), 0)
        send_test.assert_not_called()
        self.assertFalse(self.database.exists())
        self.assertFalse(json.loads(output.getvalue())['sending_enabled'])

    def test_success_stores_receipt_and_does_not_repeat(self):
        client = Client({'id': 'message-123'})
        result = discord_setup.connection_test(self.route, self.database, client, lambda: 100)
        self.assertEqual(result['status'], 'sent')
        self.assertEqual(result['message_id'], 'message-123')
        repeated = discord_setup.connection_test(self.route, self.database, client, lambda: 101)
        self.assertTrue(repeated['already_sent'])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][1]['allowed_mentions'], {'parse': []})
        self.assertIn('CONNECTION TEST', client.calls[0][1]['content'])
        store = Store(self.database)
        try:
            stored = json.dumps([tuple(row) for row in store.db.execute('SELECT key,value FROM metadata')])
            self.assertNotIn('test-only-token', stored)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 0)
        finally:
            store.close()

    def test_uncertain_response_never_automatically_reposts(self):
        client = Client(RemoteError('network_failure', ambiguous=True))
        first = discord_setup.connection_test(self.route, self.database, client, lambda: 100)
        second = discord_setup.connection_test(self.route, self.database, client, lambda: 200)
        self.assertEqual(first['status'], 'unknown')
        self.assertTrue(second['check_channel_before_retry'])
        self.assertEqual(len(client.calls), 1)

    def test_interrupted_send_requires_channel_review(self):
        store = Store(self.database)
        try:
            with store.db:
                store.set_meta('discord-connection-test:' + self.route.name, {'status': 'sending'})
        finally:
            store.close()
        client = Client()
        result = discord_setup.connection_test(self.route, self.database, client)
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(client.calls)

    def test_rate_limit_persists_across_restarts(self):
        client = Client(RemoteError('http_429', retry_after=60), {'id': 'message-123'})
        discord_setup.connection_test(self.route, self.database, client, lambda: 100)
        waiting = discord_setup.connection_test(self.route, self.database, client, lambda: 120)
        self.assertEqual(waiting['status'], 'rate_limited')
        self.assertEqual(len(client.calls), 1)
        result = discord_setup.connection_test(self.route, self.database, client, lambda: 161)
        self.assertEqual(result['status'], 'sent')
        self.assertEqual(len(client.calls), 2)

    def test_hidden_input_failure_does_not_echo_secret(self):
        with patch.object(discord_setup, 'ENVIRONMENT', self.path), \
                patch.object(discord_setup.os, 'geteuid', return_value=0), \
                patch.object(discord_setup.getpass, 'getpass', return_value='https://example.com/SECRET'), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(discord_setup.main(['configure']), 1)
        self.assertNotIn('SECRET', output.getvalue())
        self.assertEqual(self.path.read_text(), self.original)


if __name__ == '__main__':
    unittest.main()
