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
# MODULE: agent_orchestration_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Any, Dict, List


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _build_tasks(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks = []

    narrative_regime = _safe_dict(snapshot.get("narrative_regime_summary"))
    volatility = _safe_dict(snapshot.get("volatility_summary"))
    cross_asset = _safe_dict(snapshot.get("cross_asset_correlation_summary"))
    market_stress = _safe_dict(snapshot.get("market_stress_summary"))
    cluster_summary = _safe_dict(snapshot.get("cluster_explorer_summary"))
    alpha_summary = _safe_dict(snapshot.get("alpha_attribution_summary"))
    strategy_summary = _safe_dict(snapshot.get("strategy_simulation_summary"))

    if _safe_str(market_stress.get("regime")) in {"severe_stress", "elevated_stress"}:
        tasks.append({
            "agent": "risk_monitor_agent",
            "priority": "high",
            "task_type": "stress_review",
            "instruction": "Review stress propagation, entity hotspots, and downgrade aggressive strategy recommendations.",
        })

    if _safe_str(volatility.get("regime")) in {"extreme_volatility", "high_volatility"}:
        tasks.append({
            "agent": "strategy_analyst_agent",
            "priority": "high",
            "task_type": "volatility_adjustment",
            "instruction": "Re-evaluate strategy thresholds under elevated volatility conditions.",
        })

    if _safe_str(narrative_regime.get("regime")) in {"institutional_expansion", "speculative_rotation", "defensive_repricing"}:
        tasks.append({
            "agent": "market_narrator_agent",
            "priority": "medium",
            "task_type": "broadcast_brief",
            "instruction": f'Generate a market brief for narrative regime {_safe_str(narrative_regime.get("regime"))}.',
        })

    if _safe_float(cross_asset.get("top_score"), 0.0) >= 0.70:
        tasks.append({
            "agent": "cross_asset_research_agent",
            "priority": "medium",
            "task_type": "correlation_review",
            "instruction": "Review elevated cross-asset linkages and identify whether correlation is macro-, policy-, or liquidity-driven.",
        })

    if _safe_float(cluster_summary.get("cluster_count"), 0.0) > 0:
        tasks.append({
            "agent": "cluster_research_agent",
            "priority": "low",
            "task_type": "cluster_refresh",
            "instruction": "Review top clusters and refresh context for system explorer payloads.",
        })

    if _safe_str(alpha_summary.get("top_component")):
        tasks.append({
            "agent": "alpha_optimizer_agent",
            "priority": "medium",
            "task_type": "alpha_component_review",
            "instruction": f'Review top alpha component {_safe_str(alpha_summary.get("top_component"))} and compare against active strategy templates.',
        })

    if _safe_str(strategy_summary.get("top_strategy")):
        tasks.append({
            "agent": "strategy_execution_preparer",
            "priority": "medium",
            "task_type": "paper_trading_review",
            "instruction": f'Prepare paper-trading recommendations for strategy {_safe_str(strategy_summary.get("top_strategy"))}.',
        })

    return tasks


def build_agent_orchestration(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    tasks = _build_tasks(snapshot)

    summary = {
        "task_count": len(tasks),
        "high_priority_count": sum(1 for t in tasks if t.get("priority") == "high"),
        "top_agent": tasks[0]["agent"] if tasks else None,
    }

    return {
        "agent_orchestration": {
            "tasks": tasks,
        },
        "agent_orchestration_summary": summary,
        "agent_orchestration_endpoints": {
            "agent_orchestration": "/api/toknclaw/agents/orchestration",
            "agent_orchestration_summary": "/api/toknclaw/agents/orchestration/summary",
        },
    }
