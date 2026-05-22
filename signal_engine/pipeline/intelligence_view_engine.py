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
# MODULE: intelligence_view_engine
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
Intelligence View Engine

Purpose
-------
Build an intelligence-only API-ready view from the unified ToknClaw brain.

This module is designed to:
• read the central snapshot without mutating it
• expose research / agent / analytics relevant state only
• support website intelligence dashboards and OpenClaw agents
• remain additive and future-proof
• preserve separation between trading, intelligence, and media layers

Primary Input
-------------
/opt/toknclaw/data/snapshots/latest_snapshot.json

Primary Output
--------------
/opt/toknclaw/data/views/intelligence_view.json

Design Notes
------------
• no direct RPC calls
• no collector execution
• pure derived view
• stable contract for future agents and UI
• broad enough for complete system awareness

Author: TOKN Systems
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot.json")
OUTPUT_PATH = Path("/opt/toknclaw/data/views/intelligence_view.json")
TMP_OUTPUT_PATH = Path("/opt/toknclaw/data/views/intelligence_view.tmp")


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


def load_snapshot() -> Dict[str, Any]:
    data = read_json_file(SNAPSHOT_PATH, {})
    if isinstance(data, dict):
        return data
    return {}


def object_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    out: List[Dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
    return out


def top_n(rows: List[Any], n: int) -> List[Any]:
    return rows[:max(0, n)]


def signal_type_counts(signals: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for row in signals:
        signal_type = clean_text(row.get("signal_type"))
        if not signal_type:
            continue
        counts[signal_type] = counts.get(signal_type, 0) + 1

    return counts


def source_counts(signals: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for row in signals:
        source = clean_text(row.get("source"))
        if not source:
            continue
        counts[source] = counts.get(source, 0) + 1

    return counts


def entity_counts(signals: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for row in signals:
        entity = clean_text(row.get("entity"))
        if not entity:
            continue
        counts[entity] = counts.get(entity, 0) + 1

    return counts


def top_dict_items(d: Dict[str, int], n: int) -> List[Dict[str, Any]]:
    items = sorted(d.items(), key=lambda x: x[1], reverse=True)
    return [{"key": k, "count": v} for k, v in items[:n]]


def safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


# ---------------------------------------------------
# OVERVIEW
# ---------------------------------------------------

def build_overview(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    metrics = safe_dict(snapshot.get("metrics"))
    source_health = safe_dict(snapshot.get("source_health"))

    return {
        "updated_at": utc_now_iso(),
        "snapshot_timestamp": snapshot.get("timestamp"),
        "total_signals": safe_int(metrics.get("total_signals", 0)),
        "unique_entities": safe_int(metrics.get("unique_entities", 0)),
        "source_count": len(safe_dict(metrics.get("sources"))),
        "signal_type_count": len(safe_dict(metrics.get("signal_types"))),
        "overall_source_status": clean_text(source_health.get("overall_status")),
        "system_health": safe_dict(metrics.get("system_health")),
    }


# ---------------------------------------------------
# SIGNAL INTELLIGENCE
# ---------------------------------------------------

def build_signal_intelligence(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    signals = object_rows(snapshot.get("signals", []))
    metrics = safe_dict(snapshot.get("metrics"))

    return {
        "updated_at": utc_now_iso(),
        "summary": {
            "total_signals": len(signals),
            "top_signal_types": top_dict_items(signal_type_counts(signals), 25),
            "top_sources": top_dict_items(source_counts(signals), 20),
            "top_entities": top_dict_items(entity_counts(signals), 25),
            "headline_samples": top_n(metrics.get("headline_samples", []), 20),
        },
        "solana_activity": safe_dict(metrics.get("solana_activity")),
        "solana_summary": safe_dict(metrics.get("solana_summary")),
    }


# ---------------------------------------------------
# CLUSTER INTELLIGENCE
# ---------------------------------------------------

def build_cluster_intelligence(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    clusters = object_rows(snapshot.get("clusters", []))
    cluster_analysis = safe_dict(snapshot.get("cluster_analysis"))

    return {
        "updated_at": utc_now_iso(),
        "summary": {
            "cluster_count": len(clusters),
            "analysis_keys": sorted(cluster_analysis.keys()),
        },
        "clusters": top_n(clusters, 100),
        "cluster_analysis": cluster_analysis,
    }


# ---------------------------------------------------
# NARRATIVE INTELLIGENCE
# ---------------------------------------------------

def build_narrative_intelligence(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    narratives = object_rows(snapshot.get("narratives", []))
    narrative_alerts = object_rows(snapshot.get("narrative_alerts", []))
    narrative_correlations = object_rows(snapshot.get("narrative_correlations", []))
    narrative_arcs = object_rows(snapshot.get("narrative_arcs", []))

    return {
        "updated_at": utc_now_iso(),
        "summary": {
            "narrative_count": len(narratives),
            "narrative_alert_count": len(narrative_alerts),
            "correlation_count": len(narrative_correlations),
            "arc_count": len(narrative_arcs),
        },
        "narrative_summary": safe_dict(snapshot.get("narrative_summary")),
        "narratives": top_n(narratives, 50),
        "narrative_alerts": top_n(narrative_alerts, 50),
        "narrative_correlations": top_n(narrative_correlations, 50),
        "narrative_correlation_summary": safe_dict(snapshot.get("narrative_correlation_summary")),
        "narrative_arcs": top_n(narrative_arcs, 50),
        "memory": safe_dict(snapshot.get("memory")),
        "deltas": safe_dict(snapshot.get("deltas")),
    }


# ---------------------------------------------------
# ENTITY INTELLIGENCE
# ---------------------------------------------------

def build_entity_intelligence_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    entity_intelligence = object_rows(snapshot.get("entity_intelligence", []))
    entity_discovery = safe_dict(snapshot.get("entity_discovery"))

    return {
        "updated_at": utc_now_iso(),
        "summary": {
            "entity_intelligence_count": len(entity_intelligence),
            "entity_discovery_keys": sorted(entity_discovery.keys()),
        },
        "entity_intelligence": top_n(entity_intelligence, 100),
        "entity_discovery": entity_discovery,
    }


# ---------------------------------------------------
# MARKET INTELLIGENCE
# ---------------------------------------------------

def build_market_intelligence(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "updated_at": utc_now_iso(),
        "market_regime": safe_dict(snapshot.get("market_regime")),
        "signal_velocity": safe_dict(snapshot.get("signal_velocity")),
        "cross_asset_intelligence": safe_dict(snapshot.get("cross_asset_intelligence")),
        "macro_liquidity": safe_dict(snapshot.get("macro_liquidity")),
        "institutional_flows": safe_dict(snapshot.get("institutional_flows")),
        "market_stress": safe_dict(snapshot.get("market_stress")),
        "liquidity_rotation": safe_dict(snapshot.get("liquidity_rotation")),
        "market_structure": safe_dict(snapshot.get("market_structure")),
    }


# ---------------------------------------------------
# STRATEGY + RESEARCH INTELLIGENCE
# ---------------------------------------------------

def build_strategy_research_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    strategy_candidates = object_rows(snapshot.get("strategy_candidates", []))
    optimized_strategies = object_rows(snapshot.get("optimized_strategies", []))
    strategy_allocations = object_rows(snapshot.get("strategy_allocations", []))
    strategy_performance = object_rows(snapshot.get("strategy_performance", []))
    adaptive_strategy_weights = object_rows(snapshot.get("adaptive_strategy_weights", []))
    adaptive_family_weights = object_rows(snapshot.get("adaptive_strategy_family_weights", []))
    quant_factors = object_rows(snapshot.get("quant_factors", []))
    trade_signals = object_rows(snapshot.get("trade_signals", []))
    conviction_scores = object_rows(snapshot.get("conviction_scores", []))

    return {
        "updated_at": utc_now_iso(),
        "summary": {
            "strategy_candidate_count": len(strategy_candidates),
            "optimized_strategy_count": len(optimized_strategies),
            "strategy_allocation_count": len(strategy_allocations),
            "strategy_performance_count": len(strategy_performance),
            "adaptive_strategy_weight_count": len(adaptive_strategy_weights),
            "adaptive_family_weight_count": len(adaptive_family_weights),
            "quant_factor_count": len(quant_factors),
            "trade_signal_count": len(trade_signals),
            "conviction_score_count": len(conviction_scores),
        },
        "strategy_candidates": top_n(strategy_candidates, 100),
        "optimized_strategies": top_n(optimized_strategies, 100),
        "strategy_allocations": top_n(strategy_allocations, 100),
        "strategy_allocation_summary": safe_dict(snapshot.get("strategy_allocation_summary")),
        "strategy_allocation_alerts": object_rows(snapshot.get("strategy_allocation_alerts", [])),
        "strategy_performance": top_n(strategy_performance, 100),
        "adaptive_strategy_weight_summary": safe_dict(snapshot.get("adaptive_strategy_weight_summary")),
        "adaptive_strategy_weights": top_n(adaptive_strategy_weights, 100),
        "adaptive_strategy_family_weights": top_n(adaptive_family_weights, 50),
        "quant_factors": top_n(quant_factors, 100),
        "trade_signals": top_n(trade_signals, 100),
        "conviction_scores": top_n(conviction_scores, 100),
    }


# ---------------------------------------------------
# EXECUTION + RISK INTELLIGENCE
# ---------------------------------------------------

def build_execution_risk_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    execution_router = object_rows(snapshot.get("execution_router", []))
    order_lifecycle = object_rows(snapshot.get("order_lifecycle", []))
    position_risk = object_rows(snapshot.get("position_risk", []))
    risks = object_rows(snapshot.get("risks", []))

    return {
        "updated_at": utc_now_iso(),
        "summary": {
            "execution_router_count": len(execution_router),
            "order_lifecycle_count": len(order_lifecycle),
            "position_risk_count": len(position_risk),
            "risk_count": len(risks),
        },
        "execution_router": top_n(execution_router, 100),
        "execution_router_summary": safe_dict(snapshot.get("execution_router_summary")),
        "execution_router_alerts": object_rows(snapshot.get("execution_router_alerts", [])),
        "position_risk": top_n(position_risk, 100),
        "position_risk_summary": safe_dict(snapshot.get("position_risk_summary")),
        "order_lifecycle": top_n(order_lifecycle, 100),
        "kill_switch": safe_dict(snapshot.get("kill_switch")),
        "risks": top_n(risks, 100),
    }


# ---------------------------------------------------
# BACKTEST / PAPER / ATTRIBUTION
# ---------------------------------------------------

def build_experimentation_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "updated_at": utc_now_iso(),
        "backtests": safe_dict(snapshot.get("backtests")),
        "paper_trading": safe_dict(snapshot.get("paper_trading")),
        "alpha_attribution": safe_dict(snapshot.get("alpha_attribution")),
        "strategy_simulation": safe_dict(snapshot.get("strategy_simulation")),
        "strategy_simulation_summary": safe_dict(snapshot.get("strategy_simulation_summary")),
        "strategy_simulation_alerts": object_rows(snapshot.get("strategy_simulation_alerts", [])),
    }


# ---------------------------------------------------
# SOURCE HEALTH + OPERATIONS
# ---------------------------------------------------

def build_operations_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    source_health = safe_dict(snapshot.get("source_health"))
    analysis = safe_dict(snapshot.get("analysis"))
    calendar = safe_dict(snapshot.get("calendar")) if isinstance(snapshot.get("calendar"), dict) else snapshot.get("calendar")

    return {
        "updated_at": utc_now_iso(),
        "source_health": source_health,
        "analysis": analysis,
        "calendar": calendar,
    }


# ---------------------------------------------------
# AGENT CONTEXT
# ---------------------------------------------------

def build_agent_context(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    signals = object_rows(snapshot.get("signals", []))
    metrics = safe_dict(snapshot.get("metrics"))

    top_signal_types = top_dict_items(signal_type_counts(signals), 15)
    top_entities = top_dict_items(entity_counts(signals), 15)

    return {
        "updated_at": utc_now_iso(),
        "system_summary": {
            "total_signals": len(signals),
            "cluster_count": len(object_rows(snapshot.get("clusters", []))),
            "narrative_count": len(object_rows(snapshot.get("narratives", []))),
            "unique_entities": safe_int(metrics.get("unique_entities", 0)),
            "unique_sources": len(safe_dict(metrics.get("sources"))),
        },
        "top_signal_types": top_signal_types,
        "top_entities": top_entities,
        "market_regime": safe_dict(snapshot.get("market_regime")),
        "source_health": safe_dict(snapshot.get("source_health")),
        "adaptive_strategy_weight_summary": safe_dict(snapshot.get("adaptive_strategy_weight_summary")),
    }


# ---------------------------------------------------
# MASTER VIEW
# ---------------------------------------------------

def build_intelligence_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "view_name": "intelligence",
        "updated_at": utc_now_iso(),
        "overview": build_overview(snapshot),
        "signal_intelligence": build_signal_intelligence(snapshot),
        "cluster_intelligence": build_cluster_intelligence(snapshot),
        "narrative_intelligence": build_narrative_intelligence(snapshot),
        "entity_intelligence": build_entity_intelligence_view(snapshot),
        "market_intelligence": build_market_intelligence(snapshot),
        "strategy_research": build_strategy_research_view(snapshot),
        "execution_risk": build_execution_risk_view(snapshot),
        "experimentation": build_experimentation_view(snapshot),
        "operations": build_operations_view(snapshot),
        "agent_context": build_agent_context(snapshot),
    }


def run_intelligence_view_engine() -> Dict[str, Any]:
    snapshot = load_snapshot()
    view = build_intelligence_view(snapshot)
    write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, view)
    return view


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    payload = run_intelligence_view_engine()
    print(json.dumps(payload, indent=2))
