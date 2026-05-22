#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — MARKET REGIME ENGINE
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
# MODULE: market_regime_engine
# PURPOSE:
# - Classify current trading regime from trading snapshot signals
# - Distinguish dead chop, high noise, squeeze watch, early trend, confirmed trend
# - Emit trading permissions for paper/live execution gates
# - Keep leverage mode conservative unless trend quality is confirmed
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")
OUT_PATH = Path("/opt/toknclaw/data/analytics/market_regime.json")


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_str(value: Any) -> str:
    return str(value or "").strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def signal_type(row: Dict[str, Any]) -> str:
    return safe_str(row.get("signal_type")).lower()


def row_entity(row: Dict[str, Any]) -> str:
    return safe_str(row.get("entity")).upper()


def row_direction(row: Dict[str, Any]) -> str:
    return safe_str(row.get("direction")).lower()


def row_strategy(row: Dict[str, Any]) -> str:
    return safe_str(row.get("strategy") or row.get("setup_family")).lower()


def row_reasons(row: Dict[str, Any]) -> str:
    reasons = row.get("reasons", [])
    if isinstance(reasons, list):
        return " ".join(safe_str(x).lower() for x in reasons)
    return safe_str(reasons).lower()


# ---------------------------------------------------
# FEATURE EXTRACTION
# ---------------------------------------------------

