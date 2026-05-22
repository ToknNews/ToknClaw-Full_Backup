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
# MODULE: open_interest_acceleration
# PURPOSE: Compute second-order open interest flow behavior from stored OI
#          history and emit acceleration / deceleration / unwind signals.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This collector is designed to:
• consume stored OI history from the ToknClaw flow layer
• derive current and prior OI percentage changes
• compute OI acceleration / deceleration
• emit build / unwind state signals for trading engines
• remain additive and OpenClaw agent ready

Primary Config
--------------
/opt/toknclaw/config/open_interest_acceleration_collector.json

Primary Input
-------------
/opt/toknclaw/data/flow/open_interest_history.json

Primary Outputs
---------------
• perp_open_interest_acceleration
• perp_open_interest_build_accelerating
• perp_open_interest_build_decelerating
• perp_open_interest_unwind_accelerating
• perp_open_interest_acceleration_summary
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

CONFIG_FILE = "open_interest_acceleration_collector.json"
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
    "min_history_points": 3,
    "min_valid_oi": 0.0,
    "build_threshold_pct": 1.5,
    "unwind_threshold_pct": -1.5,
    "acceleration_threshold_pct": 1.0,
    "strong_acceleration_threshold_pct": 3.0,
    "max_signals_per_run": 100,
    "summary_top_n": 8,
    "emit_base_acceleration_rows": True,
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


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[OI ACCELERATION] {message}")


def info_log(message: str) -> None:
    print(f"[OI ACCELERATION] {message}")


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


def load_history() -> Dict[str, Any]:
    data = read_json(
        OI_HISTORY_PATH,
        {
            "updated_at": None,
            "symbols": {},
        },
    )

    if not isinstance(data, dict):
        return {"updated_at": None, "symbols": {}}

    if not isinstance(data.get("symbols"), dict):
        data["symbols"] = {}

    return data


def base_asset(symbol: str) -> str:
    text = clean_text(symbol).upper()

    for suffix in ("USDT", "USDC", "BUSD", "USD"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[:-len(suffix)]

    return text


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


def get_recent_points(series: List[Dict[str, Any]], count: int) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(series, list):
        return None

    valid = [row for row in series if isinstance(row, dict)]
    if len(valid) < count:
        return None

    return valid[-count:]


# ---------------------------------------------------
# SIGNAL BUILDERS
# ---------------------------------------------------

def build_acceleration_signal(
    entity: str,
    current_change_pct: float,
    prior_change_pct: float,
    acceleration_pct: float,
    current_oi: float,
    prior_oi: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_open_interest_acceleration",
        entity=entity,
        title=f"{entity} open interest acceleration",
        summary=(
            f"current_change_pct={current_change_pct:.4f} | "
            f"prior_change_pct={prior_change_pct:.4f} | "
            f"acceleration_pct={acceleration_pct:.4f} | "
            f"current_oi={current_oi:.2f} | "
            f"prior_oi={prior_oi:.2f}"
        ),
        confidence=0.84,
        sentiment_score=0.0,
        raw_url=None,
    )


def build_build_accelerating_signal(
    entity: str,
    current_change_pct: float,
    prior_change_pct: float,
    acceleration_pct: float,
    strong: bool,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_open_interest_build_accelerating",
        entity=entity,
        title=f"{entity} OI build accelerating",
        summary=(
            f"{entity} positioning build is accelerating | "
            f"current_change_pct={current_change_pct:.4f} | "
            f"prior_change_pct={prior_change_pct:.4f} | "
            f"acceleration_pct={acceleration_pct:.4f} | "
            f"strength={'strong' if strong else 'normal'}"
        ),
        confidence=0.88 if strong else 0.80,
        sentiment_score=0.14,
        raw_url=None,
    )


def build_build_decelerating_signal(
    entity: str,
    current_change_pct: float,
    prior_change_pct: float,
    acceleration_pct: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_open_interest_build_decelerating",
        entity=entity,
        title=f"{entity} OI build decelerating",
        summary=(
            f"{entity} positioning build is decelerating | "
            f"current_change_pct={current_change_pct:.4f} | "
            f"prior_change_pct={prior_change_pct:.4f} | "
            f"acceleration_pct={acceleration_pct:.4f}"
        ),
        confidence=0.78,
        sentiment_score=-0.04,
        raw_url=None,
    )


def build_unwind_accelerating_signal(
    entity: str,
    current_change_pct: float,
    prior_change_pct: float,
    acceleration_pct: float,
    strong: bool,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_open_interest_unwind_accelerating",
        entity=entity,
        title=f"{entity} OI unwind accelerating",
        summary=(
            f"{entity} positioning unwind is accelerating | "
            f"current_change_pct={current_change_pct:.4f} | "
            f"prior_change_pct={prior_change_pct:.4f} | "
            f"acceleration_pct={acceleration_pct:.4f} | "
            f"strength={'strong' if strong else 'normal'}"
        ),
        confidence=0.88 if strong else 0.80,
        sentiment_score=-0.14,
        raw_url=None,
    )


def build_summary_signal(
    rows: List[Dict[str, Any]],
    build_accelerating_count: int,
    build_decelerating_count: int,
    unwind_accelerating_count: int,
    summary_top_n: int,
) -> Signal:
    ranked = sorted(
        rows,
        key=lambda x: abs(safe_float(x.get("acceleration_pct"), 0.0)),
        reverse=True,
    )

    top_parts: List[str] = []
    for row in ranked[:summary_top_n]:
        top_parts.append(f"{row['entity']}({row['acceleration_pct']:.2f}%)")

    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_open_interest_acceleration_summary",
        entity="PERP_OI_ACCELERATION",
        title="Perpetual OI acceleration summary",
        summary=(
            f"rows={len(rows)} | "
            f"build_accelerating={build_accelerating_count} | "
            f"build_decelerating={build_decelerating_count} | "
            f"unwind_accelerating={unwind_accelerating_count} | "
            f"top_acceleration={', '.join(top_parts) if top_parts else 'none'}"
        ),
        confidence=0.84,
        sentiment_score=0.0,
        raw_url=None,
    )


