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
# MODULE: portfolio_optimization_engine
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

Portfolio Optimization Engine
-----------------------------

Purpose
-------
Construct optimal portfolio allocations from ToknClaw strategy outputs.

Features
--------
• Kelly position sizing
• risk budgeting
• regime-aware capital allocation
• factor weighting
• liquidity constraints
• diversification controls
• capital efficiency scoring
• strategy risk parity
• execution-ready portfolio blueprint

Outputs
-------
snapshot["portfolio_optimization"]
snapshot["portfolio_optimization_summary"]
snapshot["portfolio_optimization_alerts"]
snapshot["portfolio_optimization_endpoints"]

Author: TOKN Systems
"""

from __future__ import annotations
from typing import Dict, List, Any


# -----------------------------------------------------
# Helpers
# -----------------------------------------------------

def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# -----------------------------------------------------
# Kelly sizing
# -----------------------------------------------------

def _kelly_fraction(win_rate: float, payoff: float) -> float:
    """
    Kelly Criterion

    f* = (bp - q) / b
    """

    p = _clamp(win_rate)
    q = 1 - p
    b = max(payoff, 0.01)

    k = (b * p - q) / b

    return _clamp(k, 0.0, 0.5)  # half-kelly cap


# -----------------------------------------------------
# Factor weighting
# -----------------------------------------------------

def _factor_weight(row):

    confidence = _safe_float(row.get("confidence"))
    composite = _safe_float(row.get("composite_factor"))
    momentum = _safe_float(row.get("momentum_factor"))
    quality = _safe_float(row.get("quality_factor"))

    score = (
        confidence * 0.40 +
        composite * 0.30 +
        momentum * 0.20 +
        quality * 0.10
    )

    return _clamp(score)


# -----------------------------------------------------
# Liquidity constraint
# -----------------------------------------------------

def _liquidity_penalty(entity, snapshot):

    liquidity_map = _safe_dict(snapshot.get("liquidity_map"))
    flows = _safe_dict(snapshot.get("liquidity_flows"))

    liq = _safe_float(liquidity_map.get(entity))
    flow = _safe_float(flows.get(entity))

    penalty = 1.0

    if liq < 0.25:
        penalty *= 0.6

    if flow < 0:
        penalty *= 0.8

    return penalty


# -----------------------------------------------------
# Regime multiplier
# -----------------------------------------------------

def _regime_multiplier(snapshot):

    regime = _safe_dict(snapshot.get("market_regime")).get("name")

    mapping = {

        "defi_expansion_cycle": 1.25,
        "institutional_accumulation_phase": 1.15,
        "retail_speculation_cycle": 1.10,

        "mixed_transition": 0.90,
        "fragile_transition": 0.75,

        "liquidation_pressure": 0.60
    }

    return mapping.get(regime, 1.0)


# -----------------------------------------------------
# Strategy exposure
# -----------------------------------------------------

def _strategy_map(snapshot):

    out = {}

    for s in _safe_list(snapshot.get("optimized_strategies")):

        entity = s.get("entity")

        if entity:
            out[entity] = s

    return out


# -----------------------------------------------------
# Core optimizer
# -----------------------------------------------------

def _optimize_positions(snapshot):

    trades = _safe_list(snapshot.get("trade_signals"))
    quant = _safe_list(snapshot.get("quant_factors"))

    quant_map = {q.get("entity"): q for q in quant}

    regime_mult = _regime_multiplier(snapshot)

    strategy_map = _strategy_map(snapshot)

    rows = []

    for trade in trades:

        entity = trade.get("entity")
        direction = trade.get("direction")

        quant_row = _safe_dict(quant_map.get(entity))

        if not quant_row:
            continue

        win_rate = _safe_float(trade.get("confidence"))
        payoff = 1.5

        kelly = _kelly_fraction(win_rate, payoff)

        factor_score = _factor_weight({
            **trade,
            **quant_row
        })

        liquidity_pen = _liquidity_penalty(entity, snapshot)

        strategy_weight = _safe_float(
            _safe_dict(strategy_map.get(entity)).get("weight"),
            1.0
        )

        position_size = (
            kelly *
            factor_score *
            liquidity_pen *
            regime_mult *
            strategy_weight
        )

        position_size = _clamp(position_size, 0.0, 0.25)

        rows.append({

            "entity": entity,
            "direction": direction,
            "kelly_fraction": round(kelly, 3),
            "factor_score": round(factor_score, 3),
            "liquidity_penalty": round(liquidity_pen, 3),
            "strategy_weight": round(strategy_weight, 3),
            "regime_multiplier": regime_mult,

            "position_size": round(position_size, 4),

            "confidence": trade.get("confidence"),
            "signal_reasons": trade.get("signal_reasons", [])
        })

    rows.sort(
        key=lambda x: (
            x.get("position_size", 0),
            x.get("confidence", 0),
        ),
        reverse=True
    )

    return rows[:100]


# -----------------------------------------------------
# Alerts
# -----------------------------------------------------

def _alerts(rows):

    alerts = []

    for r in rows:

        size = _safe_float(r.get("position_size"))

        if size > 0.18:

            alerts.append({

                "type": "large_position",
                "severity": "medium",
                "entity": r.get("entity"),
                "title": f"Large allocation recommended for {r.get('entity')}"
            })

    return alerts[:20]


# -----------------------------------------------------
# Summary
# -----------------------------------------------------

def _summary(rows, alerts):

    if not rows:
        return {

            "position_count": 0,
            "top_position": None,
            "top_size": 0,
            "alert_count": len(alerts)
        }

    top = rows[0]

    return {

        "position_count": len(rows),

        "top_position": top.get("entity"),
        "top_size": top.get("position_size"),

        "alert_count": len(alerts)
    }


# -----------------------------------------------------
# Endpoints
# -----------------------------------------------------

def _endpoints():

    return {

        "portfolio_optimization": "/api/toknclaw/portfolio-optimization",
        "portfolio_optimization_summary": "/api/toknclaw/portfolio-optimization/summary",
        "portfolio_optimization_alerts": "/api/toknclaw/portfolio-optimization/alerts",
    }


# -----------------------------------------------------
# Public Engine
# -----------------------------------------------------

def build_portfolio_optimization(snapshot: Dict[str, Any]):

    snapshot = _safe_dict(snapshot)

    rows = _optimize_positions(snapshot)

    alerts = _alerts(rows)

    summary = _summary(rows, alerts)

    return {

        "portfolio_optimization": rows,
        "portfolio_optimization_summary": summary,
        "portfolio_optimization_alerts": alerts,
        "portfolio_optimization_endpoints": _endpoints()
    }
