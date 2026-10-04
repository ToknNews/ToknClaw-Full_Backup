"""Explicit immutable contracts for the synthetic offline foundation.

Metadata is a declaration, not proof that a caller supplied truthful data. M0
accepts only explicitly synthetic provenance and implements no fitted model.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math


class ContractError(ValueError):
    """Malformed or inconsistent evidence; do not substitute a benign value."""


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractError('AWARE_TIMESTAMP_REQUIRED')
    return value.astimezone(timezone.utc)


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ContractError('NONEMPTY_IDENTITY_REQUIRED')
    return value


def integer(value, *, minimum):
    if type(value) is not int or value < minimum:
        raise ContractError('INVALID_INTEGER')
    return value


def numeric(value, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError('FINITE_NUMERIC_MEASUREMENT_REQUIRED')
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ContractError('FINITE_NUMERIC_MEASUREMENT_REQUIRED') from exc
    if not math.isfinite(result) or (positive and result <= 0) or (nonnegative and result < 0):
        raise ContractError('INVALID_MEASUREMENT')
    return result


def fingerprint(value):
    def encode(item):
        if isinstance(item, datetime):
            return utc(item).isoformat(timespec='microseconds')
        raise TypeError('Unsupported fingerprint value')
    payload = json.dumps(value, default=encode, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class SeriesKey:
    venue: str
    instrument: str
    contract_kind: str
    base_asset: str
    quote_asset: str
    settlement_asset: str
    interval_seconds: int

    def __post_init__(self):
        for name in ('venue', 'instrument', 'base_asset', 'quote_asset', 'settlement_asset'):
            text(getattr(self, name))
        if self.contract_kind not in ('spot', 'linear_perpetual', 'inverse_perpetual', 'dated_future'):
            raise ContractError('UNKNOWN_CONTRACT_KIND')
        integer(self.interval_seconds, minimum=1)


@dataclass(frozen=True)
class Provenance:
    source_id: str
    record_id: str
    revision: int
    evidence_kind: str

    def __post_init__(self):
        text(self.source_id)
        text(self.record_id)
        integer(self.revision, minimum=0)
        if self.evidence_kind != 'synthetic':
            raise ContractError('M0_SYNTHETIC_EVIDENCE_ONLY')


@dataclass(frozen=True)
class RecordRef:
    series: SeriesKey
    event_open: datetime
    event_close: datetime
    provenance: Provenance


@dataclass(frozen=True)
class Bar:
    schema_version: int
    series: SeriesKey
    event_open: datetime
    event_close: datetime
    received_at: datetime | None
    available_at: datetime | None
    open: float
    high: float
    low: float
    close: float
    volume: float
    volume_unit: str
    provenance: Provenance
    quality_flags: tuple[str, ...]

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ContractError('UNSUPPORTED_BAR_SCHEMA')
        if not isinstance(self.series, SeriesKey) or not isinstance(self.provenance, Provenance):
            raise ContractError('EXPLICIT_SERIES_AND_PROVENANCE_REQUIRED')
        for name in ('event_open', 'event_close'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        if (self.event_close - self.event_open).total_seconds() != self.series.interval_seconds:
            raise ContractError('BAR_INTERVAL_MISMATCH')
        if (self.received_at is None) != (self.available_at is None):
            raise ContractError('RECEIPT_AND_AVAILABILITY_MUST_BOTH_BE_KNOWN_OR_MISSING')
        if self.received_at is not None:
            object.__setattr__(self, 'received_at', utc(self.received_at))
            object.__setattr__(self, 'available_at', utc(self.available_at))
            if not self.event_close <= self.received_at <= self.available_at:
                raise ContractError('INVALID_RECEIPT_AVAILABILITY_ORDER')
        for name in ('open', 'high', 'low', 'close'):
            object.__setattr__(self, name, numeric(getattr(self, name), positive=True))
        object.__setattr__(self, 'volume', numeric(self.volume, nonnegative=True))
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ContractError('INVALID_OHLC_RANGE')
        if self.volume_unit != 'base':
            raise ContractError('M0_REQUIRES_EXPLICIT_BASE_VOLUME')
        if isinstance(self.quality_flags, str):
            raise ContractError('QUALITY_FLAGS_MUST_BE_A_SEQUENCE')
        object.__setattr__(self, 'quality_flags', tuple(text(flag) for flag in self.quality_flags))

    @property
    def ref(self):
        return RecordRef(self.series, self.event_open, self.event_close, self.provenance)

    @property
    def digest(self):
        return fingerprint(asdict(self))


@dataclass(frozen=True)
class TrainingManifest:
    """Synthetic fit/transform/label timing declarations; does not train a model."""

    artifact_id: str
    training_start: datetime
    training_end: datetime
    fit_completed_at: datetime
    transform_fitted_through: datetime
    label_available_through: datetime
    evidence_kind: str

    def __post_init__(self):
        text(self.artifact_id)
        if self.evidence_kind != 'synthetic':
            raise ContractError('M0_SYNTHETIC_EVIDENCE_ONLY')
        for name in ('training_start', 'training_end', 'fit_completed_at',
                     'transform_fitted_through', 'label_available_through'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        if not self.training_start < self.training_end < self.fit_completed_at:
            raise ContractError('INVALID_TRAINING_FIT_ORDER')
        if not self.training_start <= self.transform_fitted_through <= self.training_end:
            raise ContractError('TRANSFORM_OUTSIDE_TRAINING_WINDOW')
        if self.label_available_through >= self.fit_completed_at:
            raise ContractError('LABEL_NOT_PRIOR_TO_FIT')


@dataclass(frozen=True)
class TrainingSlice:
    series: SeriesKey
    manifest: TrainingManifest
    bars: tuple[Bar, ...]

    def __post_init__(self):
        if not isinstance(self.series, SeriesKey) or not isinstance(self.manifest, TrainingManifest):
            raise ContractError('INVALID_TRAINING_CONTRACT')
        object.__setattr__(self, 'bars', tuple(self.bars))
        if not self.bars:
            raise ContractError('NO_CAUSAL_TRAINING_BARS')
        last_close = None
        for row in self.bars:
            if not isinstance(row, Bar) or row.series != self.series:
                raise ContractError('TRAINING_SERIES_MISMATCH')
            if not self.manifest.training_start <= row.event_open < row.event_close <= self.manifest.training_end:
                raise ContractError('ROW_OUTSIDE_TRAINING_WINDOW')
            if row.available_at is None or row.available_at >= self.manifest.fit_completed_at:
                raise ContractError('TRAINING_ROW_NOT_KNOWN_AT_FIT')
            if row.quality_flags:
                raise ContractError('QUALITY_FLAGGED_TRAINING_BAR')
            if last_close is not None and row.event_open < last_close:
                raise ContractError('OVERLAPPING_TRAINING_BARS')
            last_close = row.event_close

    @property
    def digest(self):
        return fingerprint(asdict(self))


@dataclass(frozen=True)
class FeatureResult:
    """Diagnostic feature values with declared timing and exact source refs."""

    values: Mapping[str, float] | tuple[tuple[str, float], ...]
    available_at: datetime
    source_refs: tuple[RecordRef, ...]

    def __post_init__(self):
        items = self.values.items() if isinstance(self.values, Mapping) else self.values
        try:
            pairs = tuple(sorted((text(name), numeric(value)) for name, value in items))
        except (TypeError, ValueError) as exc:
            raise ContractError('INVALID_FEATURE_VALUES') from exc
        if not pairs or len({name for name, _ in pairs}) != len(pairs):
            raise ContractError('NONEMPTY_UNIQUE_FEATURES_REQUIRED')
        object.__setattr__(self, 'values', pairs)
        object.__setattr__(self, 'available_at', utc(self.available_at))
        refs = tuple(self.source_refs)
        if not refs or any(not isinstance(ref, RecordRef) for ref in refs) or len(set(refs)) != len(refs):
            raise ContractError('NONEMPTY_UNIQUE_SOURCE_REFS_REQUIRED')
        object.__setattr__(self, 'source_refs', refs)
