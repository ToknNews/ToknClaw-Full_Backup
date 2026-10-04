import contextlib
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_watch.__main__ import main
from market_watch.config import Config
from market_watch.delivery import Route, dispatch
from market_watch.http import RemoteError
from market_watch.presentation import validate_presentation
from market_watch.service import run_cycle
from market_watch.setup_data import (Candle, SetupBatch, collect_setup_data, expected_close,
                                     parse_book, parse_hl_candles, parse_okx_candles, parse_spot)
from market_watch.setup_rules import candidate, features
from market_watch.setup_config import set_mode
from market_watch.setup_preview import examples, preview_html
from market_watch.storage import Store

END = datetime(2026, 10, 4, 12, tzinfo=timezone.utc).timestamp()
NOW = END + 20


def history(end=END, asset='BTC', venue='hyperliquid'):
    rows = []
    for i in range(64):
        center = [100.4, 100.8, 101.2, 101.6, 101.2, 100.8][i % 6]
        rows.append(Candle(venue, asset, end - (64 - i) * 300, center - .1,
                           center + .2, center - .2, center, 100, end + 20))
    rows[-1] = replace(rows[-1], open=101.45, high=101.75, low=101.4, close=101.65)
    return rows


def book(mid=101.65, now=NOW):
    return {'venue': 'hyperliquid', 'asset': 'BTC', 'observed_at': now - 1,
            'received_at': now, 'mid': mid, 'bid': mid - .001, 'ask': mid + .001,
            'spread_bps': .2, 'bid_depth_usd': 100000, 'ask_depth_usd': 100000,
            'depth_band_bps': 10, 'returned_levels': [20, 20], 'depth_is_partial': True}


