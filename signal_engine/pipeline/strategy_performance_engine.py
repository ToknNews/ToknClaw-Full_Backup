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
# MODULE: strategy_performance_engine
# PURPOSE: Build agent-ready strategy performance analytics from backtest,
#          paper trading, and current trading artifacts without modifying
#          execution state.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• summarize setup-family performance from closed positions
• analyze long vs short effectiveness
• inspect close reasons and trade quality
• surface current open-position exposure
• generate OpenClaw-ready recommendations
• remain read-only and safe for repeated execution

Primary Inputs
--------------
/opt/toknclaw/data/backtests/latest_backtest_results.json
/opt/toknclaw/data/backtests/latest_backtest_state.json
/opt/toknclaw/data/paper_trading_state.json
/opt/toknclaw/data/snapshots/latest_snapshot_trading.json

Primary Output
--------------
/opt/toknclaw/data/analytics/strategy_performance.json
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import json
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List

# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

BACKTEST_RESULTS_PATH = Path("/opt/toknclaw/data/backtests/latest_backtest_results.json")
BACKTEST_STATE_PATH = Path("/opt/toknclaw/data/backtests/latest_backtest_state.json")
PAPER_TRADING_STATE_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")
TRADING_SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")

OUTPUT_DIR = Path("/opt/toknclaw/data/analytics")
OUTPUT_PATH = OUTPUT_DIR / "strategy_performance.json"
TMP_OUTPUT_PATH = OUTPUT_DIR / "strategy_performance.tmp"

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


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


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp_path.replace(path)


def pnl_bucket(pnl: float) -> str:
    if pnl > 0:
        return "win"
    if pnl < 0:
        return "loss"
    return "flat"


