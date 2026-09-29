import contextlib
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_watch.__main__ import main
from market_watch.config import Config, load_config
from market_watch.delivery import Route, dispatch, routes_from_env, send
from market_watch.engine import assess, market_alerts, summaries
from market_watch.http import RemoteError
from market_watch.models import Event, Observation
from market_watch.service import process_lock, run_cycle
from market_watch.sources import collect, parse_hyperliquid, parse_okx
from market_watch.storage import Store


NOW = datetime(2026, 9, 28, 12, 2, tzinfo=timezone.utc).timestamp()
DISCORD = 'https://discord.com/api/webhooks/123/test-only-token'


def observation(venue='hyperliquid', asset='BTC', now=NOW, price=100, oi=1000, bps=1):
    interval = 1 if venue == 'hyperliquid' else 8
    return Observation(venue, asset, asset if venue == 'hyperliquid' else asset + '-USDT-SWAP',
                       now, now, 'receipt' if venue == 'hyperliquid' else 'exchange',
                       price, oi, price * oi, bps / 10000 * interval / 8, interval)


def okx_payloads(interval=8, rate='0.0001'):
    inst = 'BTC-USDT-SWAP'
    def wrap(row):
        return {'code': '0', 'data': [{'instId': inst, 'ts': str(int(NOW * 1000)), **row}]}
    return (
        wrap({'fundingRate': rate, 'fundingTime': str(int((NOW + 3600) * 1000)),
              'nextFundingTime': str(int((NOW + 3600 + interval * 3600) * 1000))}),
        wrap({'oiCcy': '1000', 'oiUsd': '100000'}),
        wrap({'markPx': '100'}),
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, url, payload=None):
        self.calls.append((url, payload))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class SourceTests(unittest.TestCase):
    def test_funding_common_basis_across_different_intervals(self):
        hl, errors = parse_hyperliquid([{'universe': [{'name': 'BTC'}]}, [
            {'markPx': '100', 'openInterest': '1000', 'funding': '0.0000125'}]], ['BTC'], NOW)
        okx = parse_okx('BTC', *okx_payloads(), NOW)
        self.assertFalse(errors)
        self.assertAlmostEqual(hl[0].funding_bps_8h, okx.funding_bps_8h)
        self.assertEqual(hl[0].oi_usd, 100000)
        self.assertEqual(hl[0].timestamp_basis, 'receipt')

    def test_okx_dynamic_interval(self):
        self.assertAlmostEqual(parse_okx('BTC', *okx_payloads(4), NOW).funding_bps_8h, 2)

    def test_zero_funding_is_valid_and_not_replaced_with_prediction(self):
        f, oi, mark = okx_payloads(rate='0')
        f['data'][0]['nextFundingRate'] = '0.25'
        self.assertEqual(parse_okx('BTC', f, oi, mark, NOW).funding_rate, 0)

    def test_missing_unknown_interval_rejected(self):
        with self.assertRaises(ValueError):
            parse_okx('BTC', *okx_payloads(3), NOW)

    def test_future_component_timestamp_rejected(self):
        f, oi, mark = okx_payloads()
        mark['data'][0]['ts'] = str(int((NOW + 1000) * 1000))
        with self.assertRaises(ValueError):
            parse_okx('BTC', f, oi, mark, NOW)

    def test_oldest_component_controls_freshness(self):
        f, oi, mark = okx_payloads()
        oi['data'][0]['ts'] = str(int((NOW - 900) * 1000))
        row = parse_okx('BTC', f, oi, mark, NOW)
        self.assertFalse(row.fresh(NOW, 180))

    def test_nonfinite_zero_and_missing_values_rejected(self):
        for rate in ('NaN', 'Infinity', ''):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                parse_okx('BTC', *okx_payloads(rate=rate), NOW)
        with self.assertRaises(ValueError):
            observation(price=0)

    def test_hyperliquid_missing_asset_is_partial_failure(self):
        rows, errors = parse_hyperliquid([{'universe': [{'name': 'BTC'}]}, [
            {'markPx': '100', 'openInterest': '1000', 'funding': '0'}]], ['BTC', 'ETH'], NOW)
        self.assertEqual(len(rows), 1)
        self.assertIn('hyperliquid:ETH', errors)

    def test_hyperliquid_array_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            parse_hyperliquid([{'universe': []}, [{}]], ['BTC'], NOW)

    def test_source_failure_is_redacted(self):
        cfg = Config(assets=('BTC',), venues=('hyperliquid',), minimum_venues=1)
        rows, errors = collect(cfg, FakeClient([RemoteError('http_429')]), clock=lambda: NOW)
        self.assertFalse(rows)
        self.assertEqual(errors, {'hyperliquid:BTC': 'http_429'})


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'state.sqlite3')
        self.store = Store(self.path)
        self.cfg = Config(assets=('BTC',), database=self.path, summary_hours=(), free_summary_hour=0)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def add_history(self, now=NOW - 900, price=100, oi=1000):
        with self.store.db:
            self.store.add_observations([observation(v, now=now, price=price, oi=oi) for v in self.cfg.venues])

    def add_event(self, route, text='Example alert', now=NOW, expires=NOW + 600, key='test'):
        event = Event(key, 'alert', route.audience, now, expires, text, {'example': True})
        with self.store.db:
            return self.store.add_event(event, [route])


