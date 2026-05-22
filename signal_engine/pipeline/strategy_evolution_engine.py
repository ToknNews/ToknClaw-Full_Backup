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
# MODULE: strategy_evolution_engine
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
Strategy Evolution Engine

Purpose
-------
Automatically evolves trading strategies based on:

• strategy performance
• simulation results
• backtest metrics
• market regime
• quant factor environment

Outputs
-------
snapshot["strategy_evolution"]
snapshot["strategy_evolution_summary"]
snapshot["strategy_evolution_mutations"]
snapshot["strategy_evolution_retirements"]
snapshot["strategy_evolution_endpoints"]

Future Capabilities
-------------------
• self-mutating strategies
• evolutionary parameter search
• reinforcement strategy scoring
• agent-driven strategy discovery

Author: TOKN Systems
"""

from __future__ import annotations

import random
from typing import Dict, List, Any


# ---------------------------------------------------
# Helpers
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


def _safe_str(v):
    if v is None:
        return ""
    return str(v)


# ---------------------------------------------------
# Performance Ranking
# ---------------------------------------------------

def _rank_strategies(snapshot):

    performance = _safe_list(snapshot.get("strategy_performance"))

    ranked = sorted(
        performance,
        key=lambda x: (
            _safe_float(x.get("sharpe")),
            _safe_float(x.get("return")),
            _safe_float(x.get("win_rate"))
        ),
        reverse=True
    )

    return ranked


# ---------------------------------------------------
# Mutation Generator
# ---------------------------------------------------

def _mutate_strategy(strategy):

    new = dict(strategy)

    mutation_type = random.choice([
        "confidence_adjustment",
        "factor_weight_shift",
        "signal_filter",
        "regime_specialization"
    ])

    if mutation_type == "confidence_adjustment":

        new["min_trade_confidence"] = round(
            _safe_float(strategy.get("min_trade_confidence", 0.55)) + random.uniform(-0.05, 0.05),
            2
        )

    if mutation_type == "factor_weight_shift":

        new["factor_weight_shift"] = round(random.uniform(-0.2, 0.2), 2)

    if mutation_type == "signal_filter":

        new["signal_filter"] = random.choice([
            "high_liquidity_only",
            "institutional_flow_only",
            "high_velocity_assets"
        ])

    if mutation_type == "regime_specialization":

        new["regime_focus"] = random.choice([
            "risk_on_liquidity",
            "institutional_rotation",
            "defi_expansion_cycle"
        ])

    new["mutation_origin"] = strategy.get("strategy_id")

    return new


# ---------------------------------------------------
# Evolution Engine
# ---------------------------------------------------

def build_strategy_evolution(snapshot: Dict[str, Any]):

    ranked = _rank_strategies(snapshot)

    top = ranked[:3]
    worst = ranked[-3:]

    mutations = []
    retirements = []

    # mutate top strategies
    for s in top:

        mutated = _mutate_strategy(s)

        mutations.append({
            "parent_strategy": s.get("strategy_id"),
            "mutation": mutated
        })

    # retire worst strategies
    for s in worst:

        sharpe = _safe_float(s.get("sharpe"))

        if sharpe < 0:

            retirements.append({
                "strategy_id": s.get("strategy_id"),
                "reason": "negative_sharpe"
            })

    summary = {

        "mutation_count": len(mutations),

        "retirement_count": len(retirements),

        "top_parent_strategies": [
            s.get("strategy_id")
            for s in top
        ],

        "evolution_cycle": "active"
    }

    return {

        "strategy_evolution": {

            "mutations": mutations,

            "retirements": retirements

        },

        "strategy_evolution_mutations": mutations,

        "strategy_evolution_retirements": retirements,

        "strategy_evolution_summary": summary,

        "strategy_evolution_endpoints": {

            "evolution": "/api/toknclaw/strategy-evolution",

            "mutations": "/api/toknclaw/strategy-evolution/mutations",

            "retirements": "/api/toknclaw/strategy-evolution/retirements",

            "summary": "/api/toknclaw/strategy-evolution/summary"
        }
    }
