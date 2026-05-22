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
# MODULE: funding_oi_strategy
# PURPOSE: Consume perpetual funding + open interest signals and emit
#          crowding, squeeze-watch, and broadcast setup strategy signals.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This collector is designed to:
• consume latest perp funding + open interest signals from signal lake
• detect crowded long / crowded short conditions
• emit squeeze-watch / liquidation-watch signals
• emit broadcast-ready market framing for ToknNews
• remain additive and OpenClaw agent ready

Primary Config
--------------
/opt/toknclaw/config/funding_oi_strategy.json

Primary Inputs
--------------
/opt/toknclaw/data/signal_lake.json

Primary Outputs
---------------
• perp_strategy_crowded_longs
• perp_strategy_crowded_shorts
• perp_strategy_short_squeeze_watch
• perp_strategy_long_liquidation_watch
• perp_broadcast_setup
• perp_strategy_flow_summary
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

import ast
import re
import time
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

from signal_engine.collectors.registry import register_collector
from signal_engine.models.signal import Signal
from signal_engine.runtime_config import load_config
from signal_engine.signal_lake import load_signal_lake


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

CONFIG_FILE = "funding_oi_strategy.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "lookback_signal_count": 4000,
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
    "min_oi_rank_pct": 0.60,
    "strong_oi_rank_pct": 0.80,
    "long_crowding_threshold": 0.0004,
    "short_crowding_threshold": -0.0004,
    "divergence_threshold": 0.0003,
    "max_strategy_signals": 50,
    "max_broadcast_setups": 5,
    "emit_broadcast_setup": True,
    "require_tracked_entity": True,
    "confidence_base": 0.72,
    "confidence_bonus_divergence": 0.08,
    "confidence_bonus_strong_oi": 0.07,
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
        print(f"[FUNDING+OI STRATEGY] {message}")


def info_log(message: str) -> None:
    print(f"[FUNDING+OI STRATEGY] {message}")


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


def load_snapshot():
    try:
        import json
        with open("/opt/toknclaw/data/snapshots/latest_snapshot.json") as f:
            return json.load(f)
    except Exception:
        return {}


