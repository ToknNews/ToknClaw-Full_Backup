#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — MARKET INTELLIGENCE ENGINE
# ============================================================
#
# ████████╗ ██████╗ ██╗  ██╗███╗   ██╗ ██████╗██╗      █████╗ ██╗    ██╗
# ╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║██╔════╝██║     ██╔══██╗██║    ██║
#    ██║   ██║   ██║█████╔╝ ██╔██╗ ██║██║     ██║     ███████║██║ █╗ ██║
#    ██║   ██║   ██║██╔═██╗ ██║╚██╗██║██║     ██║     ██╔══██║██║███╗██║
#    ██║   ╚██████╔╝██║  ██╗██║ ╚████║╚██████╗███████╗██║  ██║╚███╔███╔╝
#    ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
#
# SYSTEM: ToknClaw Intelligence Layer
# MODULE: oi_price_trend
# PURPOSE: Combine local price history and open interest history to emit
#          continuation and unwind trend signals for tradable perp assets.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This collector is designed to:
• consume rolling price history for majors + midcaps
• consume rolling open interest history for majors + midcaps
• detect aligned price/OI continuation trends
• detect price/OI unwind conditions
• emit modular trend signals for trade_signal_engine
• remain additive and OpenClaw agent ready

Primary Config
--------------
/opt/toknclaw/config/oi_price_trend_collector.json

Primary Inputs
--------------
/opt/toknclaw/data/token_price_history.json
/opt/toknclaw/data/flow/open_interest_history.json

Primary Outputs
---------------
• perp_trend_bullish
• perp_trend_bearish
• perp_trend_short_unwind
• perp_trend_long_unwind
• perp_trend_summary
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import json
import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from signal_engine.collectors.registry import register_collector
from signal_engine.models.signal import Signal
from signal_engine.runtime_config import load_config

# ---------------------------------------------------
# PATHS / CONFIG
# ---------------------------------------------------

CONFIG_FILE = "oi_price_trend_collector.json"
PRICE_HISTORY_PATH = Path("/opt/toknclaw/data/token_price_history.json")
OI_HISTORY_PATH = Path("/opt/toknclaw/data/flow/open_interest_history.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "tracked_entities": [
        "BTC",
        "ETH",
        "SOL",
        "BNB",
        "XRP",
        "DOGE",
        "LINK",
        "AVAX",
        "ARB",
        "OP",
        "INJ",
        "PYTH",
        "JUP",
        "RNDR",
    ],
    "require_tracked_entity": True,
    "min_history_points": 2,
    "min_price_change_pct": 0.25,
    "min_oi_change_pct": 0.75,
    "strong_price_change_pct": 1.0,
    "strong_oi_change_pct": 2.0,
    "emit_base_trend_rows": True,
    "max_signals_per_run": 100,
    "summary_top_n": 8,
}

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def clean_upper(value: Any) -> str:
    return clean_text(value).upper()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[OI PRICE TREND] {message}")


def info_log(message: str) -> None:
    print(f"[OI PRICE TREND] {message}")


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return deepcopy(DEFAULT_CONFIG)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)

    tracked = merged.get("tracked_entities")
    if not isinstance(tracked, list):
        merged["tracked_entities"] = deepcopy(DEFAULT_CONFIG["tracked_entities"])
    else:
        merged["tracked_entities"] = [clean_upper(x) for x in tracked if clean_text(x)]

    return merged


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_price_history() -> Dict[str, Any]:
    data = read_json(PRICE_HISTORY_PATH, {"tokens": {}})
    if not isinstance(data, dict):
        return {"tokens": {}}
    if not isinstance(data.get("tokens"), dict):
        data["tokens"] = {}
    return data


def load_oi_history() -> Dict[str, Any]:
    data = read_json(OI_HISTORY_PATH, {"symbols": {}})
    if not isinstance(data, dict):
        return {"symbols": {}}
    if not isinstance(data.get("symbols"), dict):
        data["symbols"] = {}
    return data


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


