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
# MODULE: strategy_registry_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
strategy_registry_engine.py

Central strategy registry for ToknClaw.

Strategies are defined declaratively and loaded at runtime.
Agents and bots can extend this file without modifying the engine.
"""

from __future__ import annotations
from typing import Dict, List


def load_strategy_registry() -> List[Dict]:

    return [

        {
            "strategy_id": "defi_tvl_momentum",
            "name": "DeFi TVL Momentum",
            "sector": "defi",
            "drivers": ["protocol_tvl", "protocol_revenue"],
            "regimes": ["defi_expansion_cycle"],
            "direction": "long",
            "risk_level": "medium",
        },

        {
            "strategy_id": "institutional_accumulation_follow",
            "name": "Institutional Accumulation Follow",
            "sector": "onchain",
            "drivers": ["whale_activity"],
            "regimes": ["institutional_accumulation_phase"],
            "direction": "long",
            "risk_level": "medium",
        },

        {
            "strategy_id": "memecoin_speculation",
            "name": "Memecoin Speculation Cycle",
            "sector": "retail",
            "drivers": ["retail_narrative", "memecoin_rotation"],
            "regimes": ["retail_speculation_cycle"],
            "direction": "long",
            "risk_level": "high",
        },

        {
            "strategy_id": "derivatives_squeeze",
            "name": "Derivatives Short Squeeze",
            "sector": "derivatives",
            "drivers": ["short_squeeze_risk"],
            "regimes": ["short_squeeze_setup"],
            "direction": "long",
            "risk_level": "high",
        },

        {
            "strategy_id": "market_stress_short",
            "name": "Market Stress Short",
            "sector": "macro",
            "drivers": ["market_stress"],
            "regimes": ["stressed_unwind"],
            "direction": "short",
            "risk_level": "medium",
        },
    ]
