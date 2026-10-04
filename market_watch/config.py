"""Validated non-secret settings. Credentials belong only in the environment."""

from dataclasses import dataclass, fields
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Config:
    assets: tuple = ("BTC", "ETH", "SOL")
    venues: tuple = ("hyperliquid", "okx")
    minimum_venues: int = 2
    okx_region: str = "global"
    database: str = "market_watch/runtime/state.sqlite3"
    timezone: str = "America/New_York"
    summary_hours: tuple = (8, 20)
    free_summary_hour: int = 8
    summary_grace_minutes: int = 10
    max_age_seconds: int = 180
    baseline_tolerance_seconds: int = 180
    lookback_minutes: int = 15
    cooldown_minutes: int = 60
    max_alerts_per_hour: int = 6
    price_change_pct: float = 0.75
    oi_change_pct: float = 2.0
    funding_extreme_bps_8h: float = 3.0
    funding_spread_bps_8h: float = 2.0
    max_price_disagreement_pct: float = 2.0
    delivery_ttl_seconds: int = 600
    request_timeout_seconds: int = 10
    followup_enabled: bool = True
    followup_check_minutes: int = 5
    followup_horizon_minutes: int = 60
    followup_max_updates: int = 4
    rule_version: str = "market-watch-v1"
    setup_enabled: bool = False
    setup_publish: bool = False
    setup_coinbase_enabled: bool = True
    setup_range_bars: int = 12
    setup_atr_bars: int = 14
    setup_history_bars: int = 64
    setup_close_grace_seconds: int = 15
    setup_max_delay_seconds: int = 150
    setup_expiry_minutes: int = 60
    setup_tracking_hours: int = 24
    setup_cooldown_minutes: int = 60
    setup_max_new_per_hour: int = 3
    setup_breakout_volume_ratio: float = 1.2
    setup_max_spread_bps: float = 8.0
    setup_min_visible_depth_usd: float = 10000.0
    setup_version: str = "breakout-retest-v1"

    def __post_init__(self):
        if self.okx_region not in {"global", "us", "eea", "tr"}:
            raise ValueError("unsupported OKX API region")
        if not self.assets or set(self.assets) - {"BTC", "ETH", "SOL"}:
            raise ValueError("assets must be a nonempty subset of BTC, ETH, SOL")
        if len(set(self.assets)) != len(self.assets):
            raise ValueError("assets must be unique")
        if not self.venues or set(self.venues) - {"hyperliquid", "okx"}:
            raise ValueError("unsupported venues")
        if len(set(self.venues)) != len(self.venues):
            raise ValueError("venues must be unique")
        if type(self.minimum_venues) is not int or not 1 <= self.minimum_venues <= len(self.venues):
            raise ValueError("minimum_venues exceeds configured venues")
        for name in ("summary_grace_minutes", "max_age_seconds", "baseline_tolerance_seconds",
                     "lookback_minutes", "cooldown_minutes", "max_alerts_per_hour",
                     "delivery_ttl_seconds", "request_timeout_seconds"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(name + " must be a positive integer")
        for name in ("price_change_pct", "oi_change_pct", "funding_extreme_bps_8h",
                     "funding_spread_bps_8h", "max_price_disagreement_pct"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(name + " must be finite and positive")
        if type(self.followup_enabled) is not bool:
            raise ValueError('followup_enabled must be a boolean')
        for name in ('followup_check_minutes', 'followup_horizon_minutes', 'followup_max_updates'):
            if type(getattr(self, name)) is not int:
                raise ValueError(name + ' must be an integer')
        if not 1 <= self.followup_check_minutes < self.followup_horizon_minutes <= 240:
            raise ValueError('follow-up interval must be positive and shorter than a horizon of at most 240 minutes')
        if not 2 <= self.followup_max_updates <= 10:
            raise ValueError('followup_max_updates must be between 2 and 10')
        hours = (*self.summary_hours, self.free_summary_hour)
        if any(type(h) is not int or not 0 <= h <= 23 for h in hours):
            raise ValueError("summary hours must be integers from 0 to 23")
        if len(set(self.summary_hours)) != len(self.summary_hours):
            raise ValueError("summary hours must be unique")
        if self.summary_grace_minutes > 59 or self.request_timeout_seconds > 30:
            raise ValueError("summary grace or request timeout too large")
        if self.baseline_tolerance_seconds >= self.lookback_minutes * 60:
            raise ValueError("baseline tolerance must be shorter than lookback")
        if not isinstance(self.database, str) or not self.database or not self.rule_version:
            raise ValueError("database and rule_version are required")
        for name in ('setup_enabled', 'setup_publish', 'setup_coinbase_enabled'):
            if type(getattr(self, name)) is not bool:
                raise ValueError(name + ' must be a boolean')
        for name, lower, upper in (
                ('setup_range_bars', 6, 36), ('setup_atr_bars', 7, 28),
                ('setup_history_bars', 48, 200), ('setup_close_grace_seconds', 5, 30),
                ('setup_max_delay_seconds', 60, 180), ('setup_expiry_minutes', 15, 240),
                ('setup_tracking_hours', 1, 48), ('setup_cooldown_minutes', 15, 1440),
                ('setup_max_new_per_hour', 1, 6)):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(name + ' outside supported bounds')
        if self.setup_history_bars < max(self.setup_range_bars, self.setup_atr_bars, 20) + 2:
            raise ValueError('setup history must cover every full indicator window')
        for name, lower, upper in (('setup_breakout_volume_ratio', 1.0, 5.0),
                                   ('setup_max_spread_bps', 0.1, 50.0),
                                   ('setup_min_visible_depth_usd', 1000.0, 10000000.0)):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (float, int))
                    or not math.isfinite(value) or not lower <= value <= upper):
                raise ValueError(name + ' outside supported bounds')
        if self.setup_enabled and 'hyperliquid' not in self.venues:
            raise ValueError('setup v1 requires Hyperliquid as the fixed primary venue')
        if self.setup_version != 'breakout-retest-v1':
            raise ValueError('unsupported setup version')
        ZoneInfo(self.timezone)


def load_config(path=None):
    values = json.loads(Path(path).read_text()) if path else {}
    if not isinstance(values, dict):
        raise ValueError("configuration must be an object")
    if set(values) - {f.name for f in fields(Config)}:
        raise ValueError("unknown configuration setting")
    for key in ("assets", "venues", "summary_hours"):
        if key in values:
            if not isinstance(values[key], list):
                raise ValueError(key + " must be an array")
            values[key] = tuple(values[key])
    return Config(**values)
