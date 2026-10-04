"""Causal synthetic feature replay. Callbacks are trusted local test code.

This validates declared provenance, not arbitrary Python behavior. It is not
an OS sandbox and cannot prove a callback did not lie or consult outside data.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import re

from ..contracts import (
    Bar, ContractError, FeatureResult, RecordRef, SeriesKey, TrainingSlice,
    fingerprint, text, utc,
)
from ..data.asof import SyntheticArchive
from ..data.capabilities import NotAvailable
from .clock import ReplayClock


class InvalidRun(ContractError):
    """Rejected diagnostic; no partially valid result is returned."""


@dataclass(frozen=True)
class ReplayContext:
    decision_at: datetime
    bars: tuple[Bar, ...]
    training: TrainingSlice | None


@dataclass(frozen=True)
class FeatureFrame:
    decision_at: datetime
    anchor_open: datetime
    anchor_close: datetime
    values: tuple[tuple[str, float], ...]
    available_at: datetime
    source_refs: tuple[RecordRef, ...]
    source_digests: tuple[str, ...]
    training_digest: str | None

    def __post_init__(self):
        for name in ('decision_at', 'anchor_open', 'anchor_close', 'available_at'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        result = FeatureResult(self.values, self.available_at, self.source_refs)
        object.__setattr__(self, 'values', result.values)
        object.__setattr__(self, 'source_refs', result.source_refs)
        if (not self.anchor_open < self.anchor_close < self.decision_at
                or self.available_at >= self.decision_at
                or any(ref.event_close > min(self.anchor_close, self.available_at) for ref in self.source_refs)):
            raise ContractError('FRAME_NOT_CAUSAL')
        digests = tuple(self.source_digests)
        if len(digests) != len(self.source_refs):
            raise ContractError('SOURCE_DIGEST_COUNT_MISMATCH')
        for digest in digests + (() if self.training_digest is None else (self.training_digest,)):
            if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
                raise ContractError('INVALID_EVIDENCE_DIGEST')
        object.__setattr__(self, 'source_digests', digests)


@dataclass(frozen=True)
class ReplayTrace:
    series: SeriesKey
    feature_id: str
    frames: tuple[FeatureFrame, ...]
    evidence_kind: str = field(default='synthetic', init=False)
    scope: str = field(default='offline_foundation_diagnostic_only', init=False)

    def __post_init__(self):
        text(self.feature_id)
        if not isinstance(self.series, SeriesKey):
            raise ContractError('EXPLICIT_TRACE_SERIES_REQUIRED')
        frames = tuple(self.frames)
        if not frames or any(not isinstance(frame, FeatureFrame) for frame in frames):
            raise ContractError('NONEMPTY_FEATURE_FRAMES_REQUIRED')
        if any(left.decision_at >= right.decision_at for left, right in zip(frames, frames[1:])):
            raise ContractError('STRICTLY_INCREASING_DECISIONS_REQUIRED')
        for frame in frames:
            if ((frame.anchor_close - frame.anchor_open).total_seconds() != self.series.interval_seconds
                    or any(ref.series != self.series for ref in frame.source_refs)):
                raise ContractError('TRACE_SERIES_MISMATCH')
        object.__setattr__(self, 'frames', frames)

    @property
    def digest(self):
        return fingerprint(asdict(self))


def replay(archive, series, decision_times, feature, *, feature_id, training=None):
    if not isinstance(archive, SyntheticArchive) or not isinstance(series, SeriesKey):
        raise InvalidRun('SYNTHETIC_ARCHIVE_AND_EXPLICIT_SERIES_REQUIRED')
    text(feature_id)
    times = tuple(utc(value) for value in decision_times)
    if not times or any(left >= right for left, right in zip(times, times[1:])):
        raise InvalidRun('STRICTLY_INCREASING_DECISIONS_REQUIRED')
    if training is not None:
        if not isinstance(training, TrainingSlice):
            raise InvalidRun('INVALID_TRAINING_CONTRACT')
        if training.series != series:
            raise InvalidRun('TRAINING_SERIES_MISMATCH')
        if training.manifest.fit_completed_at >= times[0]:
            raise InvalidRun('FIT_NOT_PRIOR')
    clock = ReplayClock(times[0])
    frames = []
    for decision in times:
        clock.advance(decision)
        window = archive.as_of(series, clock.now)
        if isinstance(window, NotAvailable):
            raise InvalidRun(','.join(window.reasons))
        context = ReplayContext(clock.now, window.bars, training)
        try:
            result = feature(context)
        except Exception as exc:
            raise InvalidRun('FEATURE_CALLBACK_FAILED') from exc
        if not isinstance(result, FeatureResult):
            raise InvalidRun('FEATURE_RESULT_CONTRACT_REQUIRED')
        if result.available_at >= clock.now:
            raise InvalidRun('FEATURE_NOT_PRIOR')
        by_ref = {row.ref: row for row in window.bars}
        if any(ref not in by_ref for ref in result.source_refs):
            raise InvalidRun('SOURCE_NOT_IN_CAUSAL_WINDOW')
        source_rows = tuple(by_ref[ref] for ref in result.source_refs)
        known_at = max(row.available_at for row in source_rows)
        if training is not None:
            known_at = max(known_at, training.manifest.fit_completed_at)
        if result.available_at < known_at:
            raise InvalidRun('FEATURE_BEFORE_SOURCE')
        anchor = window.bars[-1]
        frames.append(FeatureFrame(
            clock.now, anchor.event_open, anchor.event_close, result.values,
            result.available_at, result.source_refs, tuple(row.digest for row in source_rows),
            None if training is None else training.digest,
        ))
    return ReplayTrace(series, feature_id, tuple(frames))
