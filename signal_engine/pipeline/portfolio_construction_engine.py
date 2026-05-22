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
# MODULE: portfolio_construction_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from typing import Dict, Any, List


def _safe_list(v):
    return v if isinstance(v, list) else []


def build_portfolio(snapshot: Dict[str, Any]):

    signals = _safe_list(snapshot.get("trade_signals"))

    rows = []

    weight = 1 / max(len(signals), 1)

    for s in signals:

        rows.append({
            "asset": s.get("asset"),
            "direction": s.get("direction"),
            "portfolio_weight": round(weight, 4)
        })

    summary = {
        "assets": len(rows),
        "weight_per_asset": weight
    }

    return {
        "rows": rows,
        "summary": summary,
        "alerts": [],
        "endpoints": {
            "portfolio": "/api/toknclaw/portfolio"
        }
    }