def object_rows_only(rows: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in rows or []:
        if isinstance(row, dict):
            out.append(row)

    return out


def latest_rows_by_type_entity(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for row in rows:
        signal_type = clean_text(row.get("signal_type"))
        entity = clean_upper(row.get("entity"))

        if not signal_type or not entity:
            continue

        out[(signal_type, entity)] = row

    return out


def parse_avg_from_summary(summary: str, key: str) -> float:
    summary = clean_text(summary)
    pattern = rf"{re.escape(key)}=([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"
    match = re.search(pattern, summary)

    if not match:
        return 0.0

    return safe_float(match.group(1), 0.0)


def parse_venues_from_summary(summary: str) -> Dict[str, float]:
    summary = clean_text(summary)

    match = re.search(r"venues=(\{.*\})", summary)
    if not match:
        return {}

    raw = match.group(1)

    try:
        parsed = ast.literal_eval(raw)
        if not isinstance(parsed, dict):
            return {}
        return {clean_text(k): safe_float(v, 0.0) for k, v in parsed.items()}
    except Exception:
        return {}


def funding_row_to_value(row: Dict[str, Any]) -> Dict[str, Any]:
    summary = clean_text(row.get("summary"))

    avg_funding = parse_avg_from_summary(summary, "avg")
    venues = parse_venues_from_summary(summary)

    return {
        "entity": clean_upper(row.get("entity")),
        "avg_funding": avg_funding,
        "venues": venues,
        "signal_type": clean_text(row.get("signal_type")),
    }


def oi_row_to_value(row: Dict[str, Any]) -> Dict[str, Any]:
    summary = clean_text(row.get("summary"))

    avg_oi = parse_avg_from_summary(summary, "avg_oi")
    venues = parse_venues_from_summary(summary)

    return {
        "entity": clean_upper(row.get("entity")),
        "avg_oi": avg_oi,
        "venues": venues,
        "signal_type": clean_text(row.get("signal_type")),
    }


def oi_rank_map(oi_by_entity: Dict[str, float]) -> Dict[str, float]:
    if not oi_by_entity:
        return {}

    ranked = sorted(
        oi_by_entity.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    count = len(ranked)
    out: Dict[str, float] = {}

    for idx, (entity, _) in enumerate(ranked):
        if count == 1:
            out[entity] = 1.0
        else:
            out[entity] = round(1.0 - (idx / (count - 1)), 6)

    return out


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _funding_map(snapshot):
    out = {}

    for s in snapshot.get("signals", []):
        if not isinstance(s, dict):
            continue

        if s.get("signal_type") != "perp_funding_rate":
            continue

        entity = str(s.get("entity") or "").upper()
        if not entity:
            continue

        summary = str(s.get("summary") or "")

        try:
            val = float(summary.split("avg=")[1].split("|")[0].strip())
        except Exception:
            val = 0.0

        out[entity] = val

    return out


def _oi_map(snapshot):
    out = {}

    for s in snapshot.get("signals", []):
        if not isinstance(s, dict):
            continue

        if s.get("signal_type") != "perp_open_interest":
            continue

        entity = str(s.get("entity") or "").upper()
        if not entity:
            continue

        summary = str(s.get("summary") or "")

        try:
            val = float(summary.split("avg_oi=")[1].split("|")[0].strip())
        except Exception:
            val = 0.0

        out[entity] = val

    return out


# ---------------------------------------------------
# SIGNAL BUILDERS
# ---------------------------------------------------

def build_crowded_longs_signal(
    entity: str,
    avg_funding: float,
    avg_oi: float,
    oi_rank_pct: float,
    has_divergence: bool,
    confidence: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_strategy_crowded_longs",
        entity=entity,
        title=f"{entity} crowded longs detected",
        summary=(
            f"{entity} shows crowded long positioning | "
            f"funding={avg_funding:.6f} | "
            f"avg_oi={avg_oi:.2f} | "
            f"oi_rank_pct={oi_rank_pct:.2%} | "
            f"divergence={'yes' if has_divergence else 'no'}"
        ),
        confidence=confidence,
        sentiment_score=-0.16,
        raw_url=None,
    )


def build_crowded_shorts_signal(
    entity: str,
    avg_funding: float,
    avg_oi: float,
    oi_rank_pct: float,
    has_divergence: bool,
    confidence: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_strategy_crowded_shorts",
        entity=entity,
        title=f"{entity} crowded shorts detected",
        summary=(
            f"{entity} shows crowded short positioning | "
            f"funding={avg_funding:.6f} | "
            f"avg_oi={avg_oi:.2f} | "
            f"oi_rank_pct={oi_rank_pct:.2%} | "
            f"divergence={'yes' if has_divergence else 'no'}"
        ),
        confidence=confidence,
        sentiment_score=0.16,
        raw_url=None,
    )


def build_short_squeeze_watch_signal(
    entity: str,
    avg_funding: float,
    avg_oi: float,
    oi_rank_pct: float,
    has_divergence: bool,
    confidence: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_strategy_short_squeeze_watch",
        entity=entity,
        title=f"{entity} short squeeze watch",
        summary=(
            f"{entity} is a short-squeeze watch candidate | "
            f"negative funding with elevated OI suggests crowded shorts | "
            f"funding={avg_funding:.6f} | avg_oi={avg_oi:.2f} | "
            f"oi_rank_pct={oi_rank_pct:.2%} | divergence={'yes' if has_divergence else 'no'}"
        ),
        confidence=confidence,
        sentiment_score=0.28,
        raw_url=None,
    )


def build_long_liquidation_watch_signal(
    entity: str,
    avg_funding: float,
    avg_oi: float,
    oi_rank_pct: float,
    has_divergence: bool,
    confidence: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_strategy_long_liquidation_watch",
        entity=entity,
        title=f"{entity} long liquidation watch",
        summary=(
            f"{entity} is a long-liquidation watch candidate | "
            f"positive funding with elevated OI suggests crowded longs | "
            f"funding={avg_funding:.6f} | avg_oi={avg_oi:.2f} | "
            f"oi_rank_pct={oi_rank_pct:.2%} | divergence={'yes' if has_divergence else 'no'}"
        ),
        confidence=confidence,
        sentiment_score=-0.28,
        raw_url=None,
    )


def build_broadcast_setup_signal(
    entity: str,
    setup_type: str,
    avg_funding: float,
    avg_oi: float,
    oi_rank_pct: float,
    has_divergence: bool,
    confidence: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_broadcast_setup",
        entity=entity,
        title=f"{entity} perp positioning setup",
        summary=(
            f"{entity} perp setup={setup_type} | "
            f"funding={avg_funding:.6f} | "
            f"avg_oi={avg_oi:.2f} | "
            f"oi_rank_pct={oi_rank_pct:.2%} | "
            f"divergence={'yes' if has_divergence else 'no'} | "
            f"confidence={confidence:.2f}"
        ),
        confidence=confidence,
        sentiment_score=0.0,
        raw_url=None,
    )


def build_summary_signal(
    total_entities: int,
    crowded_longs: int,
    crowded_shorts: int,
    short_squeeze_watch: int,
    long_liq_watch: int,
    top_setups: List[str],
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_strategy_flow_summary",
        entity="PERP_FLOW",
        title="Perpetual positioning flow summary",
        summary=(
            f"entities={total_entities} | "
            f"crowded_longs={crowded_longs} | "
            f"crowded_shorts={crowded_shorts} | "
            f"short_squeeze_watch={short_squeeze_watch} | "
            f"long_liquidation_watch={long_liq_watch} | "
            f"top_setups={', '.join(top_setups) if top_setups else 'none'}"
        ),
        confidence=0.84,
        sentiment_score=0.0,
        raw_url=None,
    )


# ---------------------------------------------------
# CORE LOGIC
# ---------------------------------------------------

def build_entity_inputs(rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    latest = latest_rows_by_type_entity(rows)

    funding_by_entity: Dict[str, Dict[str, Any]] = {}
    oi_by_entity: Dict[str, Dict[str, Any]] = {}
    divergence_entities: set[str] = set()

    tracked_entities = set(cfg.get("tracked_entities", []))
    require_tracked = bool(cfg.get("require_tracked_entity", True))

    for (signal_type, entity), row in latest.items():
        if require_tracked and entity not in tracked_entities:
            continue

        if signal_type == "perp_funding_rate":
            funding_by_entity[entity] = funding_row_to_value(row)

        elif signal_type == "perp_open_interest":
            oi_by_entity[entity] = oi_row_to_value(row)

        elif signal_type == "perp_funding_divergence":
            divergence_entities.add(entity)

    entities = set(funding_by_entity.keys()) | set(oi_by_entity.keys())

    oi_scalar_map = {
        entity: safe_float(payload.get("avg_oi"), 0.0)
        for entity, payload in oi_by_entity.items()
        if safe_float(payload.get("avg_oi"), 0.0) > 0.0
    }

    oi_pct_map = oi_rank_map(oi_scalar_map)

    out: Dict[str, Dict[str, Any]] = {}

    for entity in sorted(entities):
        funding_payload = funding_by_entity.get(entity, {})
        oi_payload = oi_by_entity.get(entity, {})

        out[entity] = {
            "entity": entity,
            "avg_funding": safe_float(funding_payload.get("avg_funding"), 0.0),
            "avg_oi": safe_float(oi_payload.get("avg_oi"), 0.0),
            "oi_rank_pct": safe_float(oi_pct_map.get(entity), 0.0),
            "has_divergence": entity in divergence_entities,
            "funding_venues": funding_payload.get("venues", {}),
            "oi_venues": oi_payload.get("venues", {}),
        }

    return out


def confidence_for_entity(
    oi_rank_pct: float,
    has_divergence: bool,
    cfg: Dict[str, Any],
) -> float:
    confidence = safe_float(cfg.get("confidence_base", 0.72), 0.72)

    if has_divergence:
        confidence += safe_float(cfg.get("confidence_bonus_divergence", 0.08), 0.08)

    if oi_rank_pct >= safe_float(cfg.get("strong_oi_rank_pct", 0.80), 0.80):
        confidence += safe_float(cfg.get("confidence_bonus_strong_oi", 0.07), 0.07)

    return round(clamp(confidence, 0.0, 0.98), 4)


# ---------------------------------------------------
# PUBLIC COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="funding_oi_strategy",
    priority=1,
    tags=["flows", "perps", "funding", "oi", "strategy", "broadcast"],
    category="flows",
    execution="fast",
)
def fetch_funding_oi_strategy_signals() -> List[Signal]:
    started = time.time()
    cfg = load_engine_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        info_log("disabled by config")
        return signals

    snapshot = load_snapshot()
    raw_rows = object_rows_only(snapshot.get("signals", []))

    if not raw_rows:
        lake = load_signal_lake()
        raw_rows = object_rows_only(lake.get("signals", []))

    lookback_signal_count = safe_int(cfg.get("lookback_signal_count", 4000), 4000)
    rows = raw_rows[-lookback_signal_count:]

    print("[FUNDING+OI DEBUG] rows:", len(rows))
    print(
        "[FUNDING+OI DEBUG] funding signals:",
        len([r for r in rows if r.get("signal_type") == "perp_funding_rate"]),
    )
    print(
        "[FUNDING+OI DEBUG] oi signals:",
        len([r for r in rows if r.get("signal_type") == "perp_open_interest"]),
    )

    entity_inputs = build_entity_inputs(rows, cfg)
    if not entity_inputs:
        info_log("no funding/oi entity inputs found")
        return signals

    min_oi_rank_pct = safe_float(cfg.get("min_oi_rank_pct", 0.60), 0.60)
    long_crowding_threshold = safe_float(cfg.get("long_crowding_threshold", 0.0004), 0.0004)
    short_crowding_threshold = safe_float(cfg.get("short_crowding_threshold", -0.0004), -0.0004)

    crowded_longs = 0
    crowded_shorts = 0
    short_squeeze_watch = 0
    long_liq_watch = 0

    setup_rows: List[Tuple[str, float, str]] = []

    for entity, payload in entity_inputs.items():
        avg_funding = safe_float(payload.get("avg_funding"), 0.0)
        avg_oi = safe_float(payload.get("avg_oi"), 0.0)
        oi_rank_pct = safe_float(payload.get("oi_rank_pct"), 0.0)
        has_divergence = bool(payload.get("has_divergence", False))

        if avg_oi <= 0.0:
            continue

        if oi_rank_pct < min_oi_rank_pct:
            continue

        confidence = confidence_for_entity(
            oi_rank_pct=oi_rank_pct,
            has_divergence=has_divergence,
            cfg=cfg,
        )

        if avg_funding >= long_crowding_threshold:
            crowded_longs += 1
            signals.append(
                build_crowded_longs_signal(
                    entity=entity,
                    avg_funding=avg_funding,
                    avg_oi=avg_oi,
                    oi_rank_pct=oi_rank_pct,
                    has_divergence=has_divergence,
                    confidence=confidence,
                )
            )

            if has_divergence or oi_rank_pct >= safe_float(cfg.get("strong_oi_rank_pct", 0.80), 0.80):
                long_liq_watch += 1
                signals.append(
                    build_long_liquidation_watch_signal(
                        entity=entity,
                        avg_funding=avg_funding,
                        avg_oi=avg_oi,
                        oi_rank_pct=oi_rank_pct,
                        has_divergence=has_divergence,
                        confidence=confidence,
                    )
                )
                setup_rows.append((entity, confidence, "long_liquidation_watch"))

        elif avg_funding <= short_crowding_threshold:
            crowded_shorts += 1
            signals.append(
                build_crowded_shorts_signal(
                    entity=entity,
                    avg_funding=avg_funding,
                    avg_oi=avg_oi,
                    oi_rank_pct=oi_rank_pct,
                    has_divergence=has_divergence,
                    confidence=confidence,
                )
            )

            if has_divergence or oi_rank_pct >= safe_float(cfg.get("strong_oi_rank_pct", 0.80), 0.80):
                short_squeeze_watch += 1
                signals.append(
                    build_short_squeeze_watch_signal(
                        entity=entity,
                        avg_funding=avg_funding,
                        avg_oi=avg_oi,
                        oi_rank_pct=oi_rank_pct,
                        has_divergence=has_divergence,
                        confidence=confidence,
                    )
                )
                setup_rows.append((entity, confidence, "short_squeeze_watch"))

    if bool(cfg.get("emit_broadcast_setup", True)):
        max_broadcast = safe_int(cfg.get("max_broadcast_setups", 5), 5)
        ranked_setups = sorted(setup_rows, key=lambda x: x[1], reverse=True)[:max_broadcast]

        for entity, confidence, setup_type in ranked_setups:
            payload = entity_inputs.get(entity, {})
            signals.append(
                build_broadcast_setup_signal(
                    entity=entity,
                    setup_type=setup_type,
                    avg_funding=safe_float(payload.get("avg_funding"), 0.0),
                    avg_oi=safe_float(payload.get("avg_oi"), 0.0),
                    oi_rank_pct=safe_float(payload.get("oi_rank_pct"), 0.0),
                    has_divergence=bool(payload.get("has_divergence", False)),
                    confidence=confidence,
                )
            )

    ranked_top = [
        f"{entity}:{setup_type}:{confidence:.2f}"
        for entity, confidence, setup_type in sorted(setup_rows, key=lambda x: x[1], reverse=True)[:5]
    ]

    signals.append(
        build_summary_signal(
            total_entities=len(entity_inputs),
            crowded_longs=crowded_longs,
            crowded_shorts=crowded_shorts,
            short_squeeze_watch=short_squeeze_watch,
            long_liq_watch=long_liq_watch,
            top_setups=ranked_top,
        )
    )

    max_strategy_signals = safe_int(cfg.get("max_strategy_signals", 50), 50)
    signals = signals[:max_strategy_signals]

    runtime = round(time.time() - started, 2)
    debug_log(
        cfg,
        f"rows={len(rows)} entities={len(entity_inputs)} "
        f"crowded_longs={crowded_longs} crowded_shorts={crowded_shorts} "
        f"short_squeeze_watch={short_squeeze_watch} long_liq_watch={long_liq_watch} "
        f"signals_returned={len(signals)} runtime={runtime}s"
    )

    return signals


# ---------------------------------------------------
# DIRECT TEST MODE
# ---------------------------------------------------

if __name__ == "__main__":
    rows = fetch_funding_oi_strategy_signals()
    print(f"count={len(rows)}")
    for row in rows[:20]:
        print(
            getattr(row, "signal_type", None),
            getattr(row, "entity", None),
            getattr(row, "summary", None),
        )