def get_recent_points(series: List[Dict[str, Any]], count: int) -> Optional[List[Dict[str, Any]]]:
    valid = [row for row in safe_list(series) if isinstance(row, dict)]
    if len(valid) < count:
        return None
    return valid[-count:]


def latest_entity_set(price_history: Dict[str, Any], oi_history: Dict[str, Any]) -> List[str]:
    price_entities = {clean_upper(k) for k in safe_dict(price_history.get("tokens")).keys()}
    oi_entities = {clean_upper(k) for k in safe_dict(oi_history.get("symbols")).keys()}
    return sorted(price_entities & oi_entities)

# ---------------------------------------------------
# SIGNAL BUILDERS
# ---------------------------------------------------

def build_base_trend_signal(
    entity: str,
    price_change_pct: float,
    oi_change_pct: float,
    trend_type: str,
    strength: str,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type=f"perp_trend_{trend_type}",
        entity=entity,
        title=f"{entity} perp trend {trend_type.replace('_', ' ')}",
        summary=(
            f"price_change_pct={price_change_pct:.4f} | "
            f"oi_change_pct={oi_change_pct:.4f} | "
            f"trend_type={trend_type} | "
            f"strength={strength}"
        ),
        confidence=0.82 if strength == "strong" else 0.74,
        sentiment_score=0.0,
        raw_url=None,
    )


def build_summary_signal(
    rows: List[Dict[str, Any]],
    bullish_count: int,
    bearish_count: int,
    short_unwind_count: int,
    long_unwind_count: int,
    summary_top_n: int,
) -> Signal:
    ranked = sorted(
        rows,
        key=lambda x: abs(safe_float(x.get("price_change_pct"), 0.0)) + abs(safe_float(x.get("oi_change_pct"), 0.0)),
        reverse=True,
    )

    top_parts: List[str] = []
    for row in ranked[:summary_top_n]:
        top_parts.append(
            f"{row['entity']}({row['trend_type']}|p={row['price_change_pct']:.2f}%|oi={row['oi_change_pct']:.2f}%)"
        )

    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_trend_summary",
        entity="PERP_TREND",
        title="Perpetual trend summary",
        summary=(
            f"rows={len(rows)} | "
            f"bullish={bullish_count} | "
            f"bearish={bearish_count} | "
            f"short_unwind={short_unwind_count} | "
            f"long_unwind={long_unwind_count} | "
            f"top_trends={', '.join(top_parts) if top_parts else 'none'}"
        ),
        confidence=0.84,
        sentiment_score=0.0,
        raw_url=None,
    )

