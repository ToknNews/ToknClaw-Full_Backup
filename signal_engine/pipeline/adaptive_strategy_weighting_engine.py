#!/usr/bin/env python3

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
# MODULE: adaptive_strategy_weighting_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
████████╗ ██████╗ ██╗  ██╗███╗   ██╗
╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║
   ██║   ██║   ██║█████╔╝ ██╔██╗ ██║
   ██║   ██║   ██║██╔═██╗ ██║╚██╗██║
   ██║   ╚██████╔╝██║  ██╗██║ ╚████║
   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝

TOKNCLAW SIGNAL ENGINE
Adaptive Strategy Weighting Engine

Purpose
-------
Reads strategy performance outputs and produces adaptive strategy
weights for allocator / paper trading / future live execution.

This module is designed to:
• convert strategy performance into normalized weights
• remain additive and OpenClaw-ready
• support future strategies without core refactor
• persist a structured weight state for website / dashboard use

Primary Inputs
--------------
snapshot["signals"] containing:
• solana_strategy_performance

Primary Outputs
---------------
snapshot keys:
• adaptive_strategy_weights
• adaptive_strategy_weight_summary
• adaptive_strategy_weight_alerts

Persistent File
---------------
/opt/toknclaw/data/adaptive_strategy_weights.json

Agent Readiness
---------------
OpenClaw agents should tune:
• /opt/toknclaw/config/adaptive_strategy_weighting_engine.json

Author: TOKN Systems
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from runtime_config import load_config


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

CONFIG_FILE = "adaptive_strategy_weighting_engine.json"
STATE_PATH = Path("/opt/toknclaw/data/adaptive_strategy_weights.json")
STATE_TMP_PATH = Path("/opt/toknclaw/data/adaptive_strategy_weights.tmp")


# ---------------------------------------------------
# DEFAULT CONFIG
# ---------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "min_weight": 0.25,
    "max_weight": 2.50,
    "neutral_weight": 1.00,
    "min_trades_required": 5,
    "boost_threshold_expectancy": 1.00,
    "penalty_threshold_expectancy": -1.00,
    "win_rate_boost_threshold": 0.60,
    "win_rate_penalty_threshold": 0.40,
    "max_alerts": 25,
    "strategy_family_map": {
        "solana_strategy_entry_dip_buy": "dip",
        "solana_strategy_watch_dip_buy": "dip",
        "solana_strategy_avoid_dip_buy": "dip",
        "solana_strategy_entry_momentum": "momentum",
        "solana_strategy_watch_momentum": "momentum",
        "solana_strategy_avoid_momentum": "momentum",
        "solana_strategy_entry_migration": "migration",
        "solana_strategy_watch_migration": "migration",
        "solana_strategy_avoid_migration": "migration",
        "solana_trade_decision": "allocator",
        "solana_trade_candidate": "allocator",
        "solana_trade_avoid": "allocator",
    },
}


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return utc_now().isoformat()


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[ADAPTIVE WEIGHTS] {message}")


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return deepcopy(DEFAULT_CONFIG)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)

    if not isinstance(merged.get("strategy_family_map"), dict):
        merged["strategy_family_map"] = deepcopy(DEFAULT_CONFIG["strategy_family_map"])

    return merged


def parse_performance_summary(summary: str) -> Dict[str, float]:
    """
    Example summary:
    trades=12 win_rate=0.583 avg_return=1.23 expectancy=0.72
    """
    out = {
        "trades": 0.0,
        "win_rate": 0.0,
        "avg_return": 0.0,
        "expectancy": 0.0,
    }

    text = clean_text(summary)
    if not text:
        return out

    parts = text.split()

    for part in parts:
        if "=" not in part:
            continue

        key, value = part.split("=", 1)
        key = clean_text(key)
        value = clean_text(value).replace("%", "")

        if key in out:
            out[key] = safe_float(value, out[key])

    return out


