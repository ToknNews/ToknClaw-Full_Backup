from dataclasses import replace
import unittest

from market_watch.config import Config
from market_watch.playbooks import budget_text, build_playbook, direction, funding_budget, followup_action
from market_watch.presentation import alert_card
from test_market_watch import observation, NOW


class PlaybookTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.rows = [observation(v, bps=bps) for v, bps in [('hyperliquid', 1), ('okx', 5)]]

    def comparisons(self, price=1, oi=3):
        return [{'venue': o.venue, 'price_pct': price, 'oi_base_pct': oi} for o in self.rows]

    def test_price_oi_context_not_funding_sign_determines_direction(self):
        for price, expected in [(1, 'bullish_continuation'), (-1, 'bearish_continuation'), (0, 'unconfirmed')]:
            for funding in (-5, 5):
                rows = [replace(o, funding_rate=funding / 10000 * o.funding_interval_hours / 8) for o in self.rows]
                book = build_playbook(self.cfg, 'positive_funding' if funding > 0 else 'negative_funding', rows, self.comparisons(price))
                self.assertEqual(book['direction'], expected)

    def test_missing_duplicate_and_opposed_baselines_never_invent_direction(self):
        for changes in ([], self.comparisons()[:1], self.comparisons()[:1]*2,
                        [self.comparisons()[0], self.comparisons(-1)[1]], self.comparisons(1, -1)):
            self.assertEqual(direction(self.cfg, self.rows, changes), 'unconfirmed')
        self.assertEqual(direction(self.cfg, self.rows[:1], self.comparisons()), 'unavailable')

    def test_funding_side_comparison_handles_positive_negative_and_cross_zero_rates(self):
        for rates in ((1, 5), (-5, -1), (-2, 4)):
            rows = [replace(o, funding_rate=b / 10000 * o.funding_interval_hours / 8) for o, b in zip(self.rows, rates)]
            for ordered in (rows, rows[::-1]):
                book = build_playbook(self.cfg, 'funding_divergence', ordered, [])
                self.assertEqual(book['carry']['long_venue'], 'hyperliquid')
                self.assertEqual(book['carry']['short_venue'], 'okx')
                self.assertAlmostEqual(book['carry']['gap_bps_8h'], rates[1]-rates[0])
                self.assertEqual(book['direction'], 'unconfirmed')

    def test_funding_budget_preserves_sign_units_and_actual_interval(self):
        for interval in (1, 2, 4, 8):
            for bps in (-5, 0, 5):
                o = replace(self.rows[1], funding_interval_hours=interval, funding_rate=bps / 10000 * interval / 8)
                budget = funding_budget([o])[0]
                self.assertAlmostEqual(budget['long_cashflow_8h'], -bps)
                self.assertAlmostEqual(budget['short_cashflow_8h'], bps)
                self.assertAlmostEqual(budget['long_cashflow_interval'], -bps * interval / 8)
                self.assertEqual(budget['quote_currency'], 'USDT')
        self.assertIn('Long pay 1.00 / Short receive 1.00 USD', budget_text(self.rows))
        self.assertIn('at unchanged rates', budget_text(self.rows))

    def test_directional_funding_card_displays_both_invalidation_conditions(self):
        text, _ = alert_card(self.cfg, 'funding_divergence', 'BTC', self.rows, self.comparisons(), NOW)
        self.assertIn('Highest minus lowest funding', text)
        self.assertIn('Direction separately: Price', text)
        self.assertIn('Long: Hyperliquid', text)
        self.assertIn('Short: OKX', text)
        self.assertIn('New entry:', text)

    def test_tied_funding_does_not_claim_a_venue_advantage(self):
        rows = [replace(o, funding_rate=0) for o in self.rows]
        book = build_playbook(self.cfg, 'funding_divergence', rows, [])
        self.assertIsNone(book['carry'])
        self.assertIn('no current funding advantage', book['position'])

    def test_position_updates_distinguish_fade_outage_and_expiry(self):
        self.assertIn('Long: Cancel', followup_action('price_oi_up', 'faded', 'condition_faded'))
        self.assertIn('Short: Cancel', followup_action('price_oi_down', 'faded', 'condition_faded'))
        self.assertIn('old spread', followup_action('funding_divergence', 'faded', 'condition_faded'))
        self.assertIn('missing data', followup_action('price_oi_up', 'unavailable', ''))
        self.assertIn('expired watch', followup_action('price_oi_up', 'holding', 'horizon_elapsed'))


if __name__ == '__main__':
    unittest.main()
