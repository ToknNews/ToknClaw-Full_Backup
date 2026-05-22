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
# MODULE: watchlists
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Any, Dict, List


DEFAULT_WATCHLISTS = {
    "eth_stress": ["ETH", "WETH"],
    "memecoin_rotation": ["DOGE", "PEPE", "PENGU", "BONK", "WIF"],
    "ai_tokens": ["TAO", "FET", "RNDR"],
    "base_ecosystem": ["ETH", "OP"],
}


def build_watchlists(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    hits: Dict[str, Any] = {}

    for name, symbols in DEFAULT_WATCHLISTS.items():
        matched = []
        for s in signals:
            entity = str(s.get("entity") or "").upper()
            if entity in symbols:
                matched.append({
                    "entity": entity,
                    "signal_type": s.get("signal_type"),
                    "title": s.get("title"),
                })
        hits[name] = {
            "count": len(matched),
            "matches": matched[:5],
        }

    return hits
