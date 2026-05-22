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
# MODULE: strategy_decision_engine
# PURPOSE: Convert simulation and realized strategy analytics into agent-ready
#          decisions, health states, and config patch proposals without
#          directly mutating execution configs.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• compare simulated expectations vs realized performance
• classify strategy health and confidence
• generate agent-ready recommendations
• emit config patch proposals instead of directly changing configs
• remain safe, read-only, and OpenClaw hook ready

Primary Inputs
--------------
/opt/toknclaw/data/analytics/strategy_performance.json
/opt/toknclaw/data/backtests/latest_backtest_results.json
/opt/toknclaw/data/paper_trading_state.json
/opt/toknclaw/data/snapshots/latest_snapshot_trading.json
/opt/toknclaw/data/analytics/strategy_simulation.json (optional)

Primary Output
--------------
/opt/toknclaw/data/analytics/strategy_decisions.json
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
from datetime import UTC, datetime
from typing import Any, Dict, List

# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

ANALYTICS_DIR = Path("/opt/toknclaw/data/analytics")

STRATEGY_PERFORMANCE_PATH = ANALYTICS_DIR / "strategy_performance.json"
STRATEGY_SIMULATION_PATH = ANALYTICS_DIR / "strategy_simulation.json"

BACKTEST_RESULTS_PATH = Path("/opt/toknclaw/data/backtests/latest_backtest_results.json")
PAPER_TRADING_STATE_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")
TRADING_SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")

OUTPUT_PATH = ANALYTICS_DIR / "strategy_decisions.json"
TMP_OUTPUT_PATH = ANALYTICS_DIR / "strategy_decisions.tmp"

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def clean_text(value: Any) -> str:
    return str(value or "").strip()


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


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))

# ---------------------------------------------------
# LOADERS
# ---------------------------------------------------

def load_strategy_performance() -> Dict[str, Any]:
    return safe_dict(read_json_file(STRATEGY_PERFORMANCE_PATH, {}))


def load_strategy_simulation() -> Dict[str, Any]:
    return safe_dict(read_json_file(STRATEGY_SIMULATION_PATH, {}))


def load_backtest_results() -> Dict[str, Any]:
    return safe_dict(read_json_file(BACKTEST_RESULTS_PATH, {}))


def load_paper_state() -> Dict[str, Any]:
    return safe_dict(read_json_file(PAPER_TRADING_STATE_PATH, {}))


def load_trading_snapshot() -> Dict[str, Any]:
    return safe_dict(read_json_file(TRADING_SNAPSHOT_PATH, {}))

# ---------------------------------------------------
# NORMALIZATION
# ---------------------------------------------------