def extract_features(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    signals = safe_list(snapshot.get("signals"))
    trade_rows = safe_list(safe_dict(snapshot.get("trade_signals")).get("rows"))

    trend_signal_count = 0
    squeeze_signal_count = 0
    liquidation_signal_count = 0
    funding_signal_count = 0
    oi_signal_count = 0
    noise_signal_count = 0

    directional_trade_rows = 0
    strong_directional_rows = 0
    no_trade_rows = 0

    high_priority_rows = 0
    high_confidence_rows = 0

    squeeze_trade_rows = 0
    trend_trade_rows = 0

    directional_entities = set()
    squeeze_entities = set()
    trend_entities = set()

    for raw in signals:
        row = safe_dict(raw)
        st = signal_type(row)
        entity = row_entity(row)

        if "trend" in st:
            trend_signal_count += 1
            if entity:
                trend_entities.add(entity)
        elif "squeeze" in st:
            squeeze_signal_count += 1
            if entity:
                squeeze_entities.add(entity)
        elif "liquidation" in st or "flush" in st:
            liquidation_signal_count += 1
            if entity:
                squeeze_entities.add(entity)
        elif "funding" in st:
            funding_signal_count += 1
        elif "open_interest" in st or "oi_" in st:
            oi_signal_count += 1
        else:
            noise_signal_count += 1

    for raw in trade_rows:
        row = safe_dict(raw)

        direction = row_direction(row)
        strategy = row_strategy(row)
        reasons = row_reasons(row)
        entity = safe_str(row.get("entity")).upper()
        confidence = safe_float(row.get("confidence"), 0.0)
        priority = safe_float(row.get("priority_score"), 0.0)

        if direction == "no_trade":
            no_trade_rows += 1
            continue

        if direction in {"bullish", "strong_bullish", "bearish", "strong_bearish"}:
            directional_trade_rows += 1
            if entity:
                directional_entities.add(entity)

        if direction in {"strong_bullish", "strong_bearish"}:
            strong_directional_rows += 1

        if confidence >= 0.75:
            high_confidence_rows += 1

        if priority >= 0.70:
            high_priority_rows += 1

        if (
            "squeeze" in reasons
            or "liquidation" in reasons
            or "flush" in reasons
            or "crowding" in reasons
        ):
            squeeze_trade_rows += 1
            if entity:
                squeeze_entities.add(entity)

        if "trend" in strategy or "breakout" in strategy:
            trend_trade_rows += 1
            if entity:
                trend_entities.add(entity)

    total_signals = max(1, len(signals))
    total_trade_rows = max(1, len(trade_rows))

    noise_ratio = noise_signal_count / total_signals
    trend_ratio = trend_signal_count / total_signals
    squeeze_ratio = (squeeze_signal_count + liquidation_signal_count) / total_signals
    directional_ratio = directional_trade_rows / total_trade_rows
    no_trade_ratio = no_trade_rows / total_trade_rows

    return {
        "total_signals": len(signals),
        "total_trade_rows": len(trade_rows),

        "trend_score": trend_signal_count,
        "squeeze_score": squeeze_signal_count + liquidation_signal_count,
        "liquidation_score": liquidation_signal_count,
        "funding_score": funding_signal_count,
        "oi_score": oi_signal_count,
        "noise_score": noise_signal_count,

        "trend_ratio": round(trend_ratio, 6),
        "squeeze_ratio": round(squeeze_ratio, 6),
        "noise_ratio": round(noise_ratio, 6),

        "directional_trade_rows": directional_trade_rows,
        "strong_directional_rows": strong_directional_rows,
        "no_trade_rows": no_trade_rows,
        "directional_ratio": round(directional_ratio, 6),
        "no_trade_ratio": round(no_trade_ratio, 6),

        "high_priority_rows": high_priority_rows,
        "high_confidence_rows": high_confidence_rows,

        "squeeze_trade_rows": squeeze_trade_rows,
        "trend_trade_rows": trend_trade_rows,

        "directional_entities": sorted(directional_entities),
        "squeeze_entities": sorted(squeeze_entities),
        "trend_entities": sorted(trend_entities),
    }


# ---------------------------------------------------
# REGIME CLASSIFICATION
# ---------------------------------------------------

def classify_regime(features: Dict[str, Any]) -> Dict[str, Any]:
    trend_score = int(features.get("trend_score", 0))
    squeeze_score = int(features.get("squeeze_score", 0))
    noise_ratio = safe_float(features.get("noise_ratio"), 1.0)
    no_trade_ratio = safe_float(features.get("no_trade_ratio"), 1.0)

    directional_rows = int(features.get("directional_trade_rows", 0))
    strong_rows = int(features.get("strong_directional_rows", 0))
    high_priority_rows = int(features.get("high_priority_rows", 0))
    high_confidence_rows = int(features.get("high_confidence_rows", 0))
    squeeze_trade_rows = int(features.get("squeeze_trade_rows", 0))
    trend_trade_rows = int(features.get("trend_trade_rows", 0))

    regime = "dead_chop"
    confidence = 0.25
    trade_permission = "blocked"
    leverage_mode = "blocked"
    max_trade_candidates = 0
    allowed_strategy_families: List[str] = []
    allowed_reason_keywords: List[str] = []
    notes: List[str] = []

    if noise_ratio >= 0.85 and directional_rows <= 2:
        regime = "high_noise"
        confidence = 0.30
        notes.append("Noise dominates and directional rows are scarce.")

    elif trend_score >= 4 and trend_trade_rows >= 1 and high_priority_rows >= 1:
        regime = "confirmed_trend"
        confidence = 0.80
        trade_permission = "normal"
        leverage_mode = "normal"
        max_trade_candidates = 2
        allowed_strategy_families = ["trend_continuation", "breakout_continuation"]
        notes.append("Trend signals and trend/breakout candidates are present.")

    elif trend_score >= 1 and directional_rows >= 2 and high_confidence_rows >= 1:
        regime = "early_trend"
        confidence = 0.60
        trade_permission = "probe"
        leverage_mode = "probe"
        max_trade_candidates = 1
        allowed_strategy_families = ["trend_continuation", "breakout_continuation"]
        notes.append("Early trend structure detected, but not confirmed.")

    elif squeeze_score >= 2 and squeeze_trade_rows >= 1 and high_priority_rows >= 1:
        regime = "squeeze_watch"
        confidence = 0.62
        trade_permission = "probe"
        leverage_mode = "low"
        max_trade_candidates = 1
        allowed_reason_keywords = ["squeeze", "liquidation", "flush", "crowding"]
        notes.append("Squeeze/liquidation structure detected.")

    elif directional_rows >= 4 and no_trade_ratio < 0.70 and high_priority_rows >= 2:
        regime = "mixed_directional"
        confidence = 0.45
        trade_permission = "probe"
        leverage_mode = "low"
        max_trade_candidates = 1
        allowed_reason_keywords = ["squeeze", "liquidation", "flush", "trend", "breakout"]
        notes.append("Directional rows exist, but regime quality is mixed.")

    else:
        regime = "dead_chop"
        confidence = 0.25
        notes.append("No reliable trend or squeeze structure detected.")

    return {
        "regime": regime,
        "confidence": confidence,
        "trade_permission": trade_permission,
        "leverage_mode": leverage_mode,
        "max_trade_candidates": max_trade_candidates,
        "allowed_strategy_families": allowed_strategy_families,
        "allowed_reason_keywords": allowed_reason_keywords,
        "notes": notes,
    }


# ---------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------

def build_regime(snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if snapshot is None:
        if not SNAPSHOT_PATH.exists():
            return {}

        snapshot = read_json(SNAPSHOT_PATH, {})

    snapshot = safe_dict(snapshot)

    features = extract_features(snapshot)
    classification = classify_regime(features)

    payload = {
        "schema_version": 2,
        "generated_at": utc_now_iso(),
        "system": "ToknClaw",
        "module": "market_regime_engine",

        "regime": classification["regime"],
        "confidence": classification["confidence"],
        "trade_permission": classification["trade_permission"],
        "leverage_mode": classification["leverage_mode"],
        "max_trade_candidates": classification["max_trade_candidates"],
        "allowed_strategy_families": classification["allowed_strategy_families"],
        "allowed_reason_keywords": classification["allowed_reason_keywords"],

        "features": features,
        "notes": classification["notes"],

        # Backward-compatible fields used by existing UI/paper engine.
        "trend_score": features["trend_score"],
        "squeeze_score": features["squeeze_score"],
        "noise_score": features["noise_score"],
    }

    write_json(OUT_PATH, payload)

    return payload


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    result = build_regime()
    print(json.dumps(result, indent=2))
