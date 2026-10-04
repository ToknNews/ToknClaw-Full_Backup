"""Immutable synthetic archive with strict knowledge-time visibility."""

from dataclasses import dataclass

from ..contracts import Bar, ContractError, SeriesKey, TrainingManifest, TrainingSlice, utc
from .capabilities import Available, Capability, NotAvailable


@dataclass(frozen=True)
class SyntheticArchive:
    bars: tuple[Bar, ...]

    def __post_init__(self):
        unique = {}
        lineage_by_event = {}
        event_by_lineage = {}
        for row in self.bars:
            if not isinstance(row, Bar):
                raise ContractError('SYNTHETIC_BAR_REQUIRED')
            event = (row.series, row.event_open, row.event_close)
            lineage = (row.provenance.source_id, row.provenance.record_id)
            if event in lineage_by_event and lineage_by_event[event] != lineage:
                raise ContractError('REVISION_LINEAGE_MISMATCH')
            if lineage in event_by_lineage and event_by_lineage[lineage] != event:
                raise ContractError('RECORD_IDENTITY_REUSED')
            lineage_by_event[event] = lineage
            event_by_lineage[lineage] = event
            key = (event, row.provenance.revision)
            if key in unique and unique[key] != row:
                raise ContractError('CONFLICTING_REVISION')
            unique[key] = row
        object.__setattr__(self, 'bars', tuple(sorted(unique.values(), key=lambda row: row.digest)))

    def _known(self, series, cutoff):
        if not isinstance(series, SeriesKey):
            raise ContractError('EXPLICIT_SERIES_REQUIRED')
        cutoff = utc(cutoff)
        latest = {}
        for row in self.bars:
            if row.series != series or row.available_at is None or row.available_at >= cutoff:
                continue
            # Bar guarantees close <= receipt <= availability. Filtering the
            # last timestamp strictly also excludes same-close execution.
            key = (row.event_open, row.event_close)
            prior = latest.get(key)
            if prior is None or row.provenance.revision > prior.provenance.revision:
                latest[key] = row
        rows = tuple(sorted(latest.values(), key=lambda row: row.event_close))
        for left, right in zip(rows, rows[1:]):
            if right.event_open < left.event_close:
                raise ContractError('OVERLAPPING_BARS')
        return rows

    def as_of(self, series, cutoff):
        rows = self._known(series, cutoff)
        if not rows:
            return NotAvailable(Capability.CLOSED_BARS, ('NO_CAUSALLY_AVAILABLE_BARS',))
        if any(row.quality_flags for row in rows):
            return NotAvailable(Capability.CLOSED_BARS, ('QUALITY_FLAGGED_BARS',))
        return Available(rows, cutoff)

    def capabilities(self, series, cutoff):
        return {
            capability: self.as_of(series, cutoff) if capability is Capability.CLOSED_BARS
            else NotAvailable(capability, ('UNSUPPORTED_IN_M0',))
            for capability in Capability
        }

    def training_slice(self, series, manifest):
        if not isinstance(manifest, TrainingManifest):
            raise ContractError('EXPLICIT_TRAINING_MANIFEST_REQUIRED')
        rows = tuple(row for row in self._known(series, manifest.fit_completed_at)
                     if manifest.training_start <= row.event_open and row.event_close <= manifest.training_end)
        return TrainingSlice(series, manifest, rows)
