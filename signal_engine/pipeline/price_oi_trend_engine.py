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
# MODULE: price_oi_trend_engine
# PURPOSE: Detect trend using price + OI acceleration (production-safe)
# ============================================================
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

CONFIG_FILE = "price_oi_trend_engine.json"

SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")
PRICE_PATH = Path("/opt/toknclaw/data/token_price_history.json")


def _safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _safe_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _safe_float(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def _load_snapshot() -> Dict[str, Any]:
    if SNAPSHOT_PATH.exists():
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_price() -> Dict[str, Any]:
    if PRICE_PATH.exists():
        with open(PRICE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _parse(summary: Any, key: str) -> float:
    text = str(summary or "")
    match = re.search(rf"{re.escape(key)}=([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", text)
    return float(match.group(1)) if match else 0.0


def _price_change(rows: List[Dict[str, Any]]) -> float:
    """
    Compare the newest price to the most recent prior DIFFERENT price.
    This avoids false zero deltas when the last two ticks are duplicates.
    """
    rows = _safe_list(rows)
    if len(rows) < 2:
        return 0.0

    latest = _safe_float(_safe_dict(rows[-1]).get("price_usd"))
    if latest <= 0:
        return 0.0

    for prior_row in reversed(rows[:-1]):
        prior = _safe_float(_safe_dict(prior_row).get("price_usd"))
        if prior <= 0:
            continue
        if prior != latest:
            return ((latest / prior) - 1.0) * 100.0

    return 0.0


def build_price_oi_trend(snapshot: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    if not isinstance(snapshot, dict):
        snapshot = _load_snapshot()

    signals = _safe_list(snapshot.get("signals"))
    price_data = _load_price()
    tokens = _safe_dict(price_data.get("tokens"))

    out: List[Dict[str, Any]] = []

    stats = {
        "signals_in_snapshot": len(signals),
        "oi_accel_rows": 0,
        "missing_token_key": 0,
        "missing_price_rows": 0,
        "flat_price_delta": 0,
        "weak_oi": 0,
        "bullish_out": 0,
        "bearish_out": 0,
    }

    for raw in signals:
        row = _safe_dict(raw)

        if row.get("signal_type") != "perp_open_interest_acceleration":
            continue

        stats["oi_accel_rows"] += 1

        entity = str(row.get("entity") or "").strip()
        if not entity:
            continue

        summary = row.get("summary")
        change = _parse(summary, "current_change_pct")
        accel = _parse(summary, "acceleration_pct")

        entity_key = entity.upper()
        if entity_key not in tokens:
            stats["missing_token_key"] += 1
            continue

        price_rows = _safe_list(tokens.get(entity_key))
        if len(price_rows) < 2:
            stats["missing_price_rows"] += 1
            continue

        price_delta = _price_change(price_rows)

        if abs(price_delta) < 0.05:
            stats["flat_price_delta"] += 1
            continue

        if abs(change) < 0.15 and abs(accel) < 0.15:
            stats["weak_oi"] += 1
            continue

        strength = abs(price_delta) + max(abs(change), abs(accel))
        confidence = min(0.75, 0.40 + (strength / 5.0))

        if price_delta > 0 and (change > 0 or accel > 0):
            out.append({
                "signal_type": "perp_trend_bullish",
                "entity": entity,
                "summary": (
                    f"{entity} bullish trend "
                    f"(price={round(price_delta, 3)}%, "
                    f"oi_change={round(change, 3)}, "
                    f"accel={round(accel, 3)})"
                ),
                "confidence": round(confidence, 4),
            })
            stats["bullish_out"] += 1

        elif price_delta < 0 and (change < 0 or accel < 0):
            out.append({
                "signal_type": "perp_trend_bearish",
                "entity": entity,
                "summary": (
                    f"{entity} bearish trend "
                    f"(price={round(price_delta, 3)}%, "
                    f"oi_change={round(change, 3)}, "
                    f"accel={round(accel, 3)})"
                ),
                "confidence": round(confidence, 4),
            })
            stats["bearish_out"] += 1

    print(
        "[TREND ENGINE] "
        f"signals_in_snapshot={stats['signals_in_snapshot']} "
        f"oi_accel_rows={stats['oi_accel_rows']} "
        f"missing_token_key={stats['missing_token_key']} "
        f"missing_price_rows={stats['missing_price_rows']} "
        f"flat_price_delta={stats['flat_price_delta']} "
        f"weak_oi={stats['weak_oi']} "
        f"bullish_out={stats['bullish_out']} "
        f"bearish_out={stats['bearish_out']} "
        f"total_out={len(out)}"
    )

    return out
