"""Regression tests for prospective cost screening and frozen legacy watches."""

from copy import deepcopy
from dataclasses import replace
import tempfile
import unittest

from market_watch.config import Config, load_config
from market_watch.service import run_cycle
from market_watch.setup_cards import setup_card
from market_watch.setup_costs import (POLICY_VERSION, confirmation_economics, economics,
                                     policy_for, screen_candidate)
from market_watch.setup_data import Candle
from market_watch.setup_rules import candidate, transition
from market_watch.storage import Store
from market_watch.tests.test_setups import END, NOW, batch, book, history


class CostTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config(assets=('BTC',), setup_enabled=True, summary_hours=(), free_summary_hour=1)
        self.raw = candidate(self.cfg, 'BTC', history(), NOW)

    def test_live_tiny_btc_candidate_is_rejected_with_cost_evidence(self):
        # Public price-level regression from the first shadow candidate. No
        # production IDs, config, destinations or operator paths are retained.
        raw = {**self.raw, 'trigger': 84808.52142857143, 'invalidation': 84804.08928571429,
               'target_1': 84815.16964285714, 'target_2': 84819.60178571429,
               'entry_limit': 84811.65, 'atr': 5.214285714285714}
        qualified, evidence = screen_candidate(raw, self.cfg)
        self.assertIsNone(qualified)
        self.assertEqual(evidence['reasons'], ['targets_do_not_cover_costs', 'volatility_too_small',
                                               'invalidation_too_close', 'net_reward_risk_too_low'])
        self.assertAlmostEqual(evidence['at_trigger']['target_2']['gross_move_bps'], 1.3065146)
        self.assertGreater(evidence['at_trigger']['target_2']['cost_bps'], 13)
        self.assertLess(evidence['at_trigger']['target_2']['net_reward'], 0)

    def test_fees_charge_entry_and_exit_notionals_for_both_directions(self):
        policy = {**policy_for(self.cfg), 'fee_bps_per_side': 4.5, 'slippage_bps_per_side': 0}
        long = {'side': 'long', 'invalidation': 90, 'target_1': 110, 'target_2': 120}
        short = {'side': 'short', 'invalidation': 110, 'target_1': 90, 'target_2': 80}
        for spec, stop_cost, target_cost in [(long, .0855, .099), (short, .0945, .081)]:
            result = economics(spec, 100, policy)
            self.assertAlmostEqual(result['stop_cost'], stop_cost)
            self.assertAlmostEqual(result['net_risk'], 10 + stop_cost)
            self.assertAlmostEqual(result['target_2']['estimated_cost'], target_cost)
            self.assertAlmostEqual(result['target_2']['net_rr'], (20 - target_cost) / (10 + stop_cost))

    def test_narrowed_band_preserves_minimum_for_long_and_short(self):
        mirror = [replace(r, open=202-r.open, high=202-r.low, low=202-r.high, close=202-r.close)
                  for r in history()]
        for raw in [self.raw, candidate(self.cfg, 'BTC', mirror, NOW)]:
            original = deepcopy(raw)
            spec, evidence = screen_candidate(raw, self.cfg)
            self.assertEqual(raw, original)
            self.assertIsNotNone(spec)
            self.assertEqual(evidence['reasons'], [])
            sign = 1 if spec['side'] == 'long' else -1
            self.assertGreater(sign * (spec['entry_limit'] - spec['trigger']), 0)
            self.assertLess(sign * (spec['entry_limit'] - spec['trigger']),
                            sign * (raw['entry_limit'] - raw['trigger']))
            for key in ('target_1', 'target_2', 'invalidation', 'trigger'):
                self.assertEqual(spec[key], raw[key])
            for fraction in (0, .25, .5, .75, 1):
                entry = spec['trigger'] + fraction * (spec['entry_limit'] - spec['trigger'])
                self.assertGreaterEqual(confirmation_economics(spec, entry)['target_2']['net_rr'] + 1e-10, 1.5)
            outside = confirmation_economics(spec, spec['entry_limit'] + sign*.001)
            self.assertLess(outside['target_2']['net_rr'], 1.5)

    def test_costs_and_thresholds_are_frozen_even_if_operator_changes_config(self):
        spec, _ = screen_candidate(self.raw, self.cfg)
        original = deepcopy(spec)
        replacement = replace(self.cfg, setup_fee_bps_per_side=50, setup_min_net_rr=2)
        self.assertIsNone(screen_candidate(self.raw, replacement)[0])
        economics_before = confirmation_economics(spec, spec['trigger'])
        self.assertEqual(economics_before, spec['cost_screen']['at_trigger'])
        self.assertEqual(spec, original)

    def test_zero_cost_configuration_still_caps_late_entries(self):
        cfg = replace(self.cfg, setup_fee_bps_per_side=0, setup_slippage_bps_per_side=0)
        spec, evidence = screen_candidate(self.raw, cfg)
        self.assertAlmostEqual(evidence['at_trigger']['target_1']['net_rr'], 1.5)
        self.assertAlmostEqual(evidence['at_trigger']['target_2']['net_rr'], 2.5)
        self.assertAlmostEqual(evidence['at_entry_limit']['target_2']['net_rr'], 1.5)
        self.assertLess(spec['entry_limit'], self.raw['entry_limit'])

    def test_volatility_and_risk_minimums_reject_otherwise_affordable_setups(self):
        for name, reason in [('setup_min_atr_bps', 'volatility_too_small'),
                             ('setup_min_risk_bps', 'invalidation_too_close')]:
            spec, evidence = screen_candidate(self.raw, replace(self.cfg, **{name: 500}))
            self.assertIsNone(spec)
            self.assertIn(reason, evidence['reasons'])

    def test_invalid_levels_and_cost_settings_fail_closed(self):
        for key in ('trigger', 'entry_limit', 'invalidation', 'target_1', 'target_2', 'atr'):
            for value in (-1, 0, float('nan'), float('inf')):
                spec, evidence = screen_candidate({**self.raw, key: value}, self.cfg)
                self.assertIsNone(spec)
                self.assertEqual(evidence['reasons'], ['invalid_price_levels'])
        for key in ('setup_fee_bps_per_side', 'setup_slippage_bps_per_side',
                    'setup_min_atr_bps', 'setup_min_risk_bps', 'setup_min_net_rr'):
            for value in (True, -1, float('nan'), float('inf'), 1000, '1'):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    replace(self.cfg, **{key: value})

    def test_old_config_gets_defaults_without_rewriting_file_or_enabling_publish(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            original = '{"setup_enabled":true,"setup_publish":false,"setup_version":"breakout-retest-v1"}\n'
            path.write_text(original)
            cfg = load_config(path)
            self.assertEqual(cfg.setup_fee_bps_per_side, 4.5)
            self.assertEqual(cfg.setup_min_net_rr, 1.5)
            self.assertFalse(cfg.setup_publish)
            self.assertEqual(path.read_text(), original)

    def test_confirmation_rechecks_frozen_policy_and_legacy_rules_are_preserved(self):
        spec, _ = screen_candidate(self.raw, self.cfg)
        close = (spec['entry_limit'] + spec['trigger']) / 2
        a = spec['atr']
        candle = Candle('hyperliquid', 'BTC', END+300, spec['level']+.05*a,
                        close+.1*a, spec['level']-.1*a, close, 100, NOW+600)
        track = {'stage': 'armed'}
        stage, _, detail = transition(spec, track, candle, book(close, NOW+600), NOW+600)
        self.assertEqual(stage, 'triggered')
        self.assertGreaterEqual(detail['execution_costs']['target_2']['net_rr'], 1.5)
        # A stale/wrong band must not let a quote that fails costs confirm.
        wrong_band = {**spec, 'entry_limit': self.raw['entry_limit']}
        far_quote = spec['trigger'] + .2*a
        self.assertEqual(transition(wrong_band, track, candle, book(far_quote, NOW+600), NOW+600)[:2],
                         ('armed', 'net_reward_risk_too_low'))
        legacy = deepcopy(self.raw)
        for key in list(legacy['config']):
            if key.startswith(('setup_fee_', 'setup_slippage_', 'setup_min_atr_', 'setup_min_risk_', 'setup_min_net_')):
                del legacy['config'][key]
        before = deepcopy(legacy)
        self.assertEqual(transition(legacy, track, candle, book(far_quote, NOW+600), NOW+600)[0], 'triggered')
        self.assertIsNone(confirmation_economics(legacy, far_quote))
        text, _ = setup_card(Config(**legacy['config']), {'id': 'legacy', 'stage': 'armed', 'spec': legacy},
                             'armed', {}, NOW)
        self.assertIn('Legacy setup', text)
        self.assertNotIn('Room after costs', text)
        self.assertEqual(legacy, before)

    def test_rejections_are_archived_as_screen_evidence_without_cards(self):
        tiny = [replace(r, open=84800+(r.open-101)*.01, high=84800+(r.high-101)*.01,
                        low=84800+(r.low-101)*.01, close=84800+(r.close-101)*.01) for r in history()]
        store = Store(':memory:')
        try:
            run_cycle(self.cfg, store, [], {}, [], NOW, batch(tiny, NOW))
            status = store.setup_status()
            self.assertEqual(status['active'], 0)
            self.assertEqual(status['health']['status'], 'ready')
            self.assertEqual(status['health']['screen']['BTC'], 'targets_do_not_cover_costs')
            self.assertEqual(status['health']['cost_policy']['version'], POLICY_VERSION)
            self.assertLess(status['health']['screen_details']['BTC']['at_trigger']['target_2']['net_rr'], 0)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM setup_events').fetchone()[0], 0)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM setup_samples').fetchone()[0], 1)
        finally:
            store.close()

    def test_new_shadow_watches_have_distinct_identity_and_no_deliveries(self):
        store = Store(':memory:')
        try:
            run_cycle(self.cfg, store, [], {}, [], NOW, batch(history(), NOW))
            track = store.active_setups()[0]
            self.assertIn(POLICY_VERSION, track['event_key'])
            self.assertEqual(track['spec']['cost_screen']['policy']['version'], POLICY_VERSION)
            self.assertFalse(track['spec']['config']['setup_publish'])
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0], 0)
        finally:
            store.close()


if __name__ == '__main__':
    unittest.main()