def clip(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


# ---------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------

def build_adaptive_strategy_weighting(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_engine_config()

    if not bool(cfg.get("enabled", True)):
        return {
            "adaptive_strategy_weights": [],
            "adaptive_strategy_weight_summary": {
                "enabled": False,
                "updated_at": now_iso(),
                "families_seen": 0,
                "strategies_seen": 0,
            },
            "adaptive_strategy_weight_alerts": [],
        }

    rows = snapshot.get("signals", [])
    if not isinstance(rows, list):
        rows = []

    perf_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if clean_text(row.get("signal_type")) == "solana_strategy_performance":
            perf_rows.append(row)

    family_map = cfg.get("strategy_family_map", {})
    neutral_weight = safe_float(cfg.get("neutral_weight", 1.0), 1.0)
    min_weight = safe_float(cfg.get("min_weight", 0.25), 0.25)
    max_weight = safe_float(cfg.get("max_weight", 2.5), 2.5)
    min_trades_required = safe_int(cfg.get("min_trades_required", 5), 5)

    boost_expectancy = safe_float(cfg.get("boost_threshold_expectancy", 1.0), 1.0)
    penalty_expectancy = safe_float(cfg.get("penalty_threshold_expectancy", -1.0), -1.0)
    boost_win_rate = safe_float(cfg.get("win_rate_boost_threshold", 0.60), 0.60)
    penalty_win_rate = safe_float(cfg.get("win_rate_penalty_threshold", 0.40), 0.40)

    strategy_weights: List[Dict[str, Any]] = []
    family_rollup: Dict[str, List[float]] = {}
    alerts: List[Dict[str, Any]] = []

    for row in perf_rows:
        strategy_name = clean_text(row.get("entity"))
        title = clean_text(row.get("title"))
        summary = clean_text(row.get("summary"))

        parsed = parse_performance_summary(summary)

        trades = safe_int(parsed.get("trades", 0.0), 0)
        win_rate = safe_float(parsed.get("win_rate", 0.0), 0.0)
        avg_return = safe_float(parsed.get("avg_return", 0.0), 0.0)
        expectancy = safe_float(parsed.get("expectancy", 0.0), 0.0)

        family = clean_text(family_map.get(strategy_name, "unmapped"))

        weight = neutral_weight
        reasons: List[str] = []

        if trades < min_trades_required:
            reasons.append("low_sample_neutral")
        else:
            if expectancy >= boost_expectancy:
                weight += 0.50
                reasons.append("positive_expectancy")

            if expectancy <= penalty_expectancy:
                weight -= 0.40
                reasons.append("negative_expectancy")

            if win_rate >= boost_win_rate:
                weight += 0.30
                reasons.append("strong_win_rate")

            if win_rate <= penalty_win_rate:
                weight -= 0.25
                reasons.append("weak_win_rate")

            if avg_return > 0:
                weight += min(avg_return / 10.0, 0.35)
                reasons.append("positive_avg_return")

            if avg_return < 0:
                weight -= min(abs(avg_return) / 10.0, 0.35)
                reasons.append("negative_avg_return")

        weight = clip(weight, min_weight, max_weight)

        strategy_payload = {
            "strategy_name": strategy_name,
            "strategy_family": family,
            "title": title,
            "trades": trades,
            "win_rate": round(win_rate, 4),
            "avg_return": round(avg_return, 4),
            "expectancy": round(expectancy, 4),
            "adaptive_weight": round(weight, 4),
            "reasons": reasons,
            "updated_at": now_iso(),
        }

        strategy_weights.append(strategy_payload)
        family_rollup.setdefault(family, []).append(weight)

        if trades >= min_trades_required:
            if weight > neutral_weight:
                alerts.append(
                    {
                        "level": "info",
                        "strategy_name": strategy_name,
                        "message": f"{strategy_name} boosted to {round(weight, 4)}",
                    }
                )
            elif weight < neutral_weight:
                alerts.append(
                    {
                        "level": "warning",
                        "strategy_name": strategy_name,
                        "message": f"{strategy_name} reduced to {round(weight, 4)}",
                    }
                )

    strategy_weights.sort(
        key=lambda x: (
            safe_float(x.get("adaptive_weight", 0.0), 0.0),
            safe_int(x.get("trades", 0), 0),
            safe_float(x.get("expectancy", 0.0), 0.0),
        ),
        reverse=True,
    )

    family_weights: List[Dict[str, Any]] = []
    for family, weights in family_rollup.items():
        if not weights:
            continue

        avg_weight = sum(weights) / len(weights)
        family_weights.append(
            {
                "strategy_family": family,
                "adaptive_weight": round(avg_weight, 4),
                "strategy_count": len(weights),
            }
        )

    family_weights.sort(
        key=lambda x: safe_float(x.get("adaptive_weight", 0.0), 0.0),
        reverse=True,
    )

    max_alerts = safe_int(cfg.get("max_alerts", 25), 25)
    alerts = alerts[:max_alerts]

    payload = {
        "updated_at": now_iso(),
        "strategy_weights": strategy_weights,
        "family_weights": family_weights,
        "summary": {
            "enabled": True,
            "updated_at": now_iso(),
            "strategies_seen": len(strategy_weights),
            "families_seen": len(family_weights),
            "top_strategy": strategy_weights[0]["strategy_name"] if strategy_weights else None,
            "top_family": family_weights[0]["strategy_family"] if family_weights else None,
            "neutral_weight": neutral_weight,
        },
        "alerts": alerts,
    }

    write_json_atomic(STATE_PATH, STATE_TMP_PATH, payload)

    debug_log(
        cfg,
        f"strategies_seen={len(strategy_weights)} families_seen={len(family_weights)} alerts={len(alerts)}",
    )

    return {
        "adaptive_strategy_weights": strategy_weights,
        "adaptive_strategy_weight_summary": payload["summary"],
        "adaptive_strategy_weight_alerts": alerts,
        "adaptive_strategy_family_weights": family_weights,
    }
