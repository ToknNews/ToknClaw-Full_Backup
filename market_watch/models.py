"""Explicit units and timestamps; no LLM-generated measurements."""

from dataclasses import asdict, dataclass
import math
import hashlib


def number(value, *, positive=False):
    if value is None or isinstance(value, bool) or value == "":
        raise ValueError("missing numeric measurement")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError("invalid numeric measurement")
    return result


@dataclass(frozen=True)
class Observation:
    venue: str
    asset: str
    instrument: str
    observed_at: float
    fetched_at: float
    timestamp_basis: str
    mark_price: float
    oi_base: float
    oi_usd: float
    funding_rate: float
    funding_interval_hours: float

    def __post_init__(self):
        if self.venue not in {"okx", "hyperliquid"} or self.asset not in {"BTC", "ETH", "SOL"}:
            raise ValueError("unsupported instrument")
        for key in ("observed_at", "fetched_at", "mark_price", "oi_base", "oi_usd", "funding_interval_hours"):
            number(getattr(self, key), positive=True)
        number(self.funding_rate)
        if self.funding_interval_hours not in (1, 2, 4, 8):
            raise ValueError("unverified funding interval")
        if self.timestamp_basis not in {"exchange", "receipt"}:
            raise ValueError("invalid timestamp provenance")

    @property
    def quote_currency(self):
        return "USDT" if self.venue == "okx" else "USD"

    @property
    def funding_bps_8h(self):
        return self.funding_rate * 8 / self.funding_interval_hours * 10000

    def to_dict(self):
        return asdict(self)

    def fresh(self, now, max_age):
        return (-10 <= now - self.observed_at <= max_age
                and -10 <= now - self.fetched_at <= max_age)


@dataclass(frozen=True)
class Event:
    key: str
    kind: str
    audience: str
    created_at: float
    expires_at: float
    text: str
    evidence: dict


def event_id(key, created_at):
    return hashlib.sha256((key + ':' + str(created_at)).encode()).hexdigest()[:24]
