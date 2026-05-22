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
# MODULE: strategy_optimizer_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Dict, List


def optimize_strategies(snapshot, candidates):

    optimized = []

    regime = snapshot.get("market_regime", {}).get("name")

    for c in candidates:

        base = c["score"]

        if regime == "defi_expansion_cycle" and c["sector"] == "defi":
            base += 0.2

        if regime == "retail_speculation_cycle" and c["sector"] == "retail":
            base += 0.2

        if regime == "stressed_unwind" and c["direction"] == "short":
            base += 0.2

        optimized.append({
            **c,
            "optimized_score": round(min(base, 1.0), 3)
        })

    optimized.sort(key=lambda x: x["optimized_score"], reverse=True)

    return {
        "strategies": optimized,
        "ranking": [s["strategy_id"] for s in optimized]
    }
