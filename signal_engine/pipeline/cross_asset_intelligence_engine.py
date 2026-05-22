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
# MODULE: cross_asset_intelligence_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
cross_asset_intelligence_engine.py

ToknClaw Cross Asset Intelligence Engine

Purpose
-------
Detect macro relationships across assets including:

• crypto flows
• stablecoin liquidity
• risk assets
• macro stress
• news catalysts
• institutional flows

Outputs intelligence usable by:

• broadcast narrative
• dashboard analytics
• alert system
• regime detection
• quant analysis
"""

from __future__ import annotations
from typing import Dict, List, Any


# ---------------------------------------------------
# helpers
# ---------------------------------------------------

def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


# ---------------------------------------------------
# liquidity signal detection
# ---------------------------------------------------

def _detect_liquidity_regime(snapshot):

    metrics = _safe_dict(snapshot.get("metrics"))

    whale = _safe_float(metrics.get("whale_activity_usd"))
    inflow = _safe_float(metrics.get("exchange_inflows_usd"))
    outflow = _safe_float(metrics.get("exchange_outflows_usd"))

    if whale > 500_000_000 and inflow == 0:
        return "capital_rotation"

    if inflow > 250_000_000:
        return "exchange_inflow_pressure"

    if outflow > 250_000_000:
        return "exchange_outflow_accumulation"

    return "balanced"


# ---------------------------------------------------
# stablecoin liquidity
# ---------------------------------------------------

def _detect_stablecoin_flows(snapshot):

    clusters = _safe_list(snapshot.get("clusters"))

    stablecoins = {"USDT", "USDC", "DAI"}

    flow = 0

    for c in clusters:

        entity = str(c.get("entity") or "")

        if entity in stablecoins:
            flow += _safe_float(c.get("total_value_usd"))

    if flow > 1_000_000_000:
        return "large_stablecoin_movement"

    if flow > 250_000_000:
        return "moderate_stablecoin_flow"

    return "stable"


# ---------------------------------------------------
# macro narrative alignment
# ---------------------------------------------------

def _detect_macro_alignment(snapshot):

    correlations = _safe_list(snapshot.get("narrative_correlations"))

    for c in correlations:

        ctype = str(c.get("correlation_type") or "")

        if ctype == "institutional_accumulation":
            return "institutional_risk_on"

        if ctype == "market_stress_repricing":
            return "risk_off_repricing"

    return "mixed"


# ---------------------------------------------------
# cross asset signals
# ---------------------------------------------------

def _build_cross_asset_signals(snapshot):

    clusters = _safe_list(snapshot.get("clusters"))

    signals = []

    for c in clusters:

        entity = c.get("entity")
        ctype = c.get("cluster_type")
        value = _safe_float(c.get("total_value_usd"))

        if ctype == "whale_activity" and value > 100_000_000:

            signals.append({
                "type": "large_whale_transfer",
                "entity": entity,
                "value_usd": value
            })

        if ctype == "protocol_tvl" and value > 5_000_000_000:

            signals.append({
                "type": "major_protocol_liquidity",
                "entity": entity,
                "value_usd": value
            })

    return signals


# ---------------------------------------------------
# intelligence engine
# ---------------------------------------------------

def build_cross_asset_intelligence(snapshot: Dict[str, Any]) -> Dict[str, Any]:

    snapshot = _safe_dict(snapshot)

    liquidity_regime = _detect_liquidity_regime(snapshot)

    stablecoin_flow = _detect_stablecoin_flows(snapshot)

    macro_alignment = _detect_macro_alignment(snapshot)

    cross_signals = _build_cross_asset_signals(snapshot)

    intelligence = {
        "liquidity_regime": liquidity_regime,
        "stablecoin_flow": stablecoin_flow,
        "macro_alignment": macro_alignment,
        "cross_asset_signals": cross_signals,
        "signal_count": len(cross_signals)
    }

    return intelligence
