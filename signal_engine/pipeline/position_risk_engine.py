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
# MODULE: position_risk_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Dict, List, Any


def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def build_position_risk(snapshot: Dict[str, Any]):

    signals = _safe_list(snapshot.get("trade_signals"))
    volatility = _safe_dict(snapshot.get("volatility"))
    regime = _safe_dict(snapshot.get("narrative_regime"))

    vol_factor = _safe_float(volatility.get("factors", {}).get("velocity_volatility"), 0.5)

    rows = []

    for s in signals:

        asset = s.get("asset")
        direction = s.get("direction")

        base_risk = 0.02

        if vol_factor > 0.7:
            base_risk *= 0.6
        elif vol_factor < 0.3:
            base_risk *= 1.3

        if direction == "long":
            stop = s.get("entry_price", 0) * (1 - base_risk)
        else:
            stop = s.get("entry_price", 0) * (1 + base_risk)

        rows.append({
            "asset": asset,
            "direction": direction,
            "position_risk_pct": round(base_risk, 4),
            "stop_price": stop
        })

    summary = {
        "positions": len(rows),
        "volatility_factor": vol_factor
    }

    return {
        "rows": rows,
        "summary": summary,
        "alerts": [],
        "endpoints": {
            "position_risk": "/api/toknclaw/risk/positions"
        }
    }
