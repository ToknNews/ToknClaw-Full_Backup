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
# MODULE: strategy_allocation_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from typing import Dict, Any, List


def _safe_list(v):
    return v if isinstance(v, list) else []


def build_strategy_allocation(snapshot: Dict[str, Any]):

    strategies = _safe_list(snapshot.get("strategy_simulations"))

    rows = []

    for s in strategies:

        name = s.get("strategy")

        rows.append({
            "strategy": name,
            "allocation_weight": 0.2
        })

    summary = {
        "strategy_count": len(rows)
    }

    return {
        "rows": rows,
        "summary": summary,
        "alerts": [],
        "endpoints": {
            "strategy_allocation": "/api/toknclaw/strategy-allocation"
        }
    }
