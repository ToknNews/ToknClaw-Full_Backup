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
# MODULE: strategy_reinforcement_engine
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
Autonomous Market Intelligence Platform

Strategy Reinforcement Engine
-----------------------------
Scores and reinforces strategy quality for:

• adaptive strategy weighting
• persistent strategy preference
• reinforcement state transitions
• future RL policy loops
• future self-improving bot logic

This module orchestrates strategy reinforcement logic in ToknClaw.

Author: TOKN Systems
"""

from __future__ import annotations

from typing import Any, Dict, List


# ---------------------------------------------------
# Helpers
# ---------------------------------------------------

def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------
# Scoring
# ---------------------------------------------------

def _reinforcement_score(row: Dict[str, Any], snapshot: Dict[str, Any]) -> float:
    row = _safe_dict(row)

    perf = _safe_dict(row.get("performance"))
    hit_rate = _safe_float(perf.get("hit_rate"), 0.0)
    pnl = _safe_float(perf.get("avg_pnl_proxy"), 0.0)
    sharpe = _safe_float(perf.get("sharpe_proxy"), 0.0)
    perf_score = _safe_float(perf.get("performance_score"), 0.0)

    market_regime = _safe_str(_safe_dict(snapshot.get("market_regime")).get("name"))
    macro_regime = _safe_str(_safe_dict(snapshot.get("macro_liquidity_summary")).get("regime"))
    stress_regime = _safe_str(_safe_dict(snapshot.get("market_stress_summary")).get("regime"))

    regime_bonus = 0.0

    if market_regime in {"defi_expansion_cycle", "institutional_accumulation_phase"}:
        regime_bonus += 0.05

    if macro_regime in {"global_liquidity_expansion", "risk_on_liquidity"}:
        regime_bonus += 0.05

    if stress_regime in {"elevated_stress", "severe_stress"}:
        regime_bonus -= 0.08

    raw = (
        hit_rate * 0.30 +
        perf_score * 0.30 +
        sharpe * 0.20 +
        max(pnl, 0.0) * 0.20 +
        regime_bonus
    )

    return round(_clamp(raw), 4)


def _state_from_score(score: float) -> str:
    if score >= 0.75:
        return "promoted"
    if score >= 0.55:
        return "favored"
    if score >= 0.35:
        return "neutral"
    return "deprioritized"


# ---------------------------------------------------
# Main engine
# ---------------------------------------------------

def build_strategy_reinforcement(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    genome_rows = _safe_list(snapshot.get("strategy_genome"))

    rows = []

    total_score = 0.0

    for row in genome_rows:
        row = _safe_dict(row)

        score = _reinforcement_score(row, snapshot)
        state = _state_from_score(score)

        rows.append({
            "strategy_id": row.get("strategy_id"),
            "strategy_name": row.get("strategy_name"),
            "status": row.get("status"),
            "reinforcement_score": score,
            "reinforcement_state": state,
        })

        total_score += score

    total_score = max(total_score, 0.0001)

    for row in rows:
        row["reinforcement_weight"] = round(_safe_float(row.get("reinforcement_score")) / total_score, 4)

    rows.sort(
        key=lambda x: (
            _safe_float(x.get("reinforcement_score"), 0.0),
            _safe_str(x.get("strategy_id")),
        ),
        reverse=True,
    )

    summary = {
        "strategy_count": len(rows),
        "top_strategy": rows[0].get("strategy_id") if rows else None,
        "top_score": rows[0].get("reinforcement_score") if rows else 0.0,
        "promoted_count": sum(1 for r in rows if _safe_str(r.get("reinforcement_state")) == "promoted"),
        "deprioritized_count": sum(1 for r in rows if _safe_str(r.get("reinforcement_state")) == "deprioritized"),
    }

    alerts = []

    if summary["promoted_count"] > 0:
        alerts.append({
            "type": "strategies_promoted",
            "severity": "medium",
            "title": "One or more strategies are strongly reinforced",
        })

    if summary["deprioritized_count"] > 0:
        alerts.append({
            "type": "strategies_deprioritized",
            "severity": "low",
            "title": "One or more strategies have been deprioritized",
        })

    return {
        "strategy_reinforcement": rows,
        "strategy_reinforcement_summary": summary,
        "strategy_reinforcement_alerts": alerts,
        "strategy_reinforcement_endpoints": {
            "strategy_reinforcement": "/api/toknclaw/strategy-reinforcement",
            "strategy_reinforcement_summary": "/api/toknclaw/strategy-reinforcement/summary",
            "strategy_reinforcement_alerts": "/api/toknclaw/strategy-reinforcement/alerts",
        },
    }