def batch(rows, now, current_book=True):
    return SetupBatch(rows[-1].close_at, rows,
                      {'BTC': book(rows[-1].close, now)} if current_book else {})


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'state.sqlite3')
        self.store = Store(self.path)
        self.cfg = Config(assets=('BTC',), setup_enabled=True, setup_publish=True,
                          summary_hours=(), free_summary_hour=1)
        self.route = Route('discord', 'paid', 'https://discord.com/api/webhooks/123/fictional-test')
        self.free = Route('telegram', 'free', 'https://api.telegram.org/botfictional/sendMessage', 'free-test')
        self.rows = history()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def cycle(self, now, data=None, config=None, routes=None):
        result = run_cycle(config or self.cfg, self.store, [], {},
                           [self.route, self.free] if routes is None else routes, now, data)
        return [r for r in result['events'] if r['kind'].startswith('setup')]

    def start(self, receipt=True, config=None):
        events = self.cycle(NOW, batch(self.rows, NOW), config)
        self.assertEqual(len(events), 1)
        track = self.store.active_setups()[0]
        if receipt:
            with self.store.db:
                self.store.db.execute("UPDATE deliveries SET status='sent',remote_id='demo-receipt' WHERE event_id=?", (track['id'],))
        return track

    def next_bar(self, track, kind, now, old_rows=None):
        s = track['spec']; a = s['atr']; t = s['trigger']; level = s['level']
        if kind == 'break':
            o, h, l, c, v = level - .1*a, t + .2*a, level - .3*a, t + .1*a, 160
        elif kind == 'retest':
            o, h, l, c, v = level + .05*a, t + .3*a, level - .1*a, t + .2*a, 90
        elif kind == 'hold':
            o, h, l, c, v = t+.1*a, t+.3*a, t, t+.2*a, 100
        elif kind == 'target1':
            o, h, l, c, v = t+.2*a, s['target_1']+.01, t+.1*a, s['target_1']-.01, 100
        elif kind == 'target2':
            o, h, l, c, v = s['target_1'], s['target_2']+.01, s['target_1']-.1*a, s['target_2']-.01, 100
        elif kind == 'stop':
            o, h, l, c, v = t, t+.01, s['invalidation']-.01, s['invalidation']+.01, 100
        elif kind == 'ambiguous':
            o, h, l, c, v = t, s['target_1']+.01, s['invalidation']-.01, t, 100
        else:
            raise ValueError(kind)
        rows = list(self.rows if old_rows is None else old_rows)
        rows.append(Candle('hyperliquid', 'BTC', now-20-300, o,h,l,c,v,now))
        return rows

    def arm(self):
        track = self.start()
        self.rows = self.next_bar(track, 'break', NOW+300)
        events = self.cycle(NOW+300, batch(self.rows, NOW+300))
        self.assertEqual(len(events), 1)
        self.assertEqual(self.store.active_setups()[0]['stage'], 'armed')
        return self.store.active_setups()[0]

    def trigger(self):
        track = self.arm()
        self.rows = self.next_bar(track, 'retest', NOW+600)
        self.cycle(NOW+600, batch(self.rows, NOW+600))
        self.assertEqual(self.store.active_setups()[0]['stage'], 'triggered')
        return self.store.active_setups()[0]

    def test_complete_lifecycle_levels_frozen_and_paid_only(self):
        track = self.trigger()
        original = track['spec']
        self.rows = self.next_bar(track, 'hold', NOW+900)
        self.cycle(NOW+900, batch(self.rows, NOW+900))
        self.rows = self.next_bar(track, 'target1', NOW+1200)
        self.cycle(NOW+1200, batch(self.rows, NOW+1200))
        self.assertEqual(self.store.active_setups()[0]['stage'], 'target_1')
        self.rows = self.next_bar(track, 'target2', NOW+1500)
        self.cycle(NOW+1500, batch(self.rows, NOW+1500))
        self.assertEqual(self.store.active_setups(), [])
        self.assertEqual(self.store.setup_status()['states'], {'completed': 1})
        archived = [e for e in self.store.export_events() if e['kind'].startswith('setup')]
        self.assertEqual(len(archived), 5)
        for e in archived:
            self.assertEqual(e['evidence']['spec'], original)
            validate_presentation(e['evidence']['presentation'])
            self.assertLess(len(e['text'].encode('utf-16-le'))//2, 3900)
        routes = {r[0] for r in self.store.db.execute('''SELECT route FROM deliveries
            WHERE event_id IN (SELECT event_id FROM setup_events)''')}
        self.assertEqual(routes, {self.route.name})

    def test_short_setup_uses_mirrored_price_structure(self):
        self.rows = [replace(r, open=202-r.open, high=202-r.low, low=202-r.high, close=202-r.close) for r in self.rows]
        track = self.start()
        self.assertEqual(track['spec']['side'], 'short')
        self.assertLess(track['spec']['target_2'], track['spec']['trigger'])
        s = track['spec']; a = s['atr']
        self.rows.append(Candle('hyperliquid','BTC',END,s['level']+.1*a,s['level']+.3*a,
                                s['trigger']-.2*a,s['trigger']-.1*a,160,NOW+300))
        self.cycle(NOW+300,batch(self.rows,NOW+300))
        self.assertEqual(self.store.active_setups()[0]['stage'],'armed')
        self.rows.append(Candle('hyperliquid','BTC',END+300,s['level']-.05*a,s['level']+.1*a,
                                s['trigger']-.3*a,s['trigger']-.2*a,90,NOW+600))
        self.cycle(NOW+600,batch(self.rows,NOW+600))
        self.assertEqual(self.store.active_setups()[0]['stage'],'triggered')

    def test_restart_and_same_bar_do_not_repeat_events(self):
        self.start()
        self.store.close(); self.store = Store(self.path)
        self.assertEqual(self.cycle(NOW+10, batch(self.rows,NOW+10)), [])
        self.assertEqual(self.store.setup_created_count(0), 1)

    def test_partial_history_and_gaps_never_become_longer_features(self):
        self.assertIsNone(features(self.rows[-2:],self.cfg,END))
        gap = self.rows[:-10] + self.rows[-9:]
        self.assertIsNone(features(gap,self.cfg,END))
        self.assertIsNone(candidate(self.cfg,'BTC',self.rows[-2:],NOW))
        self.assertEqual(self.cycle(NOW,batch(self.rows[-2:],NOW)), [])

    def test_no_hindsight_setup_after_breakout(self):
        self.rows[-1] = replace(self.rows[-1], high=103,close=102.8)
        self.assertEqual(self.cycle(NOW,batch(self.rows,NOW)), [])

    def test_volume_required_to_arm(self):
        track = self.start()
        self.rows = self.next_bar(track,'break',NOW+300)
        self.rows[-1] = replace(self.rows[-1], volume_base=110)
        self.assertEqual(self.cycle(NOW+300,batch(self.rows,NOW+300)), [])
        self.assertEqual(self.store.active_setups()[0]['stage'],'forming')

    def test_current_quote_outside_band_prevents_late_trigger(self):
        track = self.arm()
        self.rows = self.next_bar(track,'retest',NOW+600)
        data = batch(self.rows,NOW+600)
        data.books['BTC'] = book(track['spec']['entry_limit']+1,NOW+600)
        self.cycle(NOW+600,data)
        self.assertEqual(self.store.active_setups()[0]['stage'],'armed')

    def test_invalidation_and_ambiguous_bar_are_not_wins(self):
        track = self.trigger()
        self.rows = self.next_bar(track,'ambiguous',NOW+900)
        self.cycle(NOW+900,batch(self.rows,NOW+900))
        self.assertEqual(self.store.setup_status()['states'], {'ambiguous':1})
        self.assertIn('order is unknown', self.store.export_events()[0]['text'])

    def test_failure_before_trigger_never_reports_entered_position(self):
        track=self.start()
        self.rows=self.next_bar(track,'stop',NOW+300)
        self.cycle(NOW+300,batch(self.rows,NOW+300))
        self.assertEqual(self.store.setup_status()['states'],{'invalidated':1})
        self.assertNotIn('triggered_at',self.store.setup_status(1)['recent'][0])

    def test_missing_bar_closes_tracking_without_catchup(self):
        track=self.arm()
        self.rows=self.next_bar(track,'retest',NOW+900)
        self.cycle(NOW+900,batch(self.rows,NOW+900))
        self.assertEqual(self.store.setup_status()['states'],{'unavailable':1})

    def test_missing_feed_pauses_once_then_expiry_closes(self):
        self.start()
        data=SetupBatch(END+300,errors={'hl_candles:BTC':'network_failure'})
        self.assertEqual(len(self.cycle(NOW+300,data)),1)
        self.assertEqual(self.cycle(NOW+360,data),[])
        self.cycle(NOW+3600,None)
        self.assertEqual(self.store.setup_status()['states'],{'expired':1})

    def test_thin_book_blocks_entries_but_not_invalidation(self):
        track=self.arm()
        self.rows=self.next_bar(track,'retest',NOW+600)
        data=batch(self.rows,NOW+600);data.books['BTC']['bid_depth_usd']=100
        self.cycle(NOW+600,data)
        self.assertEqual(self.store.active_setups()[0]['stage'],'armed')
        self.rows=self.next_bar(track,'stop',NOW+900)
        self.cycle(NOW+900,batch(self.rows,NOW+900,False))
        self.assertEqual(self.store.setup_status()['states'],{'invalidated':1})

    def test_targets_still_tracked_without_book(self):
        track=self.trigger()
        self.rows=self.next_bar(track,'hold',NOW+900)
        self.cycle(NOW+900,batch(self.rows,NOW+900,False))
        self.rows=self.next_bar(track,'target1',NOW+1200)
        self.cycle(NOW+1200,batch(self.rows,NOW+1200,False))
        self.assertEqual(self.store.active_setups()[0]['stage'],'target_1')

    def test_missing_optional_sources_do_not_fabricate_context(self):
        data=batch(self.rows,NOW)
        data.errors={'okx_candles:BTC':'http_429','coinbase_spot:BTC':'http_403'}
        self.cycle(NOW,data)
        status=self.store.setup_status()
        self.assertEqual(status['active'],1)
        self.assertEqual(status['health']['status'],'ready')
        self.assertEqual(len(status['health']['optional_issues']),2)
        self.assertIn('Unavailable context', next(e['text'] for e in self.store.export_events() if e['kind']=='setup'))

    def test_revised_closed_candle_keeps_original_and_suppresses_new_use(self):
        self.start()
        changed=list(self.rows);changed[-1]=replace(changed[-1],close=101.6)
        self.cycle(NOW+30,batch(changed,NOW+30))
        self.assertEqual(self.store.setup_candles('hyperliquid','BTC',NOW+30)[-1].close,101.65)
        self.assertEqual(self.store.setup_status()['health']['primary_issues']['BTC'],'closed_candle_revised')

    def test_first_receipt_gating_and_queue_supersession(self):
        track=self.start(receipt=False)
        self.rows=self.next_bar(track,'break',NOW+300)
        self.cycle(NOW+300,batch(self.rows,NOW+300))
        rows=self.store.db.execute('''SELECT d.status FROM deliveries d JOIN setup_events s ON s.event_id=d.event_id''').fetchall()
        self.assertEqual([r[0] for r in rows],['expired'])

    def test_new_route_cannot_inherit_setup(self):
        track=self.start()
        changed=Route('discord','paid','https://discord.com/api/webhooks/456/new-test')
        self.rows=self.next_bar(track,'break',NOW+300)
        self.cycle(NOW+300,batch(self.rows,NOW+300),routes=[changed])
        count=self.store.db.execute('SELECT COUNT(*) FROM deliveries WHERE route=?',(changed.name,)).fetchone()[0]
        self.assertEqual(count,0)

    def test_frozen_parameters_and_shadow_mode(self):
        cfg=replace(self.cfg,setup_publish=False)
        track=self.start(receipt=False,config=cfg)
        self.rows=self.next_bar(track,'break',NOW+300)
        self.cycle(NOW+300,batch(self.rows,NOW+300),replace(self.cfg,setup_breakout_volume_ratio=5.0))
        self.assertEqual(self.store.active_setups()[0]['stage'],'armed')
        count=self.store.db.execute('''SELECT COUNT(*) FROM deliveries WHERE event_id IN (SELECT event_id FROM setup_events)''').fetchone()[0]
        self.assertEqual(count,0)

    def test_archive_transaction_rolls_back_candles_state_and_outbox(self):
        with patch.object(self.store,'link_setup_event',side_effect=RuntimeError('test rollback')):
            with self.assertRaises(RuntimeError):
                self.cycle(NOW,batch(self.rows,NOW))
        self.assertEqual(self.store.setup_status()['candles'],0)
        self.assertEqual(self.store.setup_status()['active'],0)
        self.assertEqual(self.store.export_events(),[])

    def test_disabled_setup_closes_state_and_withdraws_pending(self):
        self.start(receipt=False)
        self.cycle(NOW+60,None,replace(self.cfg,setup_enabled=False))
        self.assertEqual(self.store.setup_status()['states'],{'cancelled':1})
        count=self.store.db.execute("SELECT COUNT(*) FROM deliveries WHERE status='pending' AND event_id IN (SELECT event_id FROM setup_events)").fetchone()[0]
        self.assertEqual(count,0)

    def test_asof_reads_reject_history_not_yet_received(self):
        with self.store.db:self.store.add_setup_candles(self.rows)
        self.assertEqual(self.store.setup_candles('hyperliquid','BTC',END),[])

    def test_readonly_cli_does_not_collect_or_dispatch(self):
        self.start()
        output=io.StringIO()
        with patch('market_watch.__main__.collect_setup_data') as collect, patch('market_watch.__main__.dispatch') as send, contextlib.redirect_stdout(output):
            self.assertEqual(main(['--database',self.path,'setups','--limit','1']),0)
        collect.assert_not_called();send.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['active'],1)

    def test_no_setup_when_live_midpoint_has_already_broken_invalidation(self):
        data=batch(self.rows,NOW)
        data.books['BTC']=book(100.4,NOW)
        self.assertEqual(self.cycle(NOW,data),[])

    def test_unknown_original_is_quarantined_not_retried_or_inherited(self):
        track=self.start(receipt=False)
        with self.store.db:
            self.store.db.execute("UPDATE deliveries SET status='unknown' WHERE event_id=?",(track['id'],))
        self.rows=self.next_bar(track,'break',NOW+300)
        self.cycle(NOW+300,batch(self.rows,NOW+300))
        states=[r[0] for r in self.store.db.execute('''SELECT status FROM deliveries
            WHERE event_id IN (SELECT event_id FROM setup_events)''')]
        self.assertEqual(states,['unknown'])

    def test_target_in_bar_overlapping_card_issuance_has_unknown_timing(self):
        track=self.trigger()
        self.rows=self.next_bar(track,'target1',NOW+900)
        events=self.cycle(NOW+900,batch(self.rows,NOW+900))
        self.assertEqual(self.store.setup_status()['states'],{'ambiguous':1})
        self.assertIn('overlaps card issuance',events[0]['text'])

    def test_monitor_deadline_is_separate_from_entry_expiry(self):
        track=self.trigger()
        self.assertEqual(self.cycle(NOW+3700,None),[])
        self.assertEqual(self.store.active_setups()[0]['stage'],'triggered')
        events=self.cycle(track['triggered_at']+24*3600,None)
        self.assertEqual(len(events),1)
        self.assertIn('not an instruction to close',events[0]['text'])

    def test_shadow_withdraws_terminal_pending_card_too(self):
        track=self.trigger()
        self.rows=self.next_bar(track,'stop',NOW+900)
        self.cycle(NOW+900,batch(self.rows,NOW+900))
        self.cycle(NOW+960,None,replace(self.cfg,setup_publish=False))
        count=self.store.db.execute("SELECT COUNT(*) FROM deliveries WHERE status='pending' AND event_id IN (SELECT event_id FROM setup_events)").fetchone()[0]
        self.assertEqual(count,0)

    def test_failed_cycle_does_not_mark_poll_complete(self):
        with self.store.db:self.store.set_meta('setup_poll',{'close':END,'at':NOW,'complete':False})
        with patch.object(self.store,'record_cycle',side_effect=RuntimeError('rollback')):
            with self.assertRaises(RuntimeError):self.cycle(NOW,batch(self.rows,NOW))
        self.assertFalse(self.store.get_meta('setup_poll')['complete'])

    def test_schema_two_readonly_then_nondestructive_migration(self):
        from market_watch.models import Event
        with self.store.db:
            self.store.add_event(Event('legacy','alert','paid',NOW,NOW+300,'legacy text',{}),[])
            self.store.db.execute('DROP TABLE setup_events')
            self.store.db.execute('DROP TABLE setups')
            self.store.db.execute('DROP TABLE setup_candles')
            self.store.db.execute('DROP TABLE setup_samples')
            self.store.db.execute('PRAGMA user_version=2')
        self.store.close()
        old=Store(self.path,readonly=True)
        try:
            self.assertEqual(old.setup_status()['health']['status'],'not_installed')
            self.assertEqual(old.db.execute('PRAGMA user_version').fetchone()[0],2)
        finally:old.close()
        self.store=Store(self.path)
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0],3)
        self.assertEqual(self.store.export_events()[0]['text'],'legacy text')