def win_rate_pct(wins: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((wins / total) * 100.0, 4)


def avg_or_zero(values: List[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


# ---------------------------------------------------
# CORE SUMMARIZERS
# ---------------------------------------------------

def summarize_closed_positions(closed_positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_setup_family: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "flat": 0,
        "realized_pnl_usd": 0.0,
        "avg_realized_pnl_usd": 0.0,
        "avg_realized_pnl_pct": 0.0,
        "close_reasons": Counter(),
        "entities": Counter(),
        "directions": Counter(),
    })

    by_direction: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "flat": 0,
        "realized_pnl_usd": 0.0,
        "avg_realized_pnl_usd": 0.0,
        "avg_realized_pnl_pct": 0.0,
    })

    by_entity: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "flat": 0,
        "realized_pnl_usd": 0.0,
        "avg_realized_pnl_usd": 0.0,
    })

    raw_family_pnls: Dict[str, List[float]] = defaultdict(list)
    raw_family_pnl_pcts: Dict[str, List[float]] = defaultdict(list)
    raw_direction_pnls: Dict[str, List[float]] = defaultdict(list)
    raw_direction_pnl_pcts: Dict[str, List[float]] = defaultdict(list)
    raw_entity_pnls: Dict[str, List[float]] = defaultdict(list)

    for pos in closed_positions:
        setup_family = clean_text(pos.get("setup_family")) or clean_text(
            safe_dict(pos.get("signal_copy")).get("setup_family")
        ) or "unknown"

        direction = clean_text(pos.get("direction")) or "unknown"
        entity = clean_upper(pos.get("entity")) or "UNKNOWN"
        close_reason = clean_text(pos.get("close_reason")) or "unknown"

        pnl_usd = safe_float(pos.get("realized_pnl_usd"), 0.0)
        pnl_pct_val = safe_float(pos.get("realized_pnl_pct"), 0.0)
        bucket = pnl_bucket(pnl_usd)

        fam = by_setup_family[setup_family]
        fam["count"] += 1
        fam["realized_pnl_usd"] += pnl_usd
        fam["close_reasons"][close_reason] += 1
        fam["entities"][entity] += 1
        fam["directions"][direction] += 1
        raw_family_pnls[setup_family].append(pnl_usd)
        raw_family_pnl_pcts[setup_family].append(pnl_pct_val)

        if bucket == "win":
            fam["wins"] += 1
        elif bucket == "loss":
            fam["losses"] += 1
        else:
            fam["flat"] += 1

        direc = by_direction[direction]
        direc["count"] += 1
        direc["realized_pnl_usd"] += pnl_usd
        raw_direction_pnls[direction].append(pnl_usd)
        raw_direction_pnl_pcts[direction].append(pnl_pct_val)

        if bucket == "win":
            direc["wins"] += 1
        elif bucket == "loss":
            direc["losses"] += 1
        else:
            direc["flat"] += 1

        ent = by_entity[entity]
        ent["count"] += 1
        ent["realized_pnl_usd"] += pnl_usd
        raw_entity_pnls[entity].append(pnl_usd)

        if bucket == "win":
            ent["wins"] += 1
        elif bucket == "loss":
            ent["losses"] += 1
        else:
            ent["flat"] += 1

    # finalize setup family stats
    finalized_setup = {}
    for family, payload in by_setup_family.items():
        total = safe_int(payload["count"], 0)
        finalized_setup[family] = {
            "count": total,
            "wins": safe_int(payload["wins"], 0),
            "losses": safe_int(payload["losses"], 0),
            "flat": safe_int(payload["flat"], 0),
            "win_rate_pct": win_rate_pct(safe_int(payload["wins"], 0), total),
            "realized_pnl_usd": round(safe_float(payload["realized_pnl_usd"]), 4),
            "avg_realized_pnl_usd": avg_or_zero(raw_family_pnls[family]),
            "avg_realized_pnl_pct": avg_or_zero(raw_family_pnl_pcts[family]),
            "top_entities": payload["entities"].most_common(5),
            "direction_mix": payload["directions"].most_common(5),
            "close_reasons": dict(payload["close_reasons"]),
        }

    finalized_direction = {}
    for direction, payload in by_direction.items():
        total = safe_int(payload["count"], 0)
        finalized_direction[direction] = {
            "count": total,
            "wins": safe_int(payload["wins"], 0),
            "losses": safe_int(payload["losses"], 0),
            "flat": safe_int(payload["flat"], 0),
            "win_rate_pct": win_rate_pct(safe_int(payload["wins"], 0), total),
            "realized_pnl_usd": round(safe_float(payload["realized_pnl_usd"]), 4),
            "avg_realized_pnl_usd": avg_or_zero(raw_direction_pnls[direction]),
            "avg_realized_pnl_pct": avg_or_zero(raw_direction_pnl_pcts[direction]),
        }

    finalized_entity = {}
    for entity, payload in by_entity.items():
        total = safe_int(payload["count"], 0)
        finalized_entity[entity] = {
            "count": total,
            "wins": safe_int(payload["wins"], 0),
            "losses": safe_int(payload["losses"], 0),
            "flat": safe_int(payload["flat"], 0),
            "win_rate_pct": win_rate_pct(safe_int(payload["wins"], 0), total),
            "realized_pnl_usd": round(safe_float(payload["realized_pnl_usd"]), 4),
            "avg_realized_pnl_usd": avg_or_zero(raw_entity_pnls[entity]),
        }

    return {
        "by_setup_family": dict(sorted(
            finalized_setup.items(),
            key=lambda x: (-safe_float(x[1].get("realized_pnl_usd"), 0.0), x[0])
        )),
        "by_direction": dict(sorted(finalized_direction.items())),
        "by_entity": dict(sorted(
            finalized_entity.items(),
            key=lambda x: (-safe_float(x[1].get("realized_pnl_usd"), 0.0), x[0])
        )),
    }


def summarize_open_positions(open_positions: Dict[str, Any]) -> Dict[str, Any]:
    by_setup_family: Counter = Counter()
    by_direction: Counter = Counter()
    by_entity: Counter = Counter()

    total_market_value = 0.0
    total_unrealized_pnl_usd = 0.0

    for _, pos in safe_dict(open_positions).items():
        if not isinstance(pos, dict):
            continue

        setup_family = clean_text(pos.get("setup_family")) or "unknown"
        direction = clean_text(pos.get("direction")) or "unknown"
        entity = clean_upper(pos.get("entity")) or "UNKNOWN"

        by_setup_family[setup_family] += 1
        by_direction[direction] += 1
        by_entity[entity] += 1

        total_market_value += safe_float(pos.get("market_value_usd"), 0.0)
        total_unrealized_pnl_usd += safe_float(pos.get("unrealized_pnl_usd"), 0.0)

    return {
        "open_position_count": len(safe_dict(open_positions)),
        "market_value_usd": round(total_market_value, 4),
        "unrealized_pnl_usd": round(total_unrealized_pnl_usd, 4),
        "by_setup_family": dict(by_setup_family.most_common()),
        "by_direction": dict(by_direction.most_common()),
        "by_entity": dict(by_entity.most_common()),
    }


