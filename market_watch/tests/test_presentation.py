import json
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from market_watch.delivery import Route, dispatch, send
from market_watch.engine import market_alerts, summaries
from market_watch.http import RemoteError
from market_watch.message_preview import examples, render_html
from market_watch.presentation import COLORS, alert_card, brief_read, recheck_rule, validate_presentation, venue_lines
from market_watch.storage import Store
from test_market_watch import DISCORD, FakeClient, NOW, StoreCase, observation


class PresentationTests(StoreCase):
    def test_all_demo_formats_fit_discord_and_telegram_limits(self):
        items = examples()
        self.assertEqual(len(items), 15)
        for item in items:
            with self.subTest(kind=item['kind']):
                embed = validate_presentation(item['presentation'])
                self.assertLessEqual(len(item['text'].encode('utf-16-le')) // 2, 3900)
                self.assertTrue(embed['title'].startswith('DEMO'))
                self.assertIn('NOT LIVE DATA', item['text'])

    def test_funding_percent_preserves_normalization_and_quote_currency(self):
        hl = observation(bps=1.2)
        okx = replace(observation('okx', bps=-1.2), funding_interval_hours=4, funding_rate=-0.00006)
        self.assertIn('+0.0120% / 8h eq.', venue_lines(hl))
        self.assertIn('-0.0120% / 8h eq.', venue_lines(okx))
        self.assertIn('100.00 USD\n', venue_lines(hl))
        self.assertIn('100.00 USDT\n', venue_lines(okx))
        self.assertIn('Received', venue_lines(hl))
        self.assertIn('As of', venue_lines(okx))

    def test_price_and_oi_changes_remain_separate_from_dollar_notional(self):
        self.add_history()
        rows = [observation(v, price=102, oi=1040) for v in self.cfg.venues]
        event = market_alerts(self.cfg, self.store, rows, NOW)[0]
        self.assertIn('Price +2.00% · OI +4.00%', event.text)
        self.assertIn('OI notional $106.08K', event.text)
        self.assertEqual(event.evidence['presentation']['discord']['color'], COLORS['up'])

    def test_downside_color_and_signs_match_the_observations(self):
        self.add_history()
        rows = [observation(v, price=98, oi=1040) for v in self.cfg.venues]
        event = market_alerts(self.cfg, self.store, rows, NOW)[0]
        self.assertIn('PRICE ↓ / OI ↑', event.text)
        self.assertIn('Price -2.00% · OI +4.00%', event.text)
        self.assertEqual(event.evidence['presentation']['discord']['color'], COLORS['down'])

    def test_summary_renders_valid_baselines_and_avoids_invented_zero_changes(self):
        cfg = replace(self.cfg, summary_hours=(8,), free_summary_hour=8)
        rows = [observation(v, price=102, oi=1040) for v in cfg.venues]
        first = summaries(cfg, self.store, rows, {}, NOW)[0]
        self.assertIn('valid baseline', first.text)
        self.assertNotIn('Price +0.00%', first.text)
        self.add_history()
        second = summaries(cfg, self.store, rows, {}, NOW)[0]
        self.assertIn('Price +2.00% · OI +4.00%', second.text)
        self.assertEqual(len(second.evidence['comparisons']['BTC']), 2)

    def test_incomplete_asset_does_not_show_partial_price_as_full_coverage(self):
        cfg = replace(self.cfg, summary_hours=(8,), free_summary_hour=8)
        event = summaries(cfg, self.store, [observation(price=12345)], {'okx:BTC': 'missing_measurement'}, NOW)[0]
        self.assertIn('analysis paused', event.text)
        self.assertNotIn('12,345', event.text)
        self.assertIn('0/1 assets ready', event.text)

    def test_free_embed_and_plain_text_exclude_paid_measurements(self):
        cfg = replace(self.cfg, assets=('BTC', 'ETH', 'SOL'), summary_hours=(8,), free_summary_hour=8)
        rows = [observation(v, asset=asset, price=price) for v in cfg.venues
                for asset, price in [('BTC', 100), ('ETH', 9876.54), ('SOL', 8765.43)]]
        free = next(e for e in summaries(cfg, self.store, rows, {'okx:ETH': 'missing_measurement'}, NOW) if e.audience == 'free')
        serialized = json.dumps(free.evidence['presentation'])
        self.assertNotIn('9,876.54', serialized + free.text)
        self.assertNotIn('8,765.43', serialized + free.text)
        self.assertEqual(set(free.evidence['comparisons']), {'BTC'})
        self.assertEqual(free.evidence['issues'], {})
        self.assertFalse({'ETH', 'SOL'} & {field['name'] for field in free.evidence['presentation']['discord']['fields']})

    def test_local_clock_and_utc_source_clock_are_both_explicit(self):
        rows = [observation(v) for v in self.cfg.venues]
        winter = datetime(2026, 1, 1, 13, tzinfo=timezone.utc).timestamp()
        text, _ = alert_card(self.cfg, 'positive_funding', 'BTC', rows, [], winter)
        self.assertIn('08:00 AM EST', text)
        text, _ = alert_card(self.cfg, 'positive_funding', 'BTC', rows, [], NOW)
        self.assertIn('08:02 AM EDT', text)
        self.assertIn('UTC', text)

    def test_recheck_criteria_use_custom_thresholds_without_rounding_them_away(self):
        cfg = replace(self.cfg, lookback_minutes=30, price_change_pct=1.125,
                      oi_change_pct=3.25, funding_extreme_bps_8h=4.5,
                      funding_spread_bps_8h=2.125)
        self.assertIn('Price ≥ +1.125%', recheck_rule(cfg, 'price_oi_up'))
        self.assertIn('Price ≤ -1.125%', recheck_rule(cfg, 'price_oi_down'))
        self.assertIn('OI ≥ +3.25%', recheck_rule(cfg, 'price_oi_up'))
        self.assertIn('~30m', recheck_rule(cfg, 'price_oi_up'))
        self.assertIn('≥ +0.045%', recheck_rule(cfg, 'positive_funding'))
        self.assertIn('≤ -0.045%', recheck_rule(cfg, 'negative_funding'))
        self.assertIn('≥ 2.125 bps', recheck_rule(cfg, 'funding_divergence'))

    def test_brief_read_agrees_with_engine_on_direction_mixed_data_and_thresholds(self):
        self.add_history()
        cases = [
            ((102, 102), (1040, 1040), 'Rally + rising OI.', 'price_oi_up'),
            ((98, 98), (1040, 1040), 'Selloff + rising OI.', 'price_oi_down'),
            ((102, 98), (1040, 1040), 'No shared price/OI trigger', None),
            ((102, 102), (1040, 990), 'No shared price/OI trigger', None),
            ((100.5, 100.5), (1040, 1040), 'No shared price/OI trigger', None),
        ]
        for prices, oi, expected, rule in cases:
            rows = [observation(v, price=p, oi=o) for v, p, o in zip(self.cfg.venues, prices, oi)]
            with self.subTest(prices=prices, oi=oi):
                events = market_alerts(self.cfg, self.store, rows, NOW)
                brief = summaries(replace(self.cfg, summary_hours=(8,)), self.store, rows, {}, NOW)[0]
                self.assertIn(expected, brief.text)
                self.assertEqual([e.evidence['rule'] for e in events], [rule] if rule else [])

    def test_brief_read_distinguishes_missing_coverage_from_missing_baselines(self):
        rows = [observation(v, bps=5) for v in self.cfg.venues]
        self.assertEqual(brief_read(self.cfg, rows[:1], []), 'Coverage incomplete. Analysis paused.')
        read = brief_read(self.cfg, rows, [])
        self.assertIn('needs a valid baseline', read)
        self.assertIn('Longs face elevated funding costs.', read)
        self.assertNotIn('No shared price/OI trigger', read)
        self.assertNotIn('Rally', read)

    def test_funding_brief_context_agrees_with_alert_rules_without_price_baselines(self):
        for rates, expected in [((5, 5), 'Longs face elevated funding costs.'),
                                ((-5, -5), 'Shorts face elevated funding costs.'),
                                ((1, 5), 'Funding differs across venues.')]:
            rows = [observation(v, bps=b) for v, b in zip(self.cfg.venues, rates)]
            with self.subTest(rates=rates):
                self.assertEqual(len(market_alerts(self.cfg, self.store, rows, NOW)), 1)
                brief = summaries(replace(self.cfg, summary_hours=(8,)), self.store, rows, {}, NOW)[0]
                self.assertIn(expected, brief.text)
                self.assertIn('needs a valid baseline', brief.text)

    def test_embed_survives_archive_restart_and_uses_receipt_delivery(self):
        self.add_history()
        event = market_alerts(self.cfg, self.store, [observation(v, price=102, oi=1040) for v in self.cfg.venues], NOW)[0]
        route = Route('discord', 'paid', DISCORD)
        with self.store.db:
            self.store.add_event(event, [route])
        self.store.close()
        self.store = Store(self.path)
        client = FakeClient([{'id': 'card-receipt'}])
        self.assertEqual(dispatch(self.store, [route], client, lambda: NOW)['sent'], 1)
        payload = client.calls[0][1]
        self.assertEqual(payload['embeds'], [event.evidence['presentation']['discord']])
        self.assertNotIn('content', payload)
        self.assertEqual(payload['allowed_mentions'], {'parse': []})
        self.assertTrue(client.calls[0][0].endswith('?wait=true'))

    def test_telegram_uses_matching_plain_text_without_discord_markup(self):
        item = examples()[0]
        route = Route('telegram', 'paid', 'https://api.telegram.org/bot123:test/sendMessage', '-123')
        client = FakeClient([{'ok': True, 'result': {'message_id': 123}}])
        self.assertEqual(send(route, item['text'], client, item['presentation']), '123')
        self.assertEqual(client.calls[0][1]['text'], item['text'])
        self.assertNotIn('parse_mode', client.calls[0][1])

    def test_invalid_or_oversized_embed_never_reaches_network(self):
        for mutation in ('oversize', 'extra_url', 'wrong_format'):
            item = examples()[0]
            if mutation == 'oversize':
                item['presentation']['discord']['fields'][0]['value'] = 'x' * 1025
            elif mutation == 'extra_url':
                item['presentation']['discord']['image'] = {'url': 'https://example.com/private'}
            else:
                item['presentation']['format'] = 'unknown'
            client = FakeClient([])
            with self.subTest(mutation=mutation), self.assertRaises(RemoteError) as caught:
                send(Route('discord', 'paid', DISCORD), item['text'], client, item['presentation'])
            self.assertEqual(caught.exception.code, 'invalid_presentation')
            self.assertFalse(client.calls)

    def test_html_preview_escapes_content_and_labels_all_samples(self):
        items = examples()
        items[0]['presentation']['discord']['title'] = '<img src=x onerror=bad()>'
        output = render_html(items)
        self.assertNotIn('<img src=x', output)
        self.assertIn('&lt;img src=x', output)
        self.assertIn('ALL MARKET VALUES ARE FICTIONAL', output)
        self.assertNotIn(DISCORD, output)


if __name__ == '__main__':
    unittest.main()