# ---------------------------------------------------
# MAIN COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="open_interest_acceleration",
    priority=1,
    tags=["flows", "perps", "oi", "acceleration", "second_order"],
    category="flows",
    execution="fast",
)
def fetch_open_interest_acceleration_signals() -> List[Signal]:
    started = time.time()
    cfg = load_engine_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        info_log("disabled by config")
        return signals

    history = load_history()
    symbols_bucket = history.get("symbols", {})
    if not isinstance(symbols_bucket, dict) or not symbols_bucket:
        info_log("no OI history found")
        return signals

    tracked = set(cfg.get("tracked_entities", []))
    require_tracked = bool(cfg.get("require_tracked_entity", True))
    min_history_points = safe_int(cfg.get("min_history_points", 3), 3)
    min_valid_oi = safe_float(cfg.get("min_valid_oi", 0.0), 0.0)

    build_threshold_pct = safe_float(cfg.get("build_threshold_pct", 1.5), 1.5)
    unwind_threshold_pct = safe_float(cfg.get("unwind_threshold_pct", -1.5), -1.5)
    acceleration_threshold_pct = safe_float(cfg.get("acceleration_threshold_pct", 1.0), 1.0)
    strong_acceleration_threshold_pct = safe_float(cfg.get("strong_acceleration_threshold_pct", 3.0), 3.0)

    emit_base_rows = bool(cfg.get("emit_base_acceleration_rows", True))
    max_signals = safe_int(cfg.get("max_signals_per_run", 100), 100)

    build_accelerating_count = 0
    build_decelerating_count = 0
    unwind_accelerating_count = 0

    accel_rows: List[Dict[str, Any]] = []

    for symbol, series in symbols_bucket.items():
        entity = base_asset(symbol)

        if require_tracked and entity not in tracked:
            continue

        points = get_recent_points(series, min_history_points)
        if not points:
            continue

        older = points[-3]
        prior = points[-2]
        current = points[-1]

        older_oi = safe_float(older.get("avg_oi"), 0.0)
        prior_oi = safe_float(prior.get("avg_oi"), 0.0)
        current_oi = safe_float(current.get("avg_oi"), 0.0)

        if older_oi <= min_valid_oi or prior_oi <= min_valid_oi or current_oi <= min_valid_oi:
            continue

        prior_change_pct = pct_change(prior_oi, older_oi)
        current_change_pct = pct_change(current_oi, prior_oi)
        acceleration_pct = current_change_pct - prior_change_pct

        accel_rows.append(
            {
                "entity": entity,
                "older_oi": older_oi,
                "prior_oi": prior_oi,
                "current_oi": current_oi,
                "prior_change_pct": prior_change_pct,
                "current_change_pct": current_change_pct,
                "acceleration_pct": acceleration_pct,
            }
        )

        if emit_base_rows:
            signals.append(
                build_acceleration_signal(
                    entity=entity,
                    current_change_pct=current_change_pct,
                    prior_change_pct=prior_change_pct,
                    acceleration_pct=acceleration_pct,
                    current_oi=current_oi,
                    prior_oi=prior_oi,
                )
            )

        # ---------------------------------------------------
        # BUILD ACCELERATING
        # ---------------------------------------------------

        if current_change_pct >= build_threshold_pct and acceleration_pct >= acceleration_threshold_pct:
            strong = acceleration_pct >= strong_acceleration_threshold_pct
            build_accelerating_count += 1

            signals.append(
                build_build_accelerating_signal(
                    entity=entity,
                    current_change_pct=current_change_pct,
                    prior_change_pct=prior_change_pct,
                    acceleration_pct=acceleration_pct,
                    strong=strong,
                )
            )

        # ---------------------------------------------------
        # BUILD DECELERATING
        # ---------------------------------------------------

        elif prior_change_pct >= build_threshold_pct and acceleration_pct <= -acceleration_threshold_pct:
            build_decelerating_count += 1

            signals.append(
                build_build_decelerating_signal(
                    entity=entity,
                    current_change_pct=current_change_pct,
                    prior_change_pct=prior_change_pct,
                    acceleration_pct=acceleration_pct,
                )
            )

        # ---------------------------------------------------
        # UNWIND ACCELERATING
        # ---------------------------------------------------

        elif current_change_pct <= unwind_threshold_pct and acceleration_pct <= -acceleration_threshold_pct:
            strong = acceleration_pct <= -strong_acceleration_threshold_pct
            unwind_accelerating_count += 1

            signals.append(
                build_unwind_accelerating_signal(
                    entity=entity,
                    current_change_pct=current_change_pct,
                    prior_change_pct=prior_change_pct,
                    acceleration_pct=acceleration_pct,
                    strong=strong,
                )
            )

        if len(signals) >= max_signals:
            break

    signals.append(
        build_summary_signal(
            rows=accel_rows,
            build_accelerating_count=build_accelerating_count,
            build_decelerating_count=build_decelerating_count,
            unwind_accelerating_count=unwind_accelerating_count,
            summary_top_n=safe_int(cfg.get("summary_top_n", 8), 8),
        )
    )

    runtime = round(time.time() - started, 2)
    debug_log(
        cfg,
        f"symbols={len(symbols_bucket)} accel_rows={len(accel_rows)} "
        f"build_accelerating={build_accelerating_count} "
        f"build_decelerating={build_decelerating_count} "
        f"unwind_accelerating={unwind_accelerating_count} "
        f"signals_returned={len(signals)} runtime={runtime}s"
    )

    return signals[:max_signals]


# ---------------------------------------------------
# DIRECT TEST MODE
# ---------------------------------------------------

if __name__ == "__main__":
    rows = fetch_open_interest_acceleration_signals()
    print("count:", len(rows))
    for row in rows[:20]:
        print(
            getattr(row, "signal_type", None),
            getattr(row, "entity", None),
            getattr(row, "summary", None),
        )