# ---------------------------------------------------
# MAIN COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="oi_price_trend",
    priority=1,
    tags=["flows", "perps", "trend", "price", "oi", "continuation", "unwind"],
    category="flows",
    execution="fast",
)
def fetch_oi_price_trend_signals() -> List[Signal]:
    started = time.time()
    cfg = load_engine_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        info_log("disabled by config")
        return signals

    price_history = load_price_history()
    oi_history = load_oi_history()

    price_tokens = safe_dict(price_history.get("tokens"))
    oi_symbols = safe_dict(oi_history.get("symbols"))

    if not price_tokens:
        info_log("no price history found")
        return signals

    if not oi_symbols:
        info_log("no OI history found")
        return signals

    tracked = set(cfg.get("tracked_entities", []))
    require_tracked = bool(cfg.get("require_tracked_entity", True))
    min_history_points = safe_int(cfg.get("min_history_points", 2), 2)

    min_price_change_pct = safe_float(cfg.get("min_price_change_pct", 0.25), 0.25)
    min_oi_change_pct = safe_float(cfg.get("min_oi_change_pct", 0.75), 0.75)
    strong_price_change_pct = safe_float(cfg.get("strong_price_change_pct", 1.0), 1.0)
    strong_oi_change_pct = safe_float(cfg.get("strong_oi_change_pct", 2.0), 2.0)

    emit_base_rows = bool(cfg.get("emit_base_trend_rows", True))
    max_signals = safe_int(cfg.get("max_signals_per_run", 100), 100)

    bullish_count = 0
    bearish_count = 0
    short_unwind_count = 0
    long_unwind_count = 0

    trend_rows: List[Dict[str, Any]] = []

    for entity in latest_entity_set(price_history, oi_history):
        if require_tracked and entity not in tracked:
            continue

        price_series = safe_list(price_tokens.get(entity))
        oi_series = safe_list(oi_symbols.get(entity))

        lookback = max(min_history_points, 5)

        price_points = get_recent_points(price_series, lookback)
        oi_points = get_recent_points(oi_series, lookback)

        if not price_points or not oi_points:
            continue

        prior_price = safe_float(price_points[-2].get("price_usd"), 0.0)
        current_price = safe_float(price_points[-1].get("price_usd"), 0.0)

        prior_oi = safe_float(oi_points[0].get("avg_oi"), 0.0)
        current_oi = safe_float(oi_points[-1].get("avg_oi"), 0.0)

        if prior_price <= 0 or current_price <= 0 or prior_oi <= 0 or current_oi <= 0:
            continue

        price_change_pct = pct_change(current_price, prior_price)
        oi_change_pct = pct_change(current_oi, prior_oi)

        abs_price = abs(price_change_pct)
        abs_oi = abs(oi_change_pct)

        if abs_price < min_price_change_pct or abs_oi < min_oi_change_pct:
            continue

        trend_type = None

        if price_change_pct > 0 and oi_change_pct > 0:
            trend_type = "bullish"
            bullish_count += 1
        elif price_change_pct < 0 and oi_change_pct > 0:
            trend_type = "bearish"
            bearish_count += 1
        elif price_change_pct > 0 and oi_change_pct < 0:
            trend_type = "short_unwind"
            short_unwind_count += 1
        elif price_change_pct < 0 and oi_change_pct < 0:
            trend_type = "long_unwind"
            long_unwind_count += 1

        if not trend_type:
            continue

        strength = "strong" if abs_price >= strong_price_change_pct and abs_oi >= strong_oi_change_pct else "normal"

        trend_rows.append(
            {
                "entity": entity,
                "price_change_pct": price_change_pct,
                "oi_change_pct": oi_change_pct,
                "trend_type": trend_type,
                "strength": strength,
            }
        )

        if emit_base_rows:
            signals.append(
                build_base_trend_signal(
                    entity=entity,
                    price_change_pct=price_change_pct,
                    oi_change_pct=oi_change_pct,
                    trend_type=trend_type,
                    strength=strength,
                )
            )

        if len(signals) >= max_signals:
            break

    signals.append(
        build_summary_signal(
            rows=trend_rows,
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            short_unwind_count=short_unwind_count,
            long_unwind_count=long_unwind_count,
            summary_top_n=safe_int(cfg.get("summary_top_n", 8), 8),
        )
    )

    runtime = round(time.time() - started, 2)
    debug_log(
        cfg,
        f"price_entities={len(price_tokens)} oi_entities={len(oi_symbols)} "
        f"trend_rows={len(trend_rows)} bullish={bullish_count} bearish={bearish_count} "
        f"short_unwind={short_unwind_count} long_unwind={long_unwind_count} "
        f"signals_returned={len(signals)} runtime={runtime}s"
    )

    return signals[:max_signals]


# ---------------------------------------------------
# DIRECT TEST MODE
# ---------------------------------------------------

if __name__ == "__main__":
    rows = fetch_oi_price_trend_signals()
    print("count:", len(rows))
    for row in rows[:20]:
        print(
            getattr(row, "signal_type", None),
            getattr(row, "entity", None),
            getattr(row, "summary", None),
        )
