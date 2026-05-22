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
# MODULE: liquidity_map_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
ToknClaw Liquidity Map Engine
Institutional-grade liquidity intelligence layer.

Purpose
-------
Build a real-time map of capital flows across the crypto ecosystem.

Tracks:
• exchange inflows / outflows
• stablecoin supply changes
• whale transfer flows
• DeFi capital formation
• derivatives liquidity shifts
• cross-chain liquidity migration

Outputs
-------
snapshot["liquidity_map"]
snapshot["liquidity_flows"]
snapshot["liquidity_summary"]
snapshot["liquidity_alerts"]
snapshot["liquidity_endpoints"]
"""

from __future__ import annotations
from typing import Dict, List, Any
from collections import defaultdict
import math


# ---------------------------------------------------------
# Utilities
# ---------------------------------------------------------

def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def _normalize(value):
    if value == 0:
        return 0
    return math.log10(abs(value) + 1)


# ---------------------------------------------------------
# Flow Extraction
# ---------------------------------------------------------

def _extract_exchange_flows(snapshot):

    metrics = _safe_dict(snapshot.get("metrics"))

    inflow = _safe_float(metrics.get("exchange_inflows_usd"))
    outflow = _safe_float(metrics.get("exchange_outflows_usd"))

    net = inflow - outflow

    return {
        "inflows": inflow,
        "outflows": outflow,
        "net_flow": net
    }


def _extract_whale_flows(snapshot):

    clusters = _safe_list(snapshot.get("clusters"))

    whale_total = 0

    for c in clusters:

        if c.get("cluster_type") != "whale_activity":
            continue

        whale_total += _safe_float(c.get("total_value_usd"))

    return whale_total


def _extract_defi_flows(snapshot):

    clusters = _safe_list(snapshot.get("clusters"))

    defi_total = 0

    for c in clusters:

        if c.get("cluster_type") not in {"protocol_tvl", "protocol_tvl_growth"}:
            continue

        defi_total += _safe_float(c.get("total_value_usd"))

    return defi_total


def _extract_stablecoin_flows(snapshot):

    clusters = _safe_list(snapshot.get("clusters"))

    stable_total = 0

    for c in clusters:

        entity = str(c.get("entity") or "").upper()

        if entity in {"USDT", "USDC", "DAI", "FDUSD"}:
            stable_total += _safe_float(c.get("total_value_usd"))

    return stable_total


# ---------------------------------------------------------
# Liquidity Concentration
# ---------------------------------------------------------

def _liquidity_concentration(snapshot):

    clusters = _safe_list(snapshot.get("clusters"))

    concentration = defaultdict(float)

    for c in clusters:

        entity = str(c.get("entity") or "UNKNOWN")
        value = _safe_float(c.get("total_value_usd"))

        concentration[entity] += value

    rows = []

    for entity, value in concentration.items():

        rows.append({
            "entity": entity,
            "liquidity_value": value,
            "normalized_score": round(_normalize(value), 3)
        })

    rows.sort(
        key=lambda x: x["liquidity_value"],
        reverse=True
    )

    return rows[:25]


# ---------------------------------------------------------
# Cross-Chain Liquidity
# ---------------------------------------------------------

def _cross_chain_liquidity(snapshot):

    clusters = _safe_list(snapshot.get("clusters"))

    chains = defaultdict(float)

    for c in clusters:

        entity = str(c.get("entity") or "")
        value = _safe_float(c.get("total_value_usd"))

        if entity in {"ETH", "WETH"}:
            chains["ethereum"] += value

        elif entity in {"SOL"}:
            chains["solana"] += value

        elif entity in {"BTC", "WBTC"}:
            chains["bitcoin"] += value

    rows = []

    for chain, value in chains.items():

        rows.append({
            "chain": chain,
            "liquidity_value": value,
            "normalized_score": round(_normalize(value), 3)
        })

    rows.sort(key=lambda x: x["liquidity_value"], reverse=True)

    return rows


# ---------------------------------------------------------
# Liquidity Alerts
# ---------------------------------------------------------

def _detect_liquidity_alerts(exchange, whales, defi):

    alerts = []

    if whales > 500_000_000:

        alerts.append({
            "type": "whale_liquidity_event",
            "severity": "high",
            "title": "Large whale liquidity movement detected"
        })

    if exchange["net_flow"] > 200_000_000:

        alerts.append({
            "type": "exchange_inflow_pressure",
            "severity": "medium",
            "title": "Heavy exchange inflows detected"
        })

    if defi > 1_000_000_000:

        alerts.append({
            "type": "defi_liquidity_growth",
            "severity": "medium",
            "title": "Strong capital formation in DeFi"
        })

    return alerts


# ---------------------------------------------------------
# Main Engine
# ---------------------------------------------------------

def build_liquidity_map(snapshot: Dict[str, Any]):

    snapshot = _safe_dict(snapshot)

    exchange = _extract_exchange_flows(snapshot)

    whales = _extract_whale_flows(snapshot)

    defi = _extract_defi_flows(snapshot)

    stable = _extract_stablecoin_flows(snapshot)

    concentration = _liquidity_concentration(snapshot)

    chains = _cross_chain_liquidity(snapshot)

    alerts = _detect_liquidity_alerts(exchange, whales, defi)

    flows = {
        "exchange": exchange,
        "whale_flows_usd": whales,
        "defi_flows_usd": defi,
        "stablecoin_flows_usd": stable
    }

    summary = {
        "dominant_liquidity_source": max(
            ["exchange", "whale", "defi", "stable"],
            key=lambda x: flows.get(f"{x}_flows_usd", 0)
        ),
        "total_whale_flow": whales,
        "total_defi_flow": defi,
        "exchange_net_flow": exchange["net_flow"],
        "alert_count": len(alerts)
    }

    return {

        "map": {
            "concentration": concentration,
            "cross_chain": chains
        },

        "flows": flows,

        "summary": summary,

        "alerts": alerts,

        "endpoints": {
            "liquidity_map": "/api/toknclaw/liquidity-map",
            "liquidity_flows": "/api/toknclaw/liquidity-flows"
        }
    }