class SetupSourceTests(unittest.TestCase):
    def test_all_preview_cards_are_valid_and_fit_telegram(self):
        items=examples()
        self.assertEqual(len(items),12)
        for item in items:
            with self.subTest(kind=item['kind']):
                validate_presentation(item['presentation'])
                self.assertLess(len(item['text'].encode('utf-16-le'))//2,3900)
                self.assertTrue(item['text'].startswith('DEMO'))
        page=preview_html(items)
        self.assertIn('Know the setup. Follow the thesis.',page)
        self.assertNotIn('fetch(',page)

    def test_explicit_mode_change_preserves_config_and_creates_exact_backup(self):
        from market_watch.config import load_config
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json'
            original='{"assets":["BTC"],"cooldown_minutes":77,"okx_region":"us"}\n'
            path.write_text(original)
            result=set_mode(path,'live')
            cfg=load_config(path)
            self.assertTrue(cfg.setup_enabled and cfg.setup_publish)
            self.assertEqual(cfg.cooldown_minutes,77)
            self.assertEqual(cfg.okx_region,'us')
            self.assertEqual(Path(result['backup']).read_text(),original)
            result=set_mode(path,'shadow')
            self.assertFalse(load_config(path).setup_publish)
            self.assertTrue(load_config(path).setup_enabled)

    def test_closed_candles_ohlcv_and_okx_base_units(self):
        c=history()[-1]
        hl={'s':'BTC','i':'5m','t':c.open_at*1000,'T':c.close_at*1000-1,
            'o':str(c.open),'h':str(c.high),'l':str(c.low),'c':str(c.close),'v':'100'}
        row=[str(int(c.open_at*1000)),str(c.open),str(c.high),str(c.low),str(c.close),'9999','100','10165','1']
        a=parse_hl_candles([hl],'BTC',NOW)
        b=parse_okx_candles({'code':'0','data':[row]},'BTC',NOW)
        self.assertEqual(a[0].volume_base,b[0].volume_base)
        self.assertEqual(b[0].volume_base,100)
        self.assertEqual(parse_hl_candles([hl],'BTC',END+2),[])
        row[-1]='0';self.assertEqual(parse_okx_candles({'code':'0','data':[row]},'BTC',NOW),[])
        with self.assertRaises(ValueError):parse_hl_candles([hl,hl],'BTC',NOW)
        with self.assertRaises(ValueError):parse_hl_candles([{**hl,'s':'ETH'}],'BTC',NOW)
        with self.assertRaises(ValueError):parse_hl_candles([{**hl,'h':'99'}],'BTC',NOW)
        with self.assertRaises(ValueError):parse_hl_candles([{**hl,'v':'NaN'}],'BTC',NOW)

    def test_book_timestamp_order_depth_band_and_crossed_market(self):
        payload={'coin':'BTC','time':NOW*1000,'levels':[
            [{'px':'99.99','sz':'100'},{'px':'99.80','sz':'10000'}],
            [{'px':'100.01','sz':'100'},{'px':'100.20','sz':'10000'}]]}
        parsed=parse_book(payload,'BTC',NOW)
        self.assertAlmostEqual(parsed['bid_depth_usd'],9999)
        self.assertAlmostEqual(parsed['ask_depth_usd'],10001)
        self.assertTrue(parsed['depth_is_partial'])
        with self.assertRaises(ValueError):parse_book(payload,'BTC',NOW+100)
        with self.assertRaises(ValueError):parse_book({**payload,'coin':'SOL'},'BTC',NOW)
        payload['levels'][0].reverse()
        with self.assertRaises(ValueError):parse_book(payload,'BTC',NOW)

    def test_coinbase_units_and_missing_timezone(self):
        payload={'price':'100','bid':'99.9','ask':'100.1','volume':'123',
                 'time':datetime.fromtimestamp(NOW,timezone.utc).isoformat()}
        parsed=parse_spot(payload,'BTC',NOW)
        self.assertEqual(parsed['instrument'],'BTC-USD')
        self.assertEqual(parsed['volume_base_24h'],123)
        with self.assertRaises(ValueError):parse_spot(payload,'BTC',NOW+121)
        with self.assertRaises(ValueError):parse_spot({**payload,'time':'2026-10-04T12:00:00'},'BTC',NOW)

    def test_config_rejects_unsafe_parameters(self):
        for values in ({'setup_enabled':1},{'setup_history_bars':10},{'setup_max_delay_seconds':999},
                       {'setup_max_spread_bps':float('nan')},{'setup_version':'made-up'},
                       {'setup_enabled':True,'venues':('okx',),'minimum_venues':1}):
            with self.subTest(values=values),self.assertRaises(ValueError):Config(**values)

    def test_poll_scheduling_and_backoff_bound_requests(self):
        class Client:
            def __init__(self):self.calls=[]
            def call(self,url,payload=None):
                self.calls.append(url)
                raise RemoteError('http_429',retry_after=900)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(str(Path(tmp)/'state.sqlite3'));client=Client()
            cfg=Config(assets=('BTC',),setup_enabled=True)
            try:
                data=collect_setup_data(cfg,client,store,lambda:NOW)
                self.assertEqual(len(data.errors),4)
                self.assertIsNone(collect_setup_data(cfg,client,store,lambda:NOW+30))
                count=len(client.calls)
                collect_setup_data(cfg,client,store,lambda:NOW+65)
                self.assertEqual(len(client.calls),count)
                self.assertEqual(expected_close(END+2),END-300)
            finally:store.close()


if __name__ == '__main__':
    unittest.main()