class EngineTests(StoreCase):
    def test_warmup_never_invents_price_change(self):
        rows = [observation(v) for v in self.cfg.venues]
        self.assertFalse(market_alerts(self.cfg, self.store, rows, NOW))

    def test_confirmed_price_and_oi_alert_with_evidence(self):
        self.add_history()
        rows = [observation(v, price=102, oi=1040) for v in self.cfg.venues]
        events = market_alerts(self.cfg, self.store, rows, NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].evidence['rule'], 'price_oi_up')
        self.assertEqual(len(events[0].evidence['comparisons']), 2)
        self.assertIn('does not identify', events[0].text)

    def test_price_revaluation_does_not_fake_oi_increase(self):
        self.add_history()
        rows = [observation(v, price=105, oi=1000) for v in self.cfg.venues]
        self.assertFalse(market_alerts(self.cfg, self.store, rows, NOW))

    def test_opposing_venues_suppress_directional_alert(self):
        self.add_history()
        rows = [observation('hyperliquid', price=101, oi=1040), observation('okx', price=99, oi=1040)]
        self.assertFalse(market_alerts(self.cfg, self.store, rows, NOW))

    def test_stale_and_missing_source_fail_closed(self):
        rows = [observation('hyperliquid'), observation('okx', now=NOW-1000)]
        accepted, errors = assess(self.cfg, rows, {}, NOW)
        self.assertEqual(len(accepted), 1)
        self.assertIn('okx:BTC', errors)
        self.assertFalse(market_alerts(self.cfg, self.store, accepted, NOW))

    def test_duplicate_source_cannot_count_as_confirmation(self):
        accepted, errors = assess(self.cfg, [observation(), observation()], {}, NOW)
        self.assertFalse(accepted)
        self.assertEqual(errors['hyperliquid:BTC'], 'duplicate_source_measurement')

    def test_inconsistent_prices_are_quarantined(self):
        accepted, errors = assess(self.cfg, [observation(), observation('okx', price=110)], {}, NOW)
        self.assertFalse(accepted)
        self.assertIn('cross_venue:BTC', errors)

    def test_no_lookahead_and_no_distant_baseline(self):
        self.add_history(NOW + 1)
        self.add_history(NOW - 3600)
        self.assertIsNone(self.store.baseline(observation(), 900, 180))

    def test_cooldown_survives_restart(self):
        rows = [observation(v, bps=4) for v in self.cfg.venues]
        first = run_cycle(self.cfg, self.store, rows, {}, [], NOW)
        self.assertEqual(len([e for e in first['events'] if e['kind']=='alert']), 1)
        self.store.close()
        self.store = Store(self.path)
        second = run_cycle(self.cfg, self.store, rows, {}, [], NOW + 60)
        self.assertFalse(second['events'])

    def test_hourly_alert_budget(self):
        cfg = replace(self.cfg, max_alerts_per_hour=1)
        rows = [observation('hyperliquid', bps=4), observation('okx', bps=7)]
        self.assertEqual(len(market_alerts(cfg, self.store, rows, NOW)), 1)

    def test_free_summary_does_not_contain_paid_asset_measurements(self):
        cfg = replace(self.cfg, assets=('BTC','ETH','SOL'), summary_hours=(8,), free_summary_hour=8)
        rows = [observation(v, asset=a) for v in cfg.venues for a in cfg.assets]
        events = summaries(cfg, self.store, rows, {}, NOW)
        free = next(e for e in events if e.audience == 'free')
        self.assertEqual({o['asset'] for o in free.evidence['observations']}, {'BTC'})
        self.assertNotIn('ETH:', free.text)
        self.assertNotIn('SOL:', free.text)

    def test_summary_deduplication_and_no_late_catchup(self):
        cfg = replace(self.cfg, summary_hours=(8,), free_summary_hour=8)
        rows = [observation(v) for v in cfg.venues]
        run_cycle(cfg, self.store, rows, {}, [], NOW)
        self.assertFalse(summaries(cfg, self.store, rows, {}, NOW + 60))
        self.assertFalse(summaries(cfg, self.store, rows, {}, NOW + 20*60))

    def test_health_degradation_and_recovery_are_archived(self):
        a = run_cycle(self.cfg, self.store, [], {}, [], NOW)
        self.assertEqual(a['events'][0]['kind'], 'health')
        b = run_cycle(self.cfg, self.store, [observation(v) for v in self.cfg.venues], {}, [], NOW + 60)
        self.assertIn('recovered', b['events'][0]['text'])

    def test_archive_rolls_back_partial_cycle(self):
        with patch.object(self.store, 'record_cycle', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                run_cycle(self.cfg, self.store, [observation(v, bps=4) for v in self.cfg.venues], {}, [], NOW)
        self.assertEqual(self.store.status(NOW)['events'], 0)
        self.assertEqual(self.store.status(NOW)['observations'], 0)

    def test_overlapping_processes_cannot_both_publish(self):
        with process_lock(self.path), self.assertRaises(RuntimeError):
            with process_lock(self.path):
                pass


class DeliveryTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.route = Route('discord', 'paid', DISCORD)

    def test_audience_destinations_must_differ(self):
        with self.assertRaises(ValueError):
            routes_from_env({'MARKET_WATCH_DISCORD_PAID_WEBHOOK': DISCORD, 'MARKET_WATCH_DISCORD_FREE_WEBHOOK': DISCORD})

    def test_rejects_arbitrary_webhook_host(self):
        with self.assertRaises(ValueError):
            routes_from_env({'MARKET_WATCH_DISCORD_PAID_WEBHOOK': 'https://example.com/api/webhooks/123/token'})

    def test_discord_receipt_mentions_and_no_repeat(self):
        self.add_event(self.route)
        client = FakeClient([{'id': 'receipt-123'}])
        self.assertEqual(dispatch(self.store, [self.route], client, lambda: NOW)['sent'], 1)
        self.assertEqual(client.calls[0][1]['allowed_mentions'], {'parse': []})
        self.assertTrue(client.calls[0][0].endswith('?wait=true'))
        dispatch(self.store, [self.route], client, lambda: NOW + 10)
        self.assertEqual(len(client.calls), 1)

    def test_telegram_receipt_and_content_protection(self):
        route = Route('telegram', 'paid', 'https://api.telegram.org/bot123:test/sendMessage', '-123')
        client = FakeClient([{'ok': True, 'result': {'message_id': 7}}])
        self.assertEqual(send(route, 'Message', client), '7')
        self.assertTrue(client.calls[0][1]['protect_content'])
        self.assertNotIn('parse_mode', client.calls[0][1])

    def test_ambiguous_timeout_quarantined_without_blind_retry(self):
        self.add_event(self.route)
        client = FakeClient([RemoteError('network_failure', ambiguous=True)])
        dispatch(self.store, [self.route], client, lambda: NOW)
        dispatch(self.store, [self.route], client, lambda: NOW + 60)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(self.store.status(NOW)['deliveries']['unknown'], 1)

    def test_crash_in_flight_is_quarantined(self):
        self.add_event(self.route)
        self.store.delivery_state(1, 'sending', NOW)
        client = FakeClient([])
        dispatch(self.store, [self.route], client, lambda: NOW + 10)
        self.assertEqual(self.store.status(NOW)['deliveries']['unknown'], 1)
        self.assertFalse(client.calls)

    def test_rate_limit_blocks_entire_route_until_retry(self):
        self.add_event(self.route, key='one')
        self.add_event(self.route, key='two')
        client = FakeClient([RemoteError('http_429', retry_after=60), {'id': '1'}, {'id': '2'}])
        dispatch(self.store, [self.route], client, lambda: NOW)
        dispatch(self.store, [self.route], client, lambda: NOW + 30)
        self.assertEqual(len(client.calls), 1)
        dispatch(self.store, [self.route], client, lambda: NOW + 61)
        self.assertEqual(self.store.status(NOW)['deliveries']['sent'], 2)

    def test_expired_outbox_never_sends_old_alert(self):
        self.add_event(self.route, expires=NOW + 10)
        client = FakeClient([])
        dispatch(self.store, [self.route], client, lambda: NOW + 11)
        self.assertFalse(client.calls)
        self.assertEqual(self.store.status(NOW)['deliveries']['expired'], 1)

    def test_destination_rotation_does_not_reroute_old_messages(self):
        self.add_event(self.route)
        new_route = Route('discord', 'paid', 'https://discord.com/api/webhooks/456/new-token')
        client = FakeClient([])
        dispatch(self.store, [new_route], client, lambda: NOW)
        self.assertFalse(client.calls)
        self.assertEqual(self.store.status(NOW)['unresolved'][0]['error'], 'destination_changed')

    def test_operator_can_resolve_ambiguous_send(self):
        self.add_event(self.route)
        self.store.delivery_state(1, 'unknown', NOW)
        self.store.resolve_delivery(1, 'sent', 'verified-id', NOW + 60)
        self.assertFalse(self.store.status(NOW)['unresolved'])

    def test_tokens_not_stored_in_archive_or_route_repr(self):
        self.add_event(self.route)
        self.assertNotIn('test-only-token', repr(self.route))
        contents = '\n'.join(self.store.db.iterdump())
        self.assertNotIn('test-only-token', contents)


class CLITests(unittest.TestCase):
    def test_default_run_never_calls_delivery(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), \
                patch('market_watch.__main__.collect', return_value=([], {})), \
                patch('market_watch.__main__.dispatch') as sender, contextlib.redirect_stdout(io.StringIO()):
            result = main(['--database', tmp + '/db.sqlite3', 'run'])
            self.assertEqual(result, 2)
            sender.assert_not_called()

    def test_send_requires_explicit_environment_gate(self):
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()), \
                patch('market_watch.__main__.collect') as collector:
            self.assertEqual(main(['run', '--send']), 1)
            collector.assert_not_called()

    def test_backup_is_consistent_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            initialized = Store(tmp + '/db.sqlite3')
            initialized.close()
            base = ['--database', tmp + '/db.sqlite3']
            target = tmp + '/backup.sqlite3'
            self.assertEqual(main(base + ['backup', target]), 0)
            self.assertEqual(main(base + ['backup', target]), 1)
            self.assertTrue(Path(target).stat().st_size > 0)

    def test_configuration_rejects_unknown_and_nonfinite_settings(self):
        with self.assertRaises(ValueError):
            Config(price_change_pct=math.nan)
        with self.assertRaises(ValueError):
            Config(minimum_venues=3)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'config.json'
            p.write_text(json.dumps({'misspelled_setting': True}))
            with self.assertRaises(ValueError):
                load_config(p)


if __name__ == '__main__':
    unittest.main()
