import contextlib
from dataclasses import replace
import io
import json
from unittest.mock import patch

from market_watch.__main__ import main
from market_watch.engine import market_alerts
from market_watch.models import Event
from market_watch.outcomes import report
from market_watch.storage import Store
from test_market_watch import NOW, StoreCase, observation


class OutcomeTests(StoreCase):
    def alert(self, at=NOW, cfg=None):
        cfg = cfg or self.cfg
        self.add_history(now=at-900)
        event = market_alerts(cfg, self.store,
                              [observation(v, now=at, price=102, oi=1040) for v in cfg.venues], at)[0]
        with self.store.db:
            return self.store.add_event(event, [])

    def samples(self, at, price, venues=('hyperliquid', 'okx'), fetched_at=None):
        rows = [observation(v, now=at, price=price) for v in venues]
        if fetched_at is not None:
            rows = [replace(o, fetched_at=fetched_at) for o in rows]
        with self.store.db:
            self.store.add_observations(rows)

    def test_horizons_use_original_mark_and_preserve_unfavorable_and_missing_outcomes(self):
        self.alert()
        self.samples(NOW+930, 103.02)
        self.samples(NOW+3600, 100.98)
        result = report(self.store, NOW+14600, include_details=True)
        group = result['cohorts'][0]
        self.assertEqual(result['total_alerts'], 1)
        self.assertEqual(group['alerts'], 1)
        measured = {x['horizon_minutes']: x for x in group['outcomes'] if x['venue']=='hyperliquid'}
        self.assertAlmostEqual(measured[15]['median_mark_change_pct'], 1)
        self.assertEqual(measured[15]['positive_mark_changes'], 1)
        self.assertAlmostEqual(measured[60]['median_mark_change_pct'], -1)
        self.assertEqual(measured[60]['negative_mark_changes'], 1)
        self.assertEqual(measured[240]['missing'], 1)
        self.assertIsNone(measured[240]['median_mark_change_pct'])
        self.assertEqual(result['events'][0]['outcomes'][0]['sample_delay_seconds'], 30)

    def test_no_lookahead_from_future_event_future_sample_or_late_receipt(self):
        self.alert()
        self.alert(NOW+7200)
        self.samples(NOW+900, 500, fetched_at=NOW+1000)
        self.samples(NOW+990, 200)
        result = report(self.store, NOW+950)
        self.assertEqual(result['total_alerts'], 1)
        self.assertTrue(all(x['measured']==0 for x in result['cohorts'][0]['outcomes']))
        result = report(self.store, NOW+1000, include_details=True)
        first = result['events'][0]['outcomes'][0]
        self.assertEqual(first['observed_at'], NOW+900)
        self.assertEqual(first['fetched_at'], NOW+1000)

    def test_missing_window_is_not_filled_with_old_or_late_measurements(self):
        self.alert()
        self.samples(NOW+899, 150)
        self.samples(NOW+1081, 200)
        result = report(self.store, NOW+1200)
        outcomes = result['cohorts'][0]['outcomes']
        self.assertTrue(all(x['missing']==1 for x in outcomes if x['horizon_minutes']==15))
        self.assertTrue(all(x['pending']==1 for x in outcomes if x['horizon_minutes']>15))

    def test_receipt_after_sampling_window_is_unavailable_even_with_in_window_source_time(self):
        self.alert()
        self.samples(NOW+1000, 200, fetched_at=NOW+1200)
        result = report(self.store, NOW+1500)
        self.assertTrue(all(x['missing']==1 for x in result['cohorts'][0]['outcomes'] if x['horizon_minutes']==15))

    def test_venues_and_instruments_are_not_substituted(self):
        self.alert()
        self.samples(NOW+900, 103.02, venues=('hyperliquid',))
        with self.store.db:
            self.store.add_observations([replace(observation('okx', now=NOW+900, price=999), instrument='OTHER')])
        result = report(self.store, NOW+1100)
        outcomes = [x for x in result['cohorts'][0]['outcomes'] if x['horizon_minutes']==15]
        self.assertEqual([(x['venue'],x['measured'],x['missing']) for x in outcomes], [('hyperliquid',1,0),('okx',0,1)])

    def test_rule_settings_separate_cohorts_and_no_alert_is_silently_dropped(self):
        self.alert()
        self.alert(NOW+7200, replace(self.cfg, price_change_pct=1.5))
        with self.store.db:
            self.store.add_event(Event('unsupported', 'alert', 'paid', NOW+100, NOW+700, 'legacy', {}), [])
            self.store.add_event(Event('summary', 'summary', 'paid', NOW+100, NOW+700, 'brief', {}), [])
        result = report(self.store, NOW+15000)
        self.assertEqual(result['total_alerts'], 3)
        self.assertEqual(result['included_alerts'], 2)
        self.assertEqual(len(result['excluded_alerts']), 1)
        self.assertEqual(len(result['cohorts']), 2)
        for group in result['cohorts']:
            for x in group['outcomes']:
                self.assertEqual(x['measured']+x['missing']+x['pending'], group['alerts'])

    def test_unsupported_or_nonfinite_original_evidence_is_counted_as_excluded(self):
        self.alert()
        with self.store.db:
            self.store.db.execute("UPDATE events SET evidence=?", (json.dumps({'config': {},'rule':'price_oi_up','asset':'BTC','observations':[{'bad':True}],'comparisons':[]}),))
        result=report(self.store, NOW+1100)
        self.assertEqual(result['included_alerts'],0)
        self.assertEqual(len(result['excluded_alerts']),1)

    def test_funding_cohorts_separate_bullish_and_bearish_context(self):
        for at, price in [(NOW,102),(NOW+7200,98)]:
            self.add_history(now=at-900)
            rows=[observation(v,now=at,price=price,oi=1040,bps=5) for v in self.cfg.venues]
            event=next(e for e in market_alerts(self.cfg,self.store,rows,at) if e.evidence['rule']=='positive_funding')
            with self.store.db: self.store.add_event(event,[])
        result=report(self.store,NOW+15000)
        self.assertEqual({g['direction'] for g in result['cohorts']},{'bullish_continuation','bearish_continuation'})
        self.assertEqual(len(result['cohorts']),2)

    def test_empty_archive_and_window_bounds(self):
        self.assertEqual(report(self.store,NOW)['total_alerts'],0)
        self.alert()
        self.assertEqual(report(self.store,NOW+86401,days=1)['total_alerts'],0)
        for days in (0,366,True):
            with self.assertRaises(ValueError): report(self.store,NOW,days)

    def test_report_and_cli_are_read_only_and_make_no_collection_or_delivery_calls(self):
        self.alert()
        readonly=Store(self.path,readonly=True)
        first=report(readonly,NOW+1100,include_details=True)
        self.assertEqual(readonly.db.total_changes,0)
        self.assertEqual(first,report(readonly,NOW+1100,include_details=True))
        readonly.close()
        output=io.StringIO()
        with patch('market_watch.__main__.time.time',return_value=NOW+1100), patch('market_watch.__main__.collect') as collect, patch('market_watch.__main__.dispatch') as dispatch, contextlib.redirect_stdout(output):
            self.assertEqual(main(['--database',self.path,'outcomes','--details']),0)
        collect.assert_not_called()
        dispatch.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()),first)
