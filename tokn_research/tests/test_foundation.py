"""Synthetic M0 specification tests; no market data, estimators or orders."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import math
import unittest

from tokn_research.contracts import (
    Bar, ContractError, FeatureResult, Provenance, RecordRef, SeriesKey, TrainingManifest,
)
from tokn_research.data.asof import SyntheticArchive
from tokn_research.data.capabilities import Available, Capability, NotAvailable
from tokn_research.research.leakage import check_forward_shift, check_prefix_invariance
from tokn_research.simulation.clock import ReplayClock
from tokn_research.simulation.replay import InvalidRun, replay


# These names, prices and ten-second intervals are fixture values, not approved
# instruments, timeframes, risk limits or strategy parameters.
ZERO = datetime(2001, 1, 1, tzinfo=timezone.utc)
SECOND = timedelta(seconds=1)
SERIES = SeriesKey('fixture-venue', 'TEST/Q', 'spot', 'TEST', 'Q', 'Q', 10)


def stamp(seconds):
    return ZERO + timedelta(seconds=seconds)


def bar(index, close=10.0, *, revision=0, received=None, available=None, **changes):
    received = stamp(index * 10 + 10.2) if received is None else received
    available = received if available is None else available
    values = dict(
        schema_version=1, series=SERIES,
        event_open=stamp(index * 10), event_close=stamp((index + 1) * 10),
        received_at=received, available_at=available,
        open=10.0, high=max(10.0, close) + 1, low=min(10.0, close) - 1,
        close=close, volume=2.0, volume_unit='base',
        provenance=Provenance('synthetic:fixture', 'bar-' + str(index), revision, 'synthetic'),
        quality_flags=(),
    )
    values.update(changes)
    return Bar(**values)


def fixture_archive():
    return SyntheticArchive(tuple(bar(i, c) for i, c in enumerate((10, 30, 20, 40))))


def marker(context):
    last = context.bars[-1]
    known_at = last.available_at
    if context.training is not None:
        known_at = max(known_at, context.training.manifest.fit_completed_at)
    return FeatureResult({'fixture_marker': last.close}, known_at, (last.ref,))


def diagnostic(values):
    return 'above-fixture-threshold' if dict(values)['fixture_marker'] >= 25 else 'below-fixture-threshold'


def trace(archive=None, decisions=(11, 21, 31, 41), feature=marker, training=None):
    return replay(
        archive or fixture_archive(), SERIES, tuple(stamp(t) for t in decisions),
        feature, feature_id='synthetic:last-close-marker-v1', training=training,
    )


def manifest(**changes):
    values = dict(
        artifact_id='synthetic:training-metadata-only', training_start=stamp(0),
        training_end=stamp(20), fit_completed_at=stamp(22),
        transform_fitted_through=stamp(20), label_available_through=stamp(21),
        evidence_kind='synthetic',
    )
    values.update(changes)
    return TrainingManifest(**values)


class ContractTests(unittest.TestCase):
    def test_requires_explicit_series_and_interval(self):
        with self.assertRaises(TypeError):
            SeriesKey()
        for interval in (0, -1, True, 1.5):
            with self.subTest(interval=interval), self.assertRaises(ContractError):
                replace(SERIES, interval_seconds=interval)

    def test_series_rejects_missing_identity_and_unknown_contract_kind(self):
        for change in ({'instrument': ''}, {'venue': ' '}, {'contract_kind': 'made-up'}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                replace(SERIES, **change)

    def test_timezones_normalize_to_utc(self):
        row = bar(0)
        shifted = replace(row, event_open=row.event_open.astimezone(timezone(timedelta(hours=3))))
        self.assertEqual(row, shifted)
        self.assertEqual(shifted.event_open.tzinfo, timezone.utc)

    def test_naive_times_and_wrong_interval_rejected(self):
        for change in ({'event_open': ZERO.replace(tzinfo=None)}, {'event_close': stamp(11)}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                bar(0, **change)

    def test_receipt_and_availability_cannot_precede_close_or_each_other(self):
        for change in (
            {'received_at': stamp(9), 'available_at': stamp(10)},
            {'received_at': stamp(11), 'available_at': stamp(10.5)},
        ):
            with self.subTest(change=change), self.assertRaises(ContractError):
                bar(0, **change)

    def test_missing_receipt_is_preserved_without_fabricated_timestamp(self):
        row = bar(0, received_at=None, available_at=None)
        self.assertIsNone(row.received_at)
        self.assertIsNone(row.available_at)
        with self.assertRaises(ContractError):
            replace(row, available_at=stamp(11))

    def test_price_volume_unit_and_schema_validation(self):
        bad = ({'close': math.nan}, {'high': math.inf}, {'low': 0}, {'volume': -1},
               {'close': True}, {'high': 5}, {'low': 11}, {'volume_unit': 'usd'},
               {'schema_version': 2}, {'schema_version': True})
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ContractError):
                bar(0, **change)

    def test_synthetic_scope_is_enforced(self):
        with self.assertRaises(ContractError):
            Provenance('external', 'row', 0, 'observed')
        with self.assertRaises(ContractError):
            replace(bar(0).provenance, revision=-1)

    def test_contracts_own_immutable_values(self):
        flags = ['fixture-quality-warning']
        row = bar(0, quality_flags=flags)
        flags.clear()
        self.assertEqual(row.quality_flags, ('fixture-quality-warning',))
        with self.assertRaises(FrozenInstanceError):
            row.close = 20
        values = {'fixture_marker': 10}
        feature = FeatureResult(values, stamp(11), (row.ref,))
        values['fixture_marker'] = 900
        self.assertEqual(feature.values, (('fixture_marker', 10.0),))

    def test_reconstructed_reference_requires_valid_synthetic_lineage_and_interval(self):
        valid = bar(0).ref
        malformed = (
            {'provenance': None}, {'series': 'not-a-series'},
            {'event_open': stamp(100)}, {'event_close': stamp(11)},
            {'event_open': ZERO.replace(tzinfo=None)},
        )
        for change in malformed:
            with self.subTest(change=change), self.assertRaises(ContractError):
                replace(valid, **change)

    def test_reconstructed_reference_normalizes_aware_timezones(self):
        ref = bar(0).ref
        converted = replace(ref, event_open=ref.event_open.astimezone(timezone(timedelta(hours=3))))
        self.assertEqual(converted, ref)
        self.assertEqual(converted.event_open.tzinfo, timezone.utc)


class AvailabilityTests(unittest.TestCase):
    def test_only_strictly_prior_received_and_available_closed_bars_are_visible(self):
        row = bar(0, received=stamp(11), available=stamp(12))
        archive = SyntheticArchive((row,))
        for cutoff in (stamp(9), stamp(10), stamp(11), stamp(12)):
            with self.subTest(cutoff=cutoff):
                self.assertIsInstance(archive.as_of(SERIES, cutoff), NotAvailable)
        result = archive.as_of(SERIES, stamp(12.001))
        self.assertIsInstance(result, Available)
        self.assertEqual(result.bars, (row,))
        self.assertEqual(result.evidence_kind, 'synthetic')

    def test_missing_receipts_are_not_substituted_with_event_time(self):
        archive = SyntheticArchive((bar(0, received_at=None, available_at=None),))
        result = archive.as_of(SERIES, stamp(100))
        self.assertIsInstance(result, NotAvailable)
        self.assertIn('NO_CAUSALLY_AVAILABLE_BARS', result.reasons)

    def test_empty_archive_and_unknown_series_are_not_available(self):
        self.assertIsInstance(SyntheticArchive(()).as_of(SERIES, stamp(11)), NotAvailable)
        self.assertIsInstance(fixture_archive().as_of(replace(SERIES, venue='another-fixture'), stamp(41)), NotAvailable)

    def test_unsupported_series_never_appear_as_zero_measurements(self):
        archive = fixture_archive()
        reports = archive.capabilities(SERIES, stamp(41))
        self.assertIsInstance(reports[Capability.CLOSED_BARS], Available)
        for capability in Capability:
            if capability is Capability.CLOSED_BARS:
                continue
            with self.subTest(capability=capability):
                result = reports[capability]
                self.assertIsInstance(result, NotAvailable)
                self.assertIn('UNSUPPORTED_IN_M0', result.reasons)
                self.assertFalse(hasattr(result, 'values'))
                self.assertEqual(result.evidence_kind, 'synthetic')

    def test_two_candle_venues_do_not_create_tick_capability(self):
        other = replace(bar(0), series=replace(SERIES, venue='fixture-venue-2'),
                        provenance=Provenance('synthetic:second-venue', 'bar-0', 0, 'synthetic'))
        archive = SyntheticArchive((bar(0), other))
        self.assertIsInstance(archive.capabilities(SERIES, stamp(11))[Capability.TWO_VENUE_TICKS], NotAvailable)

    def test_quality_flags_are_a_restriction_not_silent_clean_data(self):
        result = SyntheticArchive((bar(0, quality_flags=('gap',)),)).as_of(SERIES, stamp(11))
        self.assertIsInstance(result, NotAvailable)
        self.assertIn('QUALITY_FLAGGED_BARS', result.reasons)

    def test_exact_duplicate_receipts_are_idempotent(self):
        row = bar(0)
        result = SyntheticArchive((row, row)).as_of(SERIES, stamp(11))
        self.assertEqual(result.bars, (row,))

    def test_conflicting_same_revision_is_rejected(self):
        with self.assertRaisesRegex(ContractError, 'CONFLICTING_REVISION'):
            SyntheticArchive((bar(0), bar(0, 12)))

    def test_revisions_only_replace_a_bar_after_their_receipt(self):
        first = bar(0)
        revision = bar(0, 12, revision=1, received=stamp(31))
        archive = SyntheticArchive((revision, first))
        self.assertEqual(archive.as_of(SERIES, stamp(30)).bars, (first,))
        self.assertEqual(archive.as_of(SERIES, stamp(31)).bars, (first,))
        self.assertEqual(archive.as_of(SERIES, stamp(32)).bars, (revision,))

    def test_flagged_revision_cannot_fall_back_to_old_clean_data(self):
        archive = SyntheticArchive((bar(0), bar(0, 12, revision=1, received=stamp(12), quality_flags=('incomplete',))))
        self.assertIsInstance(archive.as_of(SERIES, stamp(13)), NotAvailable)

    def test_unrelated_clean_revision_cannot_replace_flagged_lineage(self):
        first = bar(0, quality_flags=('gap',))
        for source, record in (('synthetic:unrelated', 'bar-0'),
                               ('synthetic:fixture', 'unrelated-record'),
                               ('synthetic:unrelated', 'unrelated-record')):
            replacement = replace(bar(0, 12, revision=1, received=stamp(12)),
                                  provenance=Provenance(source, record, 1, 'synthetic'))
            with self.subTest(source=source, record=record), self.assertRaisesRegex(ContractError, 'REVISION_LINEAGE_MISMATCH'):
                SyntheticArchive((first, replacement))

    def test_record_identity_cannot_be_reused_for_another_bar_interval(self):
        first = bar(0)
        for revision in (0, 1):
            second = replace(bar(1), provenance=replace(first.provenance, revision=revision))
            with self.subTest(revision=revision), self.assertRaisesRegex(ContractError, 'RECORD_IDENTITY_REUSED'):
                SyntheticArchive((first, second))

    def test_record_identity_cannot_be_reused_for_another_series(self):
        first = bar(0)
        second = replace(first, series=replace(SERIES, venue='different-fixture'))
        with self.assertRaisesRegex(ContractError, 'RECORD_IDENTITY_REUSED'):
            SyntheticArchive((first, second))


class ClockAndReplayTests(unittest.TestCase):
    def test_clock_requires_explicit_time_and_cannot_rewind(self):
        with self.assertRaises(TypeError):
            ReplayClock()
        clock = ReplayClock(stamp(11))
        self.assertEqual(clock.now, stamp(11))
        clock.advance(stamp(12))
        clock.advance(stamp(12))
        with self.assertRaisesRegex(ContractError, 'CLOCK_REWIND'):
            clock.advance(stamp(11))
        with self.assertRaises(ContractError):
            clock.advance(datetime(2001, 1, 1))

    def test_clock_checkpoint_restore_is_explicit_and_repeatable(self):
        clock = ReplayClock(stamp(11))
        restored = ReplayClock.restore(clock.checkpoint())
        self.assertEqual(restored.now, clock.now)
        clock.advance(stamp(21))
        self.assertEqual(restored.now, stamp(11))

    def test_replay_returns_only_synthetic_feature_evidence(self):
        result = trace()
        self.assertEqual([dict(f.values)['fixture_marker'] for f in result.frames], [10, 30, 20, 40])
        self.assertEqual(result.evidence_kind, 'synthetic')
        self.assertEqual(result.scope, 'offline_foundation_diagnostic_only')
        self.assertFalse(hasattr(result, 'orders'))
        self.assertFalse(hasattr(result, 'pnl'))

    def test_replay_is_deterministic_and_input_order_independent(self):
        first = trace()
        again = trace(SyntheticArchive(tuple(reversed(tuple(bar(i, c) for i, c in enumerate((10, 30, 20, 40)))))))
        self.assertEqual(first, again)
        self.assertEqual(first.digest, again.digest)

    def test_decision_times_must_be_strictly_increasing_and_nonempty(self):
        for decisions in ((), (21, 11), (11, 11)):
            with self.subTest(decisions=decisions), self.assertRaises(InvalidRun):
                trace(decisions=decisions)

    def test_same_close_and_unknown_data_runs_are_rejected(self):
        with self.assertRaisesRegex(InvalidRun, 'NO_CAUSALLY_AVAILABLE_BARS'):
            trace(decisions=(10,))
        unknown = SyntheticArchive((bar(0, received_at=None, available_at=None),))
        with self.assertRaises(InvalidRun):
            trace(unknown, decisions=(11,))

    def test_feature_timestamp_at_or_after_decision_is_rejected(self):
        def future(context):
            last = context.bars[-1]
            return FeatureResult({'fixture_marker': last.close}, context.decision_at, (last.ref,))
        with self.assertRaisesRegex(InvalidRun, 'FEATURE_NOT_PRIOR'):
            trace(feature=future)

    def test_feature_timestamp_cannot_predate_its_sources(self):
        def earlier(context):
            last = context.bars[-1]
            return FeatureResult({'fixture_marker': last.close}, last.event_close, (last.ref,))
        with self.assertRaisesRegex(InvalidRun, 'FEATURE_BEFORE_SOURCE'):
            trace(feature=earlier)

    def test_future_source_reference_is_rejected(self):
        future_row = bar(1, 30)
        def future(context):
            return FeatureResult({'fixture_marker': 30}, stamp(10.5), (future_row.ref,))
        with self.assertRaisesRegex(InvalidRun, 'SOURCE_NOT_IN_CAUSAL_WINDOW'):
            trace(feature=future)

    def test_invalid_feature_numbers_and_empty_provenance_rejected(self):
        for values, refs in (({'x': math.nan}, (bar(0).ref,)), ({'x': True}, (bar(0).ref,)), ({}, (bar(0).ref,)), ({'x': 1}, ())):
            with self.subTest(values=values), self.assertRaises(ContractError):
                FeatureResult(values, stamp(11), refs)

    def test_failed_callback_returns_no_partially_valid_run(self):
        def broken(context):
            if context.decision_at >= stamp(21):
                raise ValueError('synthetic callback failure')
            return marker(context)
        with self.assertRaisesRegex(InvalidRun, 'FEATURE_CALLBACK_FAILED'):
            trace(feature=broken)

    def test_reconstructed_frame_cannot_hide_invalid_causal_timestamp(self):
        first = trace().frames[0]
        with self.assertRaisesRegex(ContractError, 'FRAME_NOT_CAUSAL'):
            replace(first, available_at=first.decision_at)

    def test_reconstructed_trace_rejects_empty_reversed_and_wrong_series(self):
        original = trace()
        for change in ({'frames': ()}, {'frames': tuple(reversed(original.frames))},
                       {'series': replace(SERIES, venue='different-fixture')}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                replace(original, **change)

    def test_frame_digests_must_match_declared_sources(self):
        first = trace().frames[0]
        for digests in ((), ('not-a-digest',), (first.source_digests[0], first.source_digests[0])):
            with self.subTest(digests=digests), self.assertRaises(ContractError):
                replace(first, source_digests=digests)


class TrainingIsolationTests(unittest.TestCase):
    def test_training_slice_excludes_later_bars(self):
        training = fixture_archive().training_slice(SERIES, manifest())
        self.assertEqual([b.event_close for b in training.bars], [stamp(10), stamp(20)])
        result = trace(decisions=(31, 41), training=training)
        self.assertTrue(all(f.training_digest == training.digest for f in result.frames))

    def test_fit_must_finish_strictly_before_its_first_use(self):
        training = fixture_archive().training_slice(SERIES, manifest())
        for decision in (21, 22):
            with self.subTest(decision=decision), self.assertRaisesRegex(InvalidRun, 'FIT_NOT_PRIOR'):
                trace(decisions=(decision,), training=training)

    def test_training_transform_and_label_cutoffs_are_validated(self):
        bad = ({'training_end': stamp(23)}, {'transform_fitted_through': stamp(21)},
               {'label_available_through': stamp(22)}, {'training_start': stamp(20)})
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ContractError):
                manifest(**change)

    def test_late_training_receipt_is_excluded_not_backdated(self):
        archive = SyntheticArchive((bar(0), bar(1, 30, received=stamp(40))))
        training = archive.training_slice(SERIES, manifest())
        self.assertEqual(len(training.bars), 1)
        self.assertEqual(training.bars[0].event_close, stamp(10))

    def test_no_causal_training_data_rejects_the_run(self):
        archive = SyntheticArchive((bar(0, received_at=None, available_at=None),))
        with self.assertRaisesRegex(ContractError, 'NO_CAUSAL_TRAINING_BARS'):
            archive.training_slice(SERIES, manifest())

    def test_future_poisoning_does_not_change_training_fingerprint(self):
        before = fixture_archive().training_slice(SERIES, manifest())
        poisoned = SyntheticArchive((bar(0), bar(1, 30), bar(2, 999), bar(3, 888),
                                     bar(0, 333, revision=1, received=stamp(50))))
        after = poisoned.training_slice(SERIES, manifest())
        self.assertEqual(before, after)
        self.assertEqual(before.digest, after.digest)

    def test_training_from_another_series_is_rejected(self):
        other = replace(SERIES, instrument='OTHER/Q', base_asset='OTHER')
        archive = SyntheticArchive((replace(bar(0), series=other),))
        training = archive.training_slice(other, manifest())
        with self.assertRaisesRegex(InvalidRun, 'TRAINING_SERIES_MISMATCH'):
            trace(decisions=(31,), training=training)


class LeakageTests(unittest.TestCase):
    def test_one_bar_forward_shift_changes_diagnostic_path(self):
        result = check_forward_shift(trace(), diagnostic)
        self.assertEqual(result.changed_indices, (0, 1, 2))
        self.assertEqual(len(result.original), 3)
        self.assertEqual(result.shifted, ('above-fixture-threshold', 'below-fixture-threshold', 'above-fixture-threshold'))
        self.assertEqual(result.evidence_kind, 'synthetic')
        self.assertFalse(result.establishes_no_leakage)

    def test_constant_candidate_is_invalid_not_a_false_pass(self):
        with self.assertRaisesRegex(InvalidRun, 'SHIFT_NO_EFFECT'):
            check_forward_shift(trace(), lambda values: 'constant-fixture-output')

    def test_stateful_diagnostic_cannot_fake_forward_shift_sensitivity(self):
        calls = []
        def stateful(values):
            calls.append(values)
            return 'even-call' if len(calls) % 2 == 0 else 'odd-call'
        with self.assertRaisesRegex(InvalidRun, 'SHIFT_DIAGNOSTIC_NONDETERMINISTIC'):
            check_forward_shift(trace(), stateful)

    def test_pairwise_stable_call_order_cannot_fake_shift_sensitivity(self):
        calls = []
        def pairwise_stable(values):
            label = 'call-group-' + str(len(calls) // 2)
            calls.append(values)
            return label
        with self.assertRaisesRegex(InvalidRun, 'SHIFT_DIAGNOSTIC_NONDETERMINISTIC'):
            check_forward_shift(trace(), pairwise_stable)

    def test_malformed_reference_cannot_enter_an_accepted_shift_trace(self):
        with self.assertRaises(ContractError):
            original = trace()
            frames = tuple(replace(frame, source_refs=(RecordRef(
                SERIES, stamp(100), frame.anchor_close, None,
            ),)) for frame in original.frames)
            check_forward_shift(replace(original, frames=frames), diagnostic)

    def test_changing_source_metadata_alone_is_not_feature_sensitivity(self):
        archive = SyntheticArchive(tuple(bar(i, 10) for i in range(4)))
        with self.assertRaisesRegex(InvalidRun, 'SHIFT_NO_EFFECT'):
            check_forward_shift(trace(archive), diagnostic)

    def test_feature_independent_negative_control_is_rejected_as_expected(self):
        # This models the sensitivity property of B0, not a buy/hold strategy.
        with self.assertRaisesRegex(InvalidRun, 'SHIFT_NO_EFFECT'):
            check_forward_shift(trace(), lambda values: 'feature-independent-control')

    def test_shift_requires_actual_adjacent_bars_not_next_arbitrary_snapshot(self):
        for decisions in ((11,), (11, 12), (11, 31)):
            with self.subTest(decisions=decisions), self.assertRaisesRegex(InvalidRun, 'SHIFT_'):
                check_forward_shift(trace(decisions=decisions), diagnostic)

    def test_prefix_invariance_with_future_append_and_revision(self):
        prefix = SyntheticArchive((bar(0), bar(1, 30)))
        suffix = SyntheticArchive((bar(0), bar(1, 30), bar(2, 999),
                                   bar(0, 777, revision=1, received=stamp(40))))
        before = trace(prefix, decisions=(11, 21))
        after = trace(suffix, decisions=(11, 21, 31))
        self.assertEqual(before.frames, after.frames[:2])
        self.assertTrue(check_prefix_invariance(before, after))

    def test_prefix_check_rejects_deliberately_leaky_callback(self):
        # A callback can lie or close over outside data; this control catches
        # this representative future-data dependency, not every possible lie.
        def leak(value):
            def fn(context):
                last = context.bars[-1]
                return FeatureResult({'fixture_marker': value}, last.available_at, (last.ref,))
            return fn
        before = trace(decisions=(11, 21), feature=leak(30))
        poisoned = trace(decisions=(11, 21, 31), feature=leak(999))
        with self.assertRaisesRegex(InvalidRun, 'PREFIX_CHANGED'):
            check_prefix_invariance(before, poisoned)

    def test_prefix_check_cannot_compare_different_feature_identity(self):
        before = trace(decisions=(11, 21))
        changed = replace(trace(), feature_id='synthetic:different-marker-v2')
        with self.assertRaisesRegex(InvalidRun, 'INCOMPARABLE_TRACE'):
            check_prefix_invariance(before, changed)


if __name__ == '__main__':
    unittest.main()
