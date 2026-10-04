"""Synthetic archive evidence only. No network, operator records or delivery."""

import contextlib
from copy import deepcopy
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_watch.__main__ import main
from market_watch.config import Config
from market_watch.scorecard import instant, report
from market_watch.setup_costs import policy_for
from market_watch.storage import Store

START = instant('2026-10-04T12:00:00+00:00')
END = START + 3600


def spec(at, *, legacy=False, publish=False, fee=4.5):
    cfg = Config(setup_enabled=True, setup_publish=publish, setup_fee_bps_per_side=fee)
    result = {'version': 'breakout-retest-v1', 'asset': 'BTC', 'side': 'long',
              'venue': 'hyperliquid', 'instrument': 'BTC', 'quote': 'USD', 'timeframe': '5m',
              'created_at': at, 'trigger': 100., 'entry_limit': 100.1, 'invalidation': 99.,
              'target_1': 101.5, 'target_2': 102.5, 'atr': 1., 'reference_risk': 1.,
              'config': asdict(cfg)}
    if not legacy:
        result['cost_screen'] = {'policy': policy_for(cfg), 'reasons': [],
                                'at_trigger': {'target_2': {'net_rr': 2.0}},
                                'at_entry_limit': {'target_2': {'net_rr': 1.5}}}
    return result


class ScorecardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'archive.sqlite3'
        self.store = Store(str(self.path))
        self.addCleanup(self.store.close)
        self.specs, self.sequences = {}, {}

    def formation(self, name, at=START, **kwargs):
        self.specs[name], self.sequences[name] = spec(at, **kwargs), -1
        self.event(name, 'forming', at, 'range_edge_approach')
        return name

    def event(self, name, stage, at, reason='', **extra):
        self.sequences[name] += 1
        sequence = self.sequences[name]
        event_id = name if sequence == 0 else name + ':' + str(sequence)
        evidence = {'setup_id': name, 'stage': stage, 'sequence': sequence, 'checked_at': at,
                    'spec': deepcopy(self.specs[name]), 'reason': reason, **extra}
        with self.store.db:
            self.store.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                (event_id, 'fixture:'+event_id, 'setup' if sequence == 0 else 'setup_update',
                 'paid', at, at+120, 'SYNTHETIC FIXTURE', json.dumps(evidence)))
            if sequence == 0:
                # Deliberately later mutable state must not leak into cutoff reconstruction.
                self.store.db.execute('INSERT INTO setups VALUES (?,?,?,?,?,?)',
                                      (name, 'BTC', at, 'completed', END+1000, '{}'))
            self.store.link_setup_event(event_id, name, sequence)

    def triggered(self, name, at=START, **kwargs):
        self.formation(name, at, **kwargs)
        self.event(name, 'armed', at+300, 'volume_backed_breakout')
        self.event(name, 'triggered', at+600, 'retest_closed_and_quote_in_band',
                   execution_costs={'target_2': {'net_rr': 1.8}})

    def sample(self, close=START, at=None, screens=None, reasons=None, *, publish=False, policy=True):
        health = {'screen': screens or {'BTC': 'targets_do_not_cover_costs'},
                  'publishing': publish, 'primary_issues': {}, 'screen_details': {}}
        if policy:
            health['cost_policy'] = policy_for(Config())
        if reasons is not None:
            health['screen_details']['BTC'] = {'policy': health.get('cost_policy'), 'reasons': reasons}
        with self.store.db:
            self.store.setup_sample(at if at is not None else close+20,
                {'requested_close': close, 'health': health})

    def result(self, start=START, end=END, details=True):
        return report(self.path, start, end, 'America/New_York', details)

    def test_empty_archive_has_explicit_insufficient_sample_and_unknown_coverage(self):
        output = self.result()
        self.assertEqual(output['populations']['formed_in_window']['distinct_setups'], 0)
        self.assertEqual(output['populations']['formed_in_window']['sample_state'], 'insufficient_sample')
        self.assertEqual(output['screening']['coverage_by_observed_asset'], [])
        self.assertEqual(output['window']['cutoff_local'], '2026-10-04T09:00:00-04:00')

    def test_half_open_window_and_carry_in_do_not_consult_future_mutable_state(self):
        self.formation('old-closed', START-1000)
        self.event('old-closed', 'expired', START-1, 'entry_window_elapsed')
        self.formation('carry', START-100)
        self.event('carry', 'invalidated', START, 'setup_failed_before_trigger')
        self.formation('first', START)
        self.event('first', 'armed', END, 'volume_backed_breakout')
        self.formation('excluded-end', END)
        output = self.result()
        self.assertEqual(output['prior_closed_setups_outside_population'], 1)
        self.assertEqual(output['populations']['carry_in']['distinct_setups'], 1)
        self.assertEqual(output['populations']['formed_in_window']['distinct_setups'], 1)
        first = next(r for r in output['setups'] if r['setup_id'] == 'first')
        self.assertEqual(first['stage'], 'forming')
        self.assertEqual(first['first_stage_at'], {'forming': START})

    def test_legacy_and_cost_policies_and_frozen_assumptions_are_separate(self):
        self.formation('legacy', legacy=True)
        self.formation('v1')
        self.formation('different-fee', fee=5.)
        self.formation('live', publish=True)
        output = self.result()
        self.assertEqual(len(output['cohorts']), 3)
        self.assertEqual(output['populations']['formed_in_window']['distinct_setups'], 3)
        legacy = next(c for c in output['cohorts'] if c['cost_policy_version'] == 'legacy')
        self.assertIsNone(legacy['frozen_cost_policy'])
        self.assertIsNone(legacy['frozen_estimated_economics']['formation_target_2_net_rr']['median'])
        self.assertEqual(output['excluded_evidence'], [{'setup_id': 'live', 'reason': 'live_publication_intent'}])

    def test_repeated_updates_count_distinct_setups_and_confirmation_once(self):
        self.triggered('watch')
        self.event('watch', 'triggered', START+700, 'retest_closed_and_quote_in_band')
        self.event('watch', 'paused', START+800, 'book_unavailable')
        self.event('watch', 'resumed', START+900)
        self.event('watch', 'triggered', START+1000)
        summary = self.result()['populations']['formed_in_window']
        self.assertEqual(summary['distinct_setups'], 1)
        self.assertEqual(summary['breakout_confirmed_by_cutoff'], 1)
        self.assertEqual(summary['retest_confirmed_in_window'], 1)
        self.assertEqual(summary['after_retest']['active_at_cutoff'], 1)

    def test_pre_entry_failure_is_separate_from_target_one_then_invalidation(self):
        self.formation('pre')
        self.event('pre', 'invalidated', START+100, 'setup_failed_before_trigger')
        self.triggered('post')
        self.event('post', 'target_1', START+900, 'first_reference_target_touched')
        self.event('post', 'invalidated', START+1200, 'invalidation_touched')
        summary = self.result()['populations']['formed_in_window']
        self.assertEqual(summary['before_retest']['terminal_reasons'],
                         {'invalidated:setup_failed_before_trigger': 1})
        self.assertEqual(summary['after_retest']['terminal_reasons'], {'invalidated:invalidation_touched': 1})
        self.assertEqual(summary['target_1_then_invalidation'], 1)
        self.assertEqual(summary['target_2_event_observed'], 0)
        self.assertEqual(summary['sample_state'], 'descriptive_only')

    def test_ambiguity_gaps_paused_and_open_are_never_completed_outcomes(self):
        for name in ('ambiguous', 'gap', 'paused', 'open'):
            self.triggered(name)
        self.event('ambiguous', 'ambiguous', START+900, 'both_boundaries_same_bar')
        self.event('gap', 'unavailable', START+1200, 'missed_candle')
        self.event('paused', 'paused', START+900, 'closed_candle_missing_or_late')
        summary = self.result()['populations']['formed_in_window']
        self.assertEqual(summary['after_retest']['state_counts'], {'ambiguous': 1, 'unavailable': 1, 'triggered': 2})
        self.assertEqual(summary['after_retest']['checks_paused_at_cutoff'], 1)
        self.assertEqual(summary['observed_closed_retest_paths'], 0)
        self.assertEqual(summary['sample_state'], 'insufficient_sample')

    def test_carry_in_confirmation_denominators_and_future_terminal_cutoff(self):
        self.triggered('carry', START-1000)
        self.event('carry', 'completed', END+10, 'second_reference_target_touched')
        summary = self.result()['populations']['carry_in']
        self.assertEqual(summary['retest_confirmed_by_cutoff'], 1)
        self.assertEqual(summary['retest_confirmed_in_window'], 0)
        self.assertEqual(summary['after_retest']['state_counts'], {'triggered': 1})

    def test_frozen_estimates_are_read_verbatim_not_recomputed(self):
        self.triggered('estimated')
        with patch('market_watch.setup_costs.economics', side_effect=AssertionError('must not recompute')):
            output = self.result()
        economics = output['cohorts'][0]['frozen_estimated_economics']
        self.assertEqual(economics['formation_target_2_net_rr']['median'], 2.)
        self.assertEqual(economics['confirmation_target_2_net_rr']['median'], 1.8)
        self.assertEqual(output['setups'][0]['levels']['target_2'], 102.5)

    def test_retries_dedup_by_asset_bucket_and_cost_reasons_are_multilabel(self):
        self.sample(reasons=['targets_do_not_cover_costs', 'volatility_too_small'])
        self.sample(at=START+80, reasons=['targets_do_not_cover_costs', 'volatility_too_small', 'volatility_too_small'])
        self.sample(close=START+300, screens={'BTC': 'cooldown'})
        self.sample(close=START+600, screens={'BTC': 'forming'}, reasons=[])
        self.sample(close=START+900, screens={'ETH': 'book_unavailable'})
        output = self.result()['screening']
        self.assertEqual(output['raw_asset_attempts'], 5)
        self.assertEqual(output['distinct_asset_decision_buckets'], 4)
        self.assertEqual(output['superseded_retry_attempts'], 1)
        btc = next(c for c in output['cohorts'] if c['asset'] == 'BTC')
        self.assertEqual(btc['cost_screened_buckets'], 2)
        self.assertEqual(btc['cost_rejected_buckets'], 1)
        self.assertEqual(btc['multi_reason_counts'], {'targets_do_not_cover_costs': 1, 'volatility_too_small': 1})
        coverage = next(c for c in output['coverage_by_observed_asset'] if c['asset'] == 'BTC')
        self.assertEqual(coverage['expected_5m_buckets'], 12)
        self.assertEqual(coverage['unobserved_buckets'], 9)

    def test_last_retry_supersedes_rejection_and_future_retries_are_excluded(self):
        self.sample(reasons=['volatility_too_small'])
        self.sample(at=START+80, screens={'BTC': 'forming'}, reasons=[])
        self.sample(at=END, reasons=['volatility_too_small'])
        group = self.result()['screening']['cohorts'][0]
        self.assertEqual(group['cost_rejected_buckets'], 0)
        self.assertEqual(group['cost_accepted_buckets'], 1)

    def test_screen_policy_versions_live_buckets_and_window_boundary(self):
        self.sample(close=START-300, at=START+10)
        self.sample(policy=False)
        self.sample(close=START+300, reasons=['net_reward_risk_too_low'])
        self.sample(close=START+600, publish=True)
        self.sample(close=END, at=END+20)
        screening = self.result()['screening']
        self.assertEqual(screening['rows_for_decision_closes_outside_window'], 1)
        self.assertEqual(screening['live_buckets_excluded'], 1)
        self.assertEqual({c['policy_version'] for c in screening['cohorts']}, {'unrecorded', 'execution-costs-v1'})

    def test_missing_event_sequence_is_explicit_unavailable_evidence(self):
        self.triggered('broken')
        with self.store.db:
            self.store.db.execute('DELETE FROM setup_events WHERE setup_id=? AND sequence=1', ('broken',))
        output = self.result()
        self.assertEqual(output['populations']['formed_in_window']['evidence_unavailable'], 1)
        self.assertEqual(output['populations']['formed_in_window']['unknown_retest']['denominator_distinct_setups'], 1)
        self.assertEqual(output['setups'][0]['evidence_issues'], ['missing_or_inconsistent_event_sequence'])
        self.assertEqual(output['excluded_evidence'][0]['reason'], 'unlinked_setup_event')

    def test_documented_synthetic_example_totals(self):
        self.formation('fixture-pre')
        self.event('fixture-pre', 'invalidated', START+100, 'setup_failed_before_trigger')
        self.triggered('fixture-post')
        self.event('fixture-post', 'target_1', START+900, 'first_reference_target_touched')
        self.event('fixture-post', 'invalidated', START+1200, 'invalidation_touched')
        self.triggered('fixture-ambiguous', legacy=True)
        self.event('fixture-ambiguous', 'ambiguous', START+900, 'both_boundaries_same_bar')
        self.triggered('fixture-open')
        self.triggered('fixture-carry', START-1000)
        output = self.result()
        current = output['populations']['formed_in_window']
        self.assertEqual({k: current[k] for k in ('distinct_setups', 'breakout_confirmed_by_cutoff',
                          'retest_confirmed_by_cutoff', 'target_1_then_invalidation', 'sample_state')},
                         {'distinct_setups': 4, 'breakout_confirmed_by_cutoff': 3,
                          'retest_confirmed_by_cutoff': 3, 'target_1_then_invalidation': 1,
                          'sample_state': 'descriptive_only'})
        self.assertEqual(current['after_retest']['state_counts'], {'invalidated': 1, 'ambiguous': 1, 'triggered': 1})
        self.assertEqual(output['populations']['carry_in']['distinct_setups'], 1)

    def test_real_archive_writer_fixture_is_compatible_without_replaying_rules(self):
        from test_setups import history, batch, NOW
        from market_watch.service import run_cycle
        cfg = Config(assets=('BTC',), setup_enabled=True, setup_publish=False, summary_hours=())
        run_cycle(cfg, self.store, [], {}, [], NOW, batch(history(), NOW))
        output = self.result(NOW-30, NOW+1)
        self.assertEqual(output['populations']['formed_in_window']['distinct_setups'], 1)
        self.assertEqual(output['setups'][0]['evidence_issues'], [])
        self.assertEqual(output['cohorts'][0]['cost_policy_version'], 'execution-costs-v1')
        self.assertEqual(output['screening']['cohorts'][0]['cost_accepted_buckets'], 1)

    def test_report_preserves_all_archive_tables_and_files_and_cli_avoids_runtime(self):
        self.triggered('unchanged')
        self.sample(reasons=['volatility_too_small'])
        before = '\n'.join(self.store.db.iterdump())
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.path.parent.iterdir()}
        output = io.StringIO()
        args = ['--database', str(self.path), 'scorecard', '--start', '2026-10-04T12:00:00Z',
                '--end', '2026-10-04T13:00:00Z', '--timezone', 'UTC', '--details']
        with (contextlib.redirect_stdout(output),
                patch('market_watch.__main__.load_config', side_effect=AssertionError('runtime config')),
                patch('market_watch.__main__.Store', side_effect=AssertionError('write-capable Store')),
                patch('market_watch.__main__.JsonClient', side_effect=AssertionError('client')),
                patch('market_watch.__main__.collect', side_effect=AssertionError('collector')),
                patch('market_watch.__main__.collect_setup_data', side_effect=AssertionError('setup collector')),
                patch('market_watch.__main__.dispatch', side_effect=AssertionError('delivery'))):
            self.assertEqual(main(args), 0)
        self.assertEqual(json.loads(output.getvalue())['audience'], 'operator_only')
        self.assertEqual('\n'.join(self.store.db.iterdump()), before)
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.path.parent.iterdir()}, hashes)

    def test_consistent_snapshot_excludes_commit_between_report_queries(self):
        self.formation('initial')
        from market_watch import scorecard
        original = scorecard._screening
        def concurrent_write(db, start, end):
            self.sample(reasons=['volatility_too_small'])
            return original(db, start, end)
        with patch.object(scorecard, '_screening', side_effect=concurrent_write):
            output = self.result()
        self.assertEqual(output['screening']['distinct_asset_decision_buckets'], 0)
        self.assertEqual(self.result()['screening']['distinct_asset_decision_buckets'], 1)

    def test_missing_database_and_old_schema_are_never_created_or_migrated(self):
        missing = self.path.parent / 'missing.sqlite3'
        with self.assertRaisesRegex(ValueError, 'existing archive'):
            report(missing, START, END, 'UTC')
        self.assertFalse(missing.exists())
        with self.store.db:
            self.store.db.execute('PRAGMA user_version=2')
        with self.assertRaisesRegex(ValueError, 'no migration'):
            self.result()
        self.assertEqual(self.store.db.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_explicit_timezone_offset_and_bounded_window_validation(self):
        for value in ('2026-10-04', '2026-11-01T01:30:00', 'bad'):
            with self.assertRaises(ValueError):
                instant(value)
        self.assertEqual(instant('2026-11-01T01:30:00-05:00') - instant('2026-11-01T01:30:00-04:00'), 3600)
        for start, end, zone in [(END, START, 'UTC'), (START, END, 'bad/zone'),
                                 (float('nan'), END, 'UTC'), (START, START+366*86400, 'UTC')]:
            with self.assertRaises(ValueError):
                report(self.path, start, end, zone)

    def test_malformed_evidence_is_disclosed_without_inventing_outcomes(self):
        self.formation('bad-level')
        self.formation('bad-update')
        self.event('bad-update', 'invalidated', START+300, ['not-a-reason'])
        with self.store.db:
            row = self.store.db.execute('SELECT evidence FROM events WHERE id=?', ('bad-level',)).fetchone()
            data = json.loads(row[0])
            del data['spec']['trigger']
            self.store.db.execute('UPDATE events SET evidence=? WHERE id=?', (json.dumps(data), 'bad-level'))
            self.store.setup_sample(START+20, {'requested_close': START,
                'health': {'screen': {'BTC': 'forming'}, 'publishing': False, 'primary_issues': []}})
        output = self.result()
        self.assertEqual(output['excluded_evidence'], [{'setup_id': 'bad-level', 'reason': 'invalid_formation_evidence'}])
        self.assertEqual(output['populations']['formed_in_window']['sample_state'], 'insufficient_sample')
        self.assertEqual(output['populations']['formed_in_window']['unknown_retest']['state_counts'], {'evidence_unavailable': 1})
        self.assertEqual(output['screening']['invalid_sample_rows'], 1)

    def test_cli_requires_explicit_archive_and_never_reads_supplied_config(self):
        common = ['scorecard', '--start', '2026-10-04T12:00:00Z',
                  '--end', '2026-10-04T13:00:00Z', '--timezone', 'UTC']
        with contextlib.redirect_stderr(io.StringIO()), patch('market_watch.__main__.load_config', side_effect=AssertionError):
            self.assertEqual(main(common), 1)
            self.assertEqual(main(['--database', str(self.path), '--config', 'never-read.json', *common]), 1)


if __name__ == '__main__':
    unittest.main()
