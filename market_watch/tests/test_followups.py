"""Replay lifecycle sequences locally; no real source or messaging requests."""

from dataclasses import replace
import json
from unittest.mock import patch

from market_watch.config import Config
from market_watch.delivery import Route, dispatch
from market_watch.presentation import validate_presentation
from market_watch.service import run_cycle
from market_watch.storage import Store
from test_market_watch import DISCORD, FakeClient, NOW, StoreCase, observation


class FollowupTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.cfg = replace(self.cfg, cooldown_minutes=240)
        self.route = Route('discord', 'paid', DISCORD)
        self.original = None

    def start(self, *, price=100, oi=1000, bps=4, delivered=True, routes=None, cfg=None):
        cfg = cfg or self.cfg
        self.add_history()
        rows = [observation(v, price=price, oi=oi, bps=bps) for v in cfg.venues]
        result = run_cycle(cfg, self.store, rows, {}, routes if routes is not None else [self.route], NOW)
        self.original = next(e['id'] for e in result['events'] if e['kind'] == 'alert')
        if delivered:
            dispatch(self.store, [self.route], FakeClient([{'id': 'original-receipt'}]), lambda: NOW)
        return self.original

    def cycle(self, offset, *, price=100, oi=1000, bps=4, missing=False, cfg=None, routes=None, rows=None):
        now = NOW + offset
        cfg = cfg or self.cfg
        self.add_history(now=now - 900)
        if rows is None:
            rows = [observation(v, now=now, price=price, oi=oi, bps=bps) for v in cfg.venues]
        if missing:
            rows = rows[:1]
        result = run_cycle(cfg, self.store, rows, {}, routes if routes is not None else [self.route], now)
        return [e for e in result['events'] if e['kind'] == 'followup']

    def track(self):
        return dict(self.store.db.execute('SELECT * FROM alert_watches WHERE original_id=?', (self.original,)).fetchone())

    def evidence(self, event):
        row = self.store.db.execute('SELECT evidence FROM events WHERE id=?', (event['id'],)).fetchone()
        return json.loads(row[0])

    def child_deliveries(self, event):
        return self.store.db.execute('SELECT * FROM deliveries WHERE event_id=?', (event['id'],)).fetchall()

    def test_first_holding_check_is_linked_and_unchanged_condition_is_quiet(self):
        self.start()
        self.assertFalse(self.cycle(299))
        update = self.cycle(300)[0]
        evidence = self.evidence(update)
        self.assertEqual(evidence['condition'], 'holding')
        self.assertEqual(evidence['original_id'], self.original)
        original_text = self.store.db.execute('SELECT text FROM events WHERE id=?', (self.original,)).fetchone()[0]
        self.assertIn(self.original, original_text)
        self.assertIn(self.original, update['text'])
        self.assertEqual(len(self.child_deliveries(update)), 1)
        self.assertFalse(self.cycle(600))
        self.assertEqual(self.track()['update_count'], 1)
        self.assertEqual(self.track()['last_checked_at'], NOW + 600)
        validate_presentation(evidence['presentation'])

    def test_fade_closes_watch_and_is_not_reopened_by_recovery(self):
        self.start()
        self.cycle(300)
        faded = self.cycle(600, bps=1)[0]
        self.assertEqual(self.evidence(faded)['closed_reason'], 'condition_faded')
        self.assertIn('CONDITION FADED', faded['text'])
        self.assertEqual(self.track()['state'], 'faded')
        self.assertEqual(self.track()['closed_at'], NOW + 600)
        self.assertFalse(self.cycle(900))

    def test_unavailable_is_not_a_fade_and_can_recover(self):
        self.start(price=12345)
        paused = self.cycle(300, price=12345, missing=True)[0]
        evidence = self.evidence(paused)
        self.assertEqual(evidence['condition'], 'unavailable')
        self.assertEqual(evidence['observations'], [])
        self.assertEqual(evidence['since_original'], [])
        self.assertNotIn('12,345', paused['text'])
        self.assertIsNone(self.track()['closed_at'])
        self.assertFalse(self.cycle(600, missing=True))
        recovered = self.cycle(900)[0]
        self.assertTrue(self.evidence(recovered)['recovered'])
        self.assertIn('COVERAGE BACK', recovered['text'])

    def test_partial_coverage_requires_original_cohort_even_if_minimum_is_one(self):
        cfg = replace(self.cfg, minimum_venues=1)
        self.start(cfg=cfg)
        update = self.cycle(300, cfg=cfg, missing=True)[0]
        self.assertEqual(self.evidence(update)['assessment'], 'coverage_unavailable')

    def test_rule_thresholds_and_schedule_are_frozen_at_original_alert(self):
        self.start()
        cfg = replace(self.cfg, funding_extreme_bps_8h=20, followup_check_minutes=10,
                      followup_horizon_minutes=120)
        first = self.cycle(300, cfg=cfg)[0]
        self.assertEqual(self.evidence(first)['condition'], 'holding')
        self.assertEqual(self.evidence(first)['config']['funding_extreme_bps_8h'], 3)
        self.assertEqual(self.track()['next_check_at'], NOW + 600)
        self.assertEqual(self.track()['horizon_at'], NOW + 3600)

    def test_update_cap_closes_watch_with_latest_condition(self):
        self.start()
        self.cycle(300)
        self.cycle(600, missing=True)
        self.cycle(900)
        final = self.cycle(1200, missing=True)[0]
        self.assertEqual(self.evidence(final)['closed_reason'], 'update_limit')
        self.assertEqual(self.track()['update_count'], 4)
        self.assertIn('WATCH ENDED', final['text'])
        self.assertFalse(self.cycle(1500))

    def test_horizon_emits_one_closing_update_and_preserves_actual_check_time(self):
        self.start()
        self.cycle(300)
        final = self.cycle(3660)[0]
        evidence = self.evidence(final)
        self.assertEqual(evidence['closed_reason'], 'horizon_elapsed')
        self.assertEqual(evidence['checked_at'], NOW + 3660)
        self.assertIn('+61.0m', final['text'])
        self.assertEqual(evidence['condition'], 'holding')
        self.assertEqual(self.track()['state'], 'expired')
        self.assertFalse(self.cycle(3720))

    def test_missed_horizon_archives_expiry_without_stale_catchup_delivery(self):
        self.start()
        final = self.cycle(7200)[0]
        evidence = self.evidence(final)
        self.assertEqual(evidence['closed_reason'], 'late_expiry')
        self.assertEqual(evidence['observations'], [])
        self.assertEqual(len(self.child_deliveries(final)), 0)
        self.assertIsNotNone(self.track()['closed_at'])

    def test_restart_and_same_cycle_retry_do_not_duplicate_updates(self):
        self.start()
        first = self.cycle(300)[0]
        self.store.close()
        self.store = Store(self.path)
        self.assertFalse(self.cycle(300))
        self.assertFalse(self.cycle(600))
        self.assertEqual(self.track()['update_count'], 1)
        self.assertEqual(len(self.child_deliveries(first)), 1)

    def test_cycle_failure_rolls_back_watch_update_event_and_outbox(self):
        self.start()
        before = self.store.status(NOW)
        with patch.object(self.store, 'record_cycle', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                self.cycle(300)
        self.assertEqual(self.track()['state'], 'watching')
        self.assertEqual(self.track()['update_count'], 0)
        self.assertEqual(self.store.status(NOW)['events'], before['events'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM alert_followups').fetchone()[0], 0)
        self.assertEqual(len(self.cycle(300)), 1)

    def test_new_watch_also_rolls_back_with_failed_original_cycle(self):
        with patch.object(self.store, 'record_cycle', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                self.start(delivered=False)
        self.assertEqual(self.store.watch_status()['active'], 0)
        self.assertEqual(self.store.status(NOW)['events'], 0)

    def test_only_confirmed_original_destination_receives_followup(self):
        telegram = Route('telegram', 'paid', 'https://api.telegram.org/bot123:test/sendMessage', '-123')
        free = Route('discord', 'free', 'https://discord.com/api/webhooks/456/public')
        self.start(delivered=False, routes=[self.route, telegram, free])
        for row in self.store.db.execute('SELECT id,route FROM deliveries').fetchall():
            if row['route'] == self.route.name:
                self.store.delivery_state(row['id'], 'sent', NOW, remote_id='receipt')
            else:
                self.store.delivery_state(row['id'], 'unknown', NOW, error='network_failure')
        update = self.cycle(300, routes=[self.route, telegram, free])[0]
        self.assertEqual([r['route'] for r in self.child_deliveries(update)], [self.route.name])

    def test_pending_or_unknown_parent_never_gets_orphan_update(self):
        self.start(delivered=False)
        update = self.cycle(300)[0]
        self.assertEqual(len(self.child_deliveries(update)), 0)
        self.store.delivery_state(1, 'unknown', NOW + 300, error='network_failure')
        final = self.cycle(600, bps=1)[0]
        self.assertEqual(len(self.child_deliveries(final)), 0)
        client = FakeClient([])
        dispatch(self.store, [self.route], client, lambda: NOW + 600)
        self.assertEqual(client.calls, [])

    def test_new_or_rotated_webhook_never_inherits_followup(self):
        self.start()
        other = Route('discord', 'paid', 'https://discord.com/api/webhooks/456/rotated')
        update = self.cycle(300, routes=[other])[0]
        self.assertEqual(len(self.child_deliveries(update)), 0)

    def test_new_state_expires_retryable_old_update_before_dispatch(self):
        self.start()
        holding = self.cycle(300)[0]
        old = self.child_deliveries(holding)[0]
        self.store.delivery_state(old['id'], 'pending', NOW + 300, error='http_429', delay=900)
        faded = self.cycle(600, bps=1)[0]
        old = self.child_deliveries(holding)[0]
        self.assertEqual(old['status'], 'expired')
        self.assertEqual(old['error'], 'superseded_followup')
        client = FakeClient([{'id': 'fade-receipt'}])
        dispatch(self.store, [self.route], client, lambda: NOW + 600)
        self.assertEqual(len(client.calls), 1)
        self.assertIn('CONDITION FADED', client.calls[0][1]['embeds'][0]['title'])
        self.assertEqual(self.child_deliveries(faded)[0]['status'], 'sent')

    def test_ambiguous_followup_remains_quarantined_when_condition_changes(self):
        self.start()
        holding = self.cycle(300)[0]
        old = self.child_deliveries(holding)[0]
        self.store.delivery_state(old['id'], 'unknown', NOW + 300, error='network_failure')
        self.cycle(600, bps=1)
        self.assertEqual(self.child_deliveries(holding)[0]['status'], 'unknown')

    def test_price_pattern_can_fade_while_mark_remains_above_original(self):
        self.start(price=102, oi=1040, bps=1)
        update = self.cycle(300, price=103, oi=1000, bps=1)[0]
        evidence = self.evidence(update)
        self.assertEqual(evidence['condition'], 'faded')
        self.assertGreater(evidence['since_original'][0]['price_pct'], 0)
        self.assertIn('Two different comparisons', update['text'])
        self.assertNotIn('profit', update['text'].lower())

    def test_missing_price_baseline_is_unavailable_not_faded(self):
        self.start(price=102, oi=1040, bps=1)
        rows = [observation(v, now=NOW + 300, price=103, oi=1080) for v in self.cfg.venues]
        result = run_cycle(self.cfg, self.store, rows, {}, [self.route], NOW + 300)
        update = next(e for e in result['events'] if e['kind'] == 'followup')
        self.assertEqual(self.evidence(update)['assessment'], 'baseline_unavailable')
        self.assertEqual(self.evidence(update)['condition'], 'unavailable')

    def test_stale_duplicate_mismatched_and_reused_readings_do_not_claim_persistence(self):
        self.start()
        scenarios = [
            [observation(v, now=NOW, bps=4) for v in self.cfg.venues],
            [observation(now=NOW + 600, bps=4)] * 2,
            [replace(observation(v, now=NOW + 900, bps=4), instrument='OTHER') for v in self.cfg.venues],
        ]
        for offset, rows in zip((300, 600, 900), scenarios):
            self.cycle(offset, rows=rows)
            self.assertEqual(self.track()['state'], 'unavailable')
            self.assertIsNone(self.track()['closed_at'])

    def test_fresh_but_reused_measurement_is_not_a_second_confirmation(self):
        cfg = replace(self.cfg, followup_check_minutes=1)
        self.start(cfg=cfg)
        rows = [observation(v, now=NOW, bps=4) for v in cfg.venues]
        update = self.cycle(60, cfg=cfg, rows=rows)[0]
        self.assertEqual(self.evidence(update)['assessment'], 'no_new_reading')

    def test_disabled_mode_closes_existing_watch_without_sending_and_starts_none(self):
        self.start()
        holding = self.cycle(300)[0]
        cfg = replace(self.cfg, followup_enabled=False)
        closed = self.cycle(360, cfg=cfg)[0]
        self.assertEqual(self.evidence(closed)['closed_reason'], 'disabled')
        self.assertEqual(len(self.child_deliveries(closed)), 0)
        self.assertEqual(self.child_deliveries(holding)[0]['status'], 'expired')
        self.assertEqual(self.store.watch_status()['active'], 0)
        self.assertFalse(self.cycle(600, cfg=self.cfg))

    def test_disabled_configuration_does_not_register_new_alerts(self):
        self.start(cfg=replace(self.cfg, followup_enabled=False))
        self.assertEqual(self.store.watch_status()['active'], 0)

    def test_legacy_archive_is_readable_then_migrates_without_retroactive_watches(self):
        self.start(cfg=replace(self.cfg, followup_enabled=False))
        with self.store.db:
            self.store.db.execute('DROP TABLE alert_followups')
            self.store.db.execute('DROP TABLE alert_watches')
            self.store.db.execute('PRAGMA user_version=1')
        self.store.close()
        legacy = Store(self.path, readonly=True)
        self.assertEqual(legacy.status(NOW)['events'], 1)
        self.assertEqual(legacy.watch_status()['active'], 0)
        self.assertEqual(legacy.db.execute('PRAGMA user_version').fetchone()[0], 1)
        legacy.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0], 2)
        self.assertEqual(self.store.status(NOW)['events'], 1)
        self.assertEqual(self.store.status(NOW)['deliveries']['sent'], 1)
        self.assertEqual(self.store.watch_status()['active'], 0)
        self.assertFalse(self.cycle(300))

    def test_negative_funding_holds_then_fades_without_price_history_dependency(self):
        self.start(bps=-4)
        held = self.cycle(300, bps=-4)[0]
        self.assertEqual(self.evidence(held)['rule'], 'negative_funding')
        self.assertEqual(self.evidence(held)['condition'], 'holding')
        faded = self.cycle(600, bps=-1)[0]
        self.assertEqual(self.evidence(faded)['condition'], 'faded')

    def test_funding_gap_is_rechecked_on_normalized_rates(self):
        rows = [observation('hyperliquid', bps=1), observation('okx', bps=5)]
        result = run_cycle(self.cfg, self.store, rows, {}, [self.route], NOW)
        self.original = next(e['id'] for e in result['events'] if e['kind'] == 'alert')
        dispatch(self.store, [self.route], FakeClient([{'id': 'original-receipt'}]), lambda: NOW)
        rows = [observation('hyperliquid', now=NOW + 300, bps=1),
                observation('okx', now=NOW + 300, bps=4)]
        held = self.cycle(300, rows=rows)[0]
        self.assertEqual(self.evidence(held)['rule'], 'funding_divergence')
        self.assertEqual(self.evidence(held)['condition'], 'holding')
        faded = self.cycle(600, bps=1)[0]
        self.assertEqual(self.evidence(faded)['condition'], 'faded')

    def test_downside_price_oi_condition_holds_then_fades(self):
        self.start(price=98, oi=1040, bps=1)
        held = self.cycle(300, price=97, oi=1080, bps=1)[0]
        self.assertEqual(self.evidence(held)['rule'], 'price_oi_down')
        self.assertEqual(self.evidence(held)['condition'], 'holding')
        faded = self.cycle(600, price=99.5, oi=1080, bps=1)[0]
        self.assertEqual(self.evidence(faded)['condition'], 'faded')

    def test_price_disagreement_cannot_be_reported_as_fade(self):
        self.start()
        rows = [observation('hyperliquid', now=NOW + 300, price=100, bps=1),
                observation('okx', now=NOW + 300, price=110, bps=1)]
        update = self.cycle(300, rows=rows)[0]
        self.assertEqual(self.evidence(update)['condition'], 'unavailable')
        self.assertEqual(self.evidence(update)['since_original'], [])

    def test_minute_replay_delivers_original_then_holding_then_fade(self):
        client = FakeClient([{'id': 'original'}, {'id': 'holding'}, {'id': 'faded'}])
        for minute in range(76):
            now = NOW + minute * 60
            movement = min(minute, 25)
            rows = [observation(v, now=now, price=100 * 1.001 ** movement,
                                oi=1000 * 1.003 ** movement, bps=1) for v in self.cfg.venues]
            run_cycle(self.cfg, self.store, rows, {}, [self.route], now)
            dispatch(self.store, [self.route], client, lambda: now)
        titles = [payload['embeds'][0]['title'] for _, payload in client.calls]
        self.assertEqual(titles, ['BTC · PRICE ↑ / OI ↑', 'BTC · CONDITION HOLDS', 'BTC · CONDITION FADED'])
        self.assertEqual(self.store.watch_status(), {'active': 0, 'closed': 1, 'states': {'faded': 1}})
        self.assertEqual(self.store.status(now)['deliveries'], {'sent': 3})
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.store.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_first_funding_followup_compares_direction_to_original_alert(self):
        self.cfg = replace(self.cfg, max_alerts_per_hour=1)
        self.start()
        changed = self.cycle(300, price=102, oi=1040)[0]
        self.assertTrue(self.evidence(changed)['direction_changed'])
        self.assertIn('TRADE READ CHANGED', changed['text'])

    def test_funding_watch_reports_direction_changes_and_enforces_existing_cap(self):
        self.cfg = replace(self.cfg, max_alerts_per_hour=1)
        self.start()
        self.cycle(300)
        changed = self.cycle(600, price=102, oi=1040)[0]
        self.assertEqual(self.evidence(changed)['condition'], 'holding')
        self.assertTrue(self.evidence(changed)['direction_changed'])
        self.assertEqual(self.evidence(changed)['playbook']['direction'], 'bullish_continuation')
        self.assertIn('TRADE READ CHANGED', changed['text'])
        self.assertFalse(self.cycle(900, price=102, oi=1040))
        unconfirmed = self.cycle(1200)[0]
        self.assertEqual(self.evidence(unconfirmed)['playbook']['direction'], 'unconfirmed')
        ended = self.cycle(1500, price=104.04, oi=1081.6)[0]
        self.assertEqual(self.evidence(ended)['closed_reason'], 'update_limit')
        self.assertEqual(self.track()['update_count'], 4)

    def test_configuration_rejects_unbounded_or_ambiguous_followup_settings(self):
        for values in ({'followup_enabled': 1}, {'followup_check_minutes': True},
                       {'followup_horizon_minutes': 1000}, {'followup_max_updates': 1},
                       {'followup_check_minutes': 60, 'followup_horizon_minutes': 60}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Config(**values)
