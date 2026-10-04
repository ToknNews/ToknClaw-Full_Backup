"""Availability describes fixture records, never live coverage or model fitness."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..contracts import Bar, ContractError, utc


class Capability(str, Enum):
    CLOSED_BARS = 'closed_bars'
    SETTLED_FUNDING = 'settled_funding'
    SPOT_HEDGE = 'historical_spot_hedge'
    TRADE_PRINTS = 'trade_prints'
    LIQUIDATION_PRINTS = 'liquidation_prints'
    DEPTH_HISTORY = 'depth_history'
    TWO_VENUE_TICKS = 'synchronized_two_venue_ticks'
    FITTED_MODEL = 'fitted_model'


@dataclass(frozen=True)
class Available:
    bars: tuple[Bar, ...]
    as_of: datetime
    status: str = field(default='Available', init=False)
    evidence_kind: str = field(default='synthetic', init=False)
    scope: str = field(default='fixture_records_only', init=False)
    coverage: str = field(default='completeness_and_freshness_not_assessed', init=False)

    def __post_init__(self):
        object.__setattr__(self, 'bars', tuple(self.bars))
        object.__setattr__(self, 'as_of', utc(self.as_of))
        if not self.bars or any(not isinstance(row, Bar) for row in self.bars):
            raise ContractError('AVAILABLE_REQUIRES_BARS')
        if any(row.available_at is None or row.available_at >= self.as_of or row.quality_flags for row in self.bars):
            raise ContractError('AVAILABLE_REQUIRES_CAUSAL_UNFLAGGED_BARS')


@dataclass(frozen=True)
class NotAvailable:
    capability: Capability
    reasons: tuple[str, ...]
    status: str = field(default='NotAvailable', init=False)
    evidence_kind: str = field(default='synthetic', init=False)

    def __post_init__(self):
        object.__setattr__(self, 'reasons', tuple(self.reasons))
        if not isinstance(self.capability, Capability) or not self.reasons:
            raise ContractError('UNAVAILABILITY_REASON_REQUIRED')
