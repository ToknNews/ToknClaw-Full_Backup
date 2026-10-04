import contextlib
from dataclasses import replace
from email.message import Message
import io
import tempfile
from pathlib import Path
from market_watch.__main__ import main
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from market_watch.delivery import dispatch, routes_from_env
from market_watch.engine import market_alerts, summaries
from market_watch.http import JsonClient, RemoteError
from market_watch.service import run_cycle
from market_watch.tests.test_market_watch import DISCORD, NOW, FakeClient, StoreCase, observation


class OutboxEdgeTests(StoreCase):
    def test_measurements_expire_at_source_freshness_boundary(self):
        rows = [observation(v, now=NOW-170, bps=4) for v in self.cfg.venues]
        event = market_alerts(self.cfg, self.store, rows, NOW)[0]
        self.assertEqual(event.expires_at, NOW + 10)

    def test_same_discord_webhook_with_api_version_is_rejected(self):
        with self.assertRaises(ValueError):
            routes_from_env({'MARKET_WATCH_DISCORD_PAID_WEBHOOK': DISCORD,
                'MARKET_WATCH_DISCORD_FREE_WEBHOOK': DISCORD.replace('/api/', '/api/v10/')})

    def test_paid_alerts_never_enqueued_to_free_route(self):
        routes = routes_from_env({'MARKET_WATCH_DISCORD_PAID_WEBHOOK': DISCORD,
            'MARKET_WATCH_DISCORD_FREE_WEBHOOK': 'https://discord.com/api/webhooks/456/free-token'})
        rows = [observation(v, bps=4) for v in self.cfg.venues]
        run_cycle(self.cfg, self.store, rows, {}, routes, NOW)
        deliveries = self.store.db.execute('SELECT route FROM deliveries').fetchall()
        self.assertEqual(len(deliveries), 1)
        self.assertIn(':paid:', deliveries[0]['route'])

    def test_missing_receipt_not_recorded_as_success(self):
        route = routes_from_env({'MARKET_WATCH_DISCORD_PAID_WEBHOOK': DISCORD})[0]
        self.add_event(route)
        dispatch(self.store, [route], FakeClient([{}]), lambda: NOW)
        self.assertEqual(self.store.status(NOW)['deliveries'], {'unknown': 1})

    def test_oversized_message_fails_without_truncation(self):
        route = routes_from_env({'MARKET_WATCH_DISCORD_PAID_WEBHOOK': DISCORD})[0]
        self.add_event(route, text='x'*2000)
        client = FakeClient([])
        dispatch(self.store, [route], client, lambda: NOW)
        self.assertFalse(client.calls)
        self.assertEqual(self.store.status(NOW)['unresolved'][0]['error'], 'message_too_long')

    def test_dst_repeated_hour_does_not_repeat_digest(self):
        from datetime import datetime, timezone
        cfg = replace(self.cfg, summary_hours=(1,), free_summary_hour=1)
        first = datetime(2026,11,1,5,2,tzinfo=timezone.utc).timestamp()
        second = datetime(2026,11,1,6,2,tzinfo=timezone.utc).timestamp()
        events = summaries(cfg, self.store, [], {}, first)
        with self.store.db:
            for event in events:
                self.store.add_event(event, [])
        self.assertFalse(summaries(cfg, self.store, [], {}, second))


class HTTPTests(unittest.TestCase):
    def test_health_check_does_not_create_uninitialized_archive(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()):
            path = str(Path(tmp) / "missing.sqlite3")
            self.assertEqual(main(["--database", path, "check"]), 1)
            self.assertFalse(Path(path).exists())

    def test_http_error_never_exposes_url_or_body(self):
        client = JsonClient()
        exc = HTTPError(DISCORD, 401, 'secret-body', {}, io.BytesIO(b'secret-body'))
        with patch.object(client.opener, 'open', side_effect=exc):
            with self.assertRaises(RemoteError) as error:
                client.call(DISCORD, {'content': 'test'})
        self.assertEqual(str(error.exception), 'http_401')

    def test_rate_limit_json_delay(self):
        client = JsonClient()
        exc = HTTPError(DISCORD, 429, '', {}, io.BytesIO(b'{"retry_after": 2.5}'))
        with patch.object(client.opener, 'open', side_effect=exc):
            with self.assertRaises(RemoteError) as error:
                client.call(DISCORD, {'content': 'test'})
        self.assertEqual(error.exception.retry_after, 2.5)

    def test_html_response_rejected_without_echoing_content(self):
        headers = Message()
        headers['Content-Type'] = 'text/html'
        response = io.BytesIO(b'<html>restricted or unavailable</html>')
        response.headers = headers
        client = JsonClient()
        with patch.object(client.opener, 'open', return_value=response):
            with self.assertRaises(RemoteError) as error:
                client.call('https://example.com')
        self.assertEqual(str(error.exception), 'unexpected_content_type')


if __name__ == '__main__':
    unittest.main()