def summarize_current_trade_signals(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    rows = safe_list(safe_dict(snapshot.get("trade_signals")).get("rows"))
    by_setup_family: Counter = Counter()
    by_direction: Counter = Counter()
    by_entity: Counter = Counter()

    priority_scores: List[float] = []
    confidence_scores: List[float] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        by_setup_family[clean_text(row.get("setup_family")) or "unknown"] += 1
        by_direction[clean_text(row.get("direction")) or "unknown"] += 1
        by_entity[clean_upper(row.get("entity")) or "UNKNOWN"] += 1

        priority_scores.append(safe_float(row.get("priority_score"), 0.0))
        confidence_scores.append(safe_float(row.get("confidence"), 0.0))

    return {
        "trade_row_count": len(rows),
        "avg_priority_score": avg_or_zero(priority_scores),
        "avg_confidence": avg_or_zero(confidence_scores),
        "by_setup_family": dict(by_setup_family.most_common()),
        "by_direction": dict(by_direction.most_common()),
        "top_entities": by_entity.most_common(10),
    }


def build_agent_recommendations(
    backtest_results: Dict[str, Any],
    setup_summary: Dict[str, Any],
    open_summary: Dict[str, Any],
    signal_summary: Dict[str, Any],
) -> Dict[str, Any]:
    portfolio = safe_dict(backtest_results.get("portfolio"))
    closed_summary = safe_dict(backtest_results.get("closed_position_summary"))

    realized_pnl_usd = safe_float(portfolio.get("realized_pnl_usd"), 0.0)
    equity_usd = safe_float(portfolio.get("equity_usd"), 0.0)
    max_drawdown_pct = safe_float(backtest_results.get("max_drawdown_pct"), 0.0)
    profit_factor = safe_float(closed_summary.get("profit_factor"), 0.0)

    setup_families = safe_dict(setup_summary.get("by_setup_family"))
    directions = safe_dict(setup_summary.get("by_direction"))

    weak_setups: List[Dict[str, Any]] = []
    strong_setups: List[Dict[str, Any]] = []
    notes: List[str] = []
    proposed_actions: List[Dict[str, Any]] = []

    for family, payload in setup_families.items():
        pnl = safe_float(payload.get("realized_pnl_usd"), 0.0)
        count = safe_int(payload.get("count"), 0)

        item = {
            "setup_family": family,
            "count": count,
            "realized_pnl_usd": round(pnl, 4),
            "win_rate_pct": safe_float(payload.get("win_rate_pct"), 0.0),
        }

        if pnl > 0:
            strong_setups.append(item)
        elif pnl < 0:
            weak_setups.append(item)

    strong_setups.sort(key=lambda x: (-x["realized_pnl_usd"], x["setup_family"]))
    weak_setups.sort(key=lambda x: (x["realized_pnl_usd"], x["setup_family"]))

    if profit_factor < 1.0:
        notes.append("System is not yet profitable on replay. Maintain conservative sizing.")
        proposed_actions.append({
            "type": "config_review",
            "target": "trade_signal_weights.json",
            "action": "downweight_weak_setups",
            "reason": "profit_factor_below_one"
        })

    if max_drawdown_pct < 1.0 and realized_pnl_usd < 0:
        notes.append("Losses are controlled, suggesting weak edge rather than excessive risk.")
        proposed_actions.append({
            "type": "threshold_review",
            "target": "paper_trading_engine.json",
            "action": "consider_stricter_entry_filters",
            "reason": "controlled_drawdown_negative_pnl"
        })

    bearish_pnl = (
        safe_float(safe_dict(directions.get("bearish")).get("realized_pnl_usd"), 0.0) +
        safe_float(safe_dict(directions.get("strong_bearish")).get("realized_pnl_usd"), 0.0)
    )
    bullish_pnl = (
        safe_float(safe_dict(directions.get("bullish")).get("realized_pnl_usd"), 0.0) +
        safe_float(safe_dict(directions.get("strong_bullish")).get("realized_pnl_usd"), 0.0)
    )

    if bearish_pnl > bullish_pnl:
        notes.append("Short-side setups are outperforming long-side setups in observed replay.")
        proposed_actions.append({
            "type": "bias_review",
            "target": "trade_signal_engine",
            "action": "favor_short_side_experiments",
            "reason": "bearish_side_outperforming"
        })
    elif bullish_pnl > bearish_pnl:
        notes.append("Long-side setups are outperforming short-side setups in observed replay.")
        proposed_actions.append({
            "type": "bias_review",
            "target": "trade_signal_engine",
            "action": "favor_long_side_experiments",
            "reason": "bullish_side_outperforming"
        })

    if safe_int(signal_summary.get("trade_row_count"), 0) > 0 and safe_int(open_summary.get("open_position_count"), 0) == 0:
        notes.append("Signal generation is active, but execution is not carrying exposure currently.")
        proposed_actions.append({
            "type": "execution_review",
            "target": "paper_trading_engine.json",
            "action": "inspect_entry_and_hold_filters",
            "reason": "signals_present_no_open_positions"
        })

    if not strong_setups:
        notes.append("No setup families have produced positive realized PnL yet.")
        proposed_actions.append({
            "type": "observation",
            "target": "strategy_performance",
            "action": "continue_collecting_samples",
            "reason": "no_positive_setup_families"
        })

    return {
        "system_state": {
            "equity_usd": round(equity_usd, 4),
            "realized_pnl_usd": round(realized_pnl_usd, 4),
            "profit_factor": round(profit_factor, 6),
            "max_drawdown_pct": round(max_drawdown_pct, 4),
        },
        "strong_setups": strong_setups[:10],
        "weak_setups": weak_setups[:10],
        "notes": notes[:12],
        "proposed_actions": proposed_actions[:12],
    }


# ---------------------------------------------------
# PUBLIC ENGINE
# ---------------------------------------------------

def build_strategy_performance(write_output: bool = True) -> Dict[str, Any]:
    backtest_results = safe_dict(read_json_file(BACKTEST_RESULTS_PATH, {}))
    backtest_state = safe_dict(read_json_file(BACKTEST_STATE_PATH, {}))
    paper_state = safe_dict(read_json_file(PAPER_TRADING_STATE_PATH, {}))
    trading_snapshot = safe_dict(read_json_file(TRADING_SNAPSHOT_PATH, {}))

    backtest_closed_positions = safe_list(backtest_state.get("closed_positions"))
    live_open_positions = safe_dict(paper_state.get("open_positions"))

    closed_summary = summarize_closed_positions(backtest_closed_positions)
    open_summary = summarize_open_positions(live_open_positions)
    signal_summary = summarize_current_trade_signals(trading_snapshot)

    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "system": "ToknClaw",
        "module": "strategy_performance_engine",
        "sources": {
            "backtest_results_path": str(BACKTEST_RESULTS_PATH),
            "backtest_state_path": str(BACKTEST_STATE_PATH),
            "paper_trading_state_path": str(PAPER_TRADING_STATE_PATH),
            "trading_snapshot_path": str(TRADING_SNAPSHOT_PATH),
        },
        "backtest_snapshot": {
            "status": clean_text(backtest_results.get("status")) or "unknown",
            "snapshot_file_count": safe_int(safe_dict(backtest_results.get("input")).get("snapshot_file_count"), 0),
            "processed_snapshot_count": safe_int(safe_dict(backtest_results.get("input")).get("processed_snapshot_count"), 0),
            "portfolio": deepcopy(safe_dict(backtest_results.get("portfolio"))),
            "max_drawdown_pct": safe_float(backtest_results.get("max_drawdown_pct"), 0.0),
            "sharpe_like_ratio": safe_float(backtest_results.get("sharpe_like_ratio"), 0.0),
            "closed_position_summary": deepcopy(safe_dict(backtest_results.get("closed_position_summary"))),
        },
        "performance": {
            "closed_positions": closed_summary,
            "open_positions": open_summary,
            "current_signal_mix": signal_summary,
        },
        "agent_feedback": build_agent_recommendations(
            backtest_results=backtest_results,
            setup_summary=closed_summary,
            open_summary=open_summary,
            signal_summary=signal_summary,
        ),
    }

    if write_output:
        write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)

    return payload


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main() -> None:
    payload = build_strategy_performance(write_output=True)

    summary = {
        "status": safe_dict(payload.get("backtest_snapshot")).get("status"),
        "processed_snapshot_count": safe_dict(payload.get("backtest_snapshot")).get("processed_snapshot_count"),
        "equity_usd": safe_dict(safe_dict(payload.get("backtest_snapshot")).get("portfolio")).get("equity_usd"),
        "realized_pnl_usd": safe_dict(safe_dict(payload.get("backtest_snapshot")).get("portfolio")).get("realized_pnl_usd"),
        "profit_factor": safe_dict(safe_dict(payload.get("backtest_snapshot")).get("closed_position_summary")).get("profit_factor"),
        "weak_setups": safe_dict(payload.get("agent_feedback")).get("weak_setups"),
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
