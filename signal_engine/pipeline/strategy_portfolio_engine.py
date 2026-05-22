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
# MODULE: strategy_portfolio_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Dict, List


def allocate_strategy_portfolio(snapshot, strategies):

    if not strategies:
        return {"allocations": [], "summary": {}}

    total = sum(s["optimized_score"] for s in strategies)

    allocations = []

    for s in strategies:

        weight = s["optimized_score"] / total if total else 0

        allocations.append({
            "strategy_id": s["strategy_id"],
            "weight": round(weight, 3),
            "direction": s["direction"],
            "sector": s["sector"]
        })

    return {
        "allocations": allocations,
        "summary": {
            "strategy_count": len(allocations),
            "dominant_strategy": allocations[0]["strategy_id"] if allocations else None
        }
    }
