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
# MODULE: snapshot
# PURPOSE: Builds the full ToknClaw intelligence graph and now
#          attaches canonical trading_state output.
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

from signal_engine import bootstrap

import time
from types import SimpleNamespace
from typing import Any, Dict, List

# ---------------------------------------------------
# EXISTING IMPORTS (UNCHANGED)
# ---------------------------------------------------

from signal_engine.pipeline.collector_loader import run_collectors
from signal_engine.pipeline.price_engine import update_price_history
from signal_engine.pipeline.asset_registry_engine import (
    get_registry_lookup,
    discover_entity,
)

from pipeline.ranker import compute_score
from pipeline.metrics import compute_metrics
from pipeline.analyst import analyze

from pipeline.cluster_engine import build_clusters
from pipeline.cluster_analyst import analyze_clusters

from pipeline.narrative_engine import (
    build_narratives,
    build_narrative_summary,
    build_narrative_alerts,
)
from pipeline.narrative_correlation_engine import (
    build_narrative_correlations,
    build_narrative_correlation_summary,
)
from pipeline.narrative_memory import update_narrative_memory
from pipeline.arc_engine import build_narrative_arcs

from pipeline.entity_memory import build_entity_intelligence
from pipeline.entity_discovery_engine import run_entity_discovery

from pipeline.regime_engine import build_market_regime
from pipeline.signal_velocity_engine import build_signal_velocity
from pipeline.cross_asset_intelligence_engine import build_cross_asset_intelligence

from pipeline.macro_liquidity_engine import build_macro_liquidity
from pipeline.institutional_flow_engine import build_institutional_flows
from pipeline.market_stress_engine import build_market_stress
from pipeline.liquidity_rotation_engine import build_liquidity_rotation
from pipeline.market_structure_engine import build_market_structure

from pipeline.quant_factor_engine import build_quant_factors
from pipeline.trade_signal_engine import build_trade_signals
from pipeline.conviction_engine import build_conviction_scores

from pipeline.strategy_registry_engine import load_strategy_registry
from pipeline.strategy_candidate_engine import build_strategy_candidates
from pipeline.strategy_optimizer_engine import optimize_strategies
from pipeline.strategy_allocation_engine import build_strategy_allocation
from pipeline.strategy_simulation_engine import build_strategy_simulation
from pipeline.strategy_performance_engine import build_strategy_performance
from pipeline.position_risk_engine import build_position_risk
from pipeline.execution_router_engine import build_execution_router
from pipeline.order_lifecycle_engine import build_order_lifecycle
from pipeline.kill_switch_engine import build_kill_switch

from pipeline.backtesting_engine import build_backtests
from pipeline.paper_trading_engine import build_paper_trading
from pipeline.alpha_attribution_engine import build_alpha_attribution
from pipeline.adaptive_strategy_weighting_engine import build_adaptive_strategy_weighting
from pipeline.history_store import persist_snapshot

# 🔴 NEW IMPORT (ONLY ADDITION)
from pipeline.trading_state_engine import build_trading_state

from schema.snapshot_schema import empty_snapshot, normalize_signals
from health.source_health import summarize

from verticals.culture import build_culture_vertical
from verticals.watchlists import build_watchlists
from verticals.calendar import build_calendar
from verticals.analysis import build_risks

from signal_engine.runtime_config import load_config
from signal_lake import load_signal_lake
from signal_engine.pipeline.output_router import build_output_views
from signal_engine.pipeline.entity_registry_engine import build_entity_registry

# ---------------------------------------------------
# EXISTING LOGIC (UNCHANGED UNTIL FINAL INSERT)
# ---------------------------------------------------

collector_cfg = load_config("collector_settings.json")

MAX_PER_ENTITY = collector_cfg.get("max_signals_per_entity", 10)
MAX_TOTAL = collector_cfg.get("max_signals_per_snapshot", 500)

def _to_obj(signal: Any) -> Any:
    if isinstance(signal, dict):
        return SimpleNamespace(**signal)
    return signal

def dedupe(signals: List[Any]) -> List[Any]:
    seen = set()
    out = []
    for s in signals:
        key = (
            getattr(s, "source", None),
            getattr(s, "signal_type", None),
            getattr(s, "title", None),
            getattr(s, "entity", None),
            getattr(s, "raw_url", None),
            getattr(s, "summary", None),
        )
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out

def diversify(signals: List[Any]) -> List[Any]:
    entity_counts = {}
    out = []
    for s in signals:
        entity = getattr(s, "entity", None) or "NONE"
        if entity_counts.get(entity, 0) >= MAX_PER_ENTITY:
            continue
        entity_counts[entity] = entity_counts.get(entity, 0) + 1
        out.append(s)
        if len(out) >= MAX_TOTAL:
            break
    return out

# ---------------------------------------------------
# MAIN SNAPSHOT
# ---------------------------------------------------

def generate_snapshot() -> Dict[str, Any]:

    registry_lookup = get_registry_lookup()
    snapshot = empty_snapshot()
    snapshot["timestamp"] = time.time()

    # ---- collectors
    try:
        collector_signals, collector_health = run_collectors(mode="full")
        snapshot["signals"] = collector_signals
        snapshot["collector_health"] = collector_health
    except Exception as e:
        print("[COLLECTORS] error:", e)
        snapshot["signals"] = []

    # ---- price
    try:
        update_price_history(snapshot)
    except Exception as e:
        print("[PRICE ENGINE] error:", e)

    # ---- rank/filter
    raw_signals = [_to_obj(s) for s in snapshot["signals"]]
    raw_signals = dedupe(raw_signals)
    ranked = sorted(raw_signals, key=lambda s: compute_score(s), reverse=True)
    snapshot["signals"] = normalize_signals(ranked)

    # ---- intelligence layers (UNCHANGED)
    snapshot["clusters"] = build_clusters(snapshot["signals"])
    snapshot["cluster_analysis"] = analyze_clusters(snapshot["clusters"])

    snapshot["market_regime"] = build_market_regime(snapshot)
    snapshot["signal_velocity"] = build_signal_velocity(snapshot)
    snapshot["cross_asset_intelligence"] = build_cross_asset_intelligence(snapshot)

    snapshot["market_structure"] = build_market_structure(snapshot)
    snapshot["trade_signals"] = build_trade_signals(snapshot)

    snapshot["paper_trading"] = build_paper_trading(snapshot)

    # ---------------------------------------------------
    # 🔴 NEW: CANONICAL TRADING STATE (ONLY ADDITION)
    # ---------------------------------------------------

    try:
        snapshot["trading_state"] = build_trading_state(snapshot, write_output=True)
        print("[TRADING STATE] built")
    except Exception as e:
        print("[TRADING STATE] error:", e)
        snapshot["trading_state"] = {}

    # ---------------------------------------------------

    persist_snapshot(snapshot)

    return snapshot