def normalize_simulation_rows(simulation_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Supports either:
    - {"rows": [...]}
    - {"strategy_performance": {"rows": [...]}}
    """
    rows = safe_list(simulation_payload.get("rows"))
    if not rows:
        rows = safe_list(safe_dict(simulation_payload.get("strategy_performance")).get("rows"))

    out: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        strategy_id = clean_text(row.get("strategy_id")) or clean_text(row.get("strategy_name"))
        if not strategy_id:
            continue

        out[strategy_id] = row

    return out


def normalize_realized_rows(perf_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = safe_dict(safe_dict(perf_payload.get("performance")).get("closed_positions")).get("by_setup_family", {})
    out: Dict[str, Dict[str, Any]] = {}

    for family, payload in safe_dict(rows).items():
        out[clean_text(family)] = safe_dict(payload)

    return out

# ---------------------------------------------------
# HEALTH / DECISION LOGIC
# ---------------------------------------------------

def classify_realized_health(payload: Dict[str, Any]) -> str:
    count = safe_int(payload.get("count"), 0)
    pnl = safe_float(payload.get("realized_pnl_usd"), 0.0)
    win_rate = safe_float(payload.get("win_rate_pct"), 0.0)

    if count < 5:
        return "insufficient_sample"

    if pnl > 0 and win_rate >= 50.0:
        return "healthy"

    if pnl > 0 and win_rate < 50.0:
        return "fragile_positive"

    if pnl < 0 and win_rate < 45.0:
        return "underperforming"

    if pnl < 0:
        return "weak"

    return "neutral"


def confidence_from_sample(count: int) -> float:
    return round(clamp(count / 20.0), 4)


def compare_expected_vs_realized(
    simulation_rows: Dict[str, Dict[str, Any]],
    realized_rows: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    all_keys = sorted(set(simulation_rows.keys()) | set(realized_rows.keys()))
    decisions: List[Dict[str, Any]] = []

    for key in all_keys:
        sim = safe_dict(simulation_rows.get(key))
        real = safe_dict(realized_rows.get(key))

        realized_count = safe_int(real.get("count"), 0)
        realized_pnl = safe_float(real.get("realized_pnl_usd"), 0.0)
        realized_win_rate = safe_float(real.get("win_rate_pct"), 0.0)

        expected_score = safe_float(sim.get("performance_score"), 0.0)
        expected_hit_rate = safe_float(sim.get("hit_rate"), 0.0)

        health = classify_realized_health(real)
        sample_confidence = confidence_from_sample(realized_count)

        drift = "unknown"
        if sim and real:
            if expected_score >= 0.60 and realized_pnl < 0:
                drift = "expected_good_real_bad"
            elif expected_score < 0.40 and realized_pnl > 0:
                drift = "expected_bad_real_good"
            elif expected_score >= 0.60 and realized_pnl > 0:
                drift = "aligned_positive"
            elif expected_score < 0.40 and realized_pnl < 0:
                drift = "aligned_negative"
            else:
                drift = "mixed"

        actions: List[Dict[str, Any]] = []
        notes: List[str] = []

        if health == "underperforming":
            actions.append({
                "type": "weight_reduction_candidate",
                "target": key,
                "severity": "high",
                "patch": {
                    "config_file": "trade_signal_weights.json",
                    "operation": "downweight"
                }
            })
            notes.append("Realized performance is negative with a sufficient sample.")
        elif health == "weak":
            actions.append({
                "type": "threshold_review_candidate",
                "target": key,
                "severity": "medium",
                "patch": {
                    "config_file": "paper_trading_engine.json",
                    "operation": "tighten_entry_gate"
                }
            })
            notes.append("Realized performance is weak but not yet catastrophic.")
        elif health == "healthy":
            actions.append({
                "type": "promotion_candidate",
                "target": key,
                "severity": "low",
                "patch": {
                    "config_file": "trade_signal_weights.json",
                    "operation": "upweight_after_validation"
                }
            })
            notes.append("Realized performance is positive with acceptable win rate.")
        elif health == "insufficient_sample":
            actions.append({
                "type": "observe_candidate",
                "target": key,
                "severity": "low",
                "patch": {
                    "config_file": None,
                    "operation": "collect_more_data"
                }
            })
            notes.append("Sample size is too small to justify a config change.")

        if drift == "expected_good_real_bad":
            notes.append("Simulation disagrees with realized behavior. Possible strategy drift.")
            actions.append({
                "type": "simulation_drift_review",
                "target": key,
                "severity": "high",
                "patch": {
                    "config_file": "trade_signal_weights.json",
                    "operation": "downweight_until_revalidated"
                }
            })

        if drift == "expected_bad_real_good":
            notes.append("Realized behavior is outperforming simulation expectations.")
            actions.append({
                "type": "unexpected_strength_review",
                "target": key,
                "severity": "medium",
                "patch": {
                    "config_file": "trade_signal_weights.json",
                    "operation": "consider_upweight_after_more_samples"
                }
            })

        decisions.append({
            "strategy_key": key,
            "expected": {
                "performance_score": expected_score,
                "hit_rate": expected_hit_rate,
            },
            "realized": {
                "count": realized_count,
                "realized_pnl_usd": round(realized_pnl, 4),
                "win_rate_pct": realized_win_rate,
                "health": health,
            },
            "drift": drift,
            "sample_confidence": sample_confidence,
            "notes": notes,
            "actions": actions,
        })

    decisions.sort(
        key=lambda x: (
            x["realized"]["health"] == "underperforming",
            x["realized"]["health"] == "weak",
            -safe_float(x["sample_confidence"], 0.0),
            abs(safe_float(x["realized"]["realized_pnl_usd"], 0.0)),
        ),
        reverse=True,
    )

    return decisions


def build_global_decisions(
    performance_payload: Dict[str, Any],
    backtest_results: Dict[str, Any],
    paper_state: Dict[str, Any],
    trading_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    backtest_portfolio = safe_dict(backtest_results.get("portfolio"))
    closed_summary = safe_dict(backtest_results.get("closed_position_summary"))
    perf_feedback = safe_dict(performance_payload.get("agent_feedback"))

    equity_usd = safe_float(backtest_portfolio.get("equity_usd"), 0.0)
    realized_pnl_usd = safe_float(backtest_portfolio.get("realized_pnl_usd"), 0.0)
    max_drawdown_pct = safe_float(backtest_results.get("max_drawdown_pct"), 0.0)
    profit_factor = safe_float(closed_summary.get("profit_factor"), 0.0)

    open_positions = safe_dict(paper_state.get("open_positions"))
    trade_rows = safe_list(safe_dict(trading_snapshot.get("trade_signals")).get("rows"))

    notes: List[str] = []
    actions: List[Dict[str, Any]] = []

    if profit_factor < 1.0:
        notes.append("System remains unprofitable on replay. Do not increase aggression.")
        actions.append({
            "type": "global_safety",
            "target": "trade_signal_weights.json",
            "severity": "high",
            "patch": {
                "operation": "hold_or_reduce_risk"
            }
        })

    if max_drawdown_pct < 1.0 and realized_pnl_usd < 0:
        notes.append("Losses are contained. Main issue appears to be edge quality, not runaway risk.")
        actions.append({
            "type": "global_diagnosis",
            "target": "paper_trading_engine.json",
            "severity": "medium",
            "patch": {
                "operation": "review_entry_quality_filters"
            }
        })

    if len(open_positions) == 0 and len(trade_rows) > 0:
        notes.append("Signal generation is active but current exposure is flat.")
        actions.append({
            "type": "execution_review",
            "target": "paper_trading_engine.json",
            "severity": "medium",
            "patch": {
                "operation": "inspect_entry_vs_hold_constraints"
            }
        })

    for weak in safe_list(perf_feedback.get("weak_setups"))[:5]:
        actions.append({
            "type": "family_watchlist",
            "target": clean_text(safe_dict(weak).get("setup_family")),
            "severity": "medium",
            "patch": {
                "operation": "watch_or_downweight",
                "reason": "weak_setup_family"
            }
        })

    return {
        "portfolio_state": {
            "equity_usd": round(equity_usd, 4),
            "realized_pnl_usd": round(realized_pnl_usd, 4),
            "profit_factor": round(profit_factor, 6),
            "max_drawdown_pct": round(max_drawdown_pct, 4),
            "open_position_count": len(open_positions),
            "trade_row_count": len(trade_rows),
        },
        "notes": notes[:12],
        "actions": actions[:20],
    }

# ---------------------------------------------------
# PUBLIC ENGINE
# ---------------------------------------------------

def build_strategy_decisions(write_output: bool = True) -> Dict[str, Any]:
    performance_payload = load_strategy_performance()
    simulation_payload = load_strategy_simulation()
    backtest_results = load_backtest_results()
    paper_state = load_paper_state()
    trading_snapshot = load_trading_snapshot()

    simulation_rows = normalize_simulation_rows(simulation_payload)
    realized_rows = normalize_realized_rows(performance_payload)

    strategy_decisions = compare_expected_vs_realized(
        simulation_rows=simulation_rows,
        realized_rows=realized_rows,
    )

    global_decisions = build_global_decisions(
        performance_payload=performance_payload,
        backtest_results=backtest_results,
        paper_state=paper_state,
        trading_snapshot=trading_snapshot,
    )

    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "system": "ToknClaw",
        "module": "strategy_decision_engine",
        "sources": {
            "strategy_performance_path": str(STRATEGY_PERFORMANCE_PATH),
            "strategy_simulation_path": str(STRATEGY_SIMULATION_PATH),
            "backtest_results_path": str(BACKTEST_RESULTS_PATH),
            "paper_trading_state_path": str(PAPER_TRADING_STATE_PATH),
            "trading_snapshot_path": str(TRADING_SNAPSHOT_PATH),
        },
        "global_decisions": global_decisions,
        "strategy_decisions": strategy_decisions,
        "openclaw_handoff": {
            "ready": True,
            "recommended_next_actor": "openclaw_agent",
            "approved_mutation_targets": [
                "trade_signal_weights.json",
                "paper_trading_engine.json",
                "price_oi_trend_engine.json"
            ],
            "mutation_policy": "config_only_no_code_changes",
        },
    }

    if write_output:
        write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)

    return payload

# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main() -> None:
    payload = build_strategy_decisions(write_output=True)

    summary = {
        "generated_at": payload.get("generated_at"),
        "global_notes": safe_dict(payload.get("global_decisions")).get("notes"),
        "global_actions": len(safe_dict(payload.get("global_decisions")).get("actions")),
        "strategy_decision_count": len(safe_list(payload.get("strategy_decisions"))),
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
