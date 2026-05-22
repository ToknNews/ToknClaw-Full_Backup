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
# MODULE: analysis
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Any, Dict, List


def build_risks(signals: List[Dict[str, Any]], retail_pulse: Dict[str, Any]) -> Dict[str, Any]:
    primary: List[str] = []
    contradictions: List[str] = []

    signal_types = {str(s.get("signal_type") or "") for s in signals}

    if "exchange_inflow" in signal_types:
        primary.append("Exchange inflows may signal sell pressure.")
    if "defi_liquidation" in signal_types:
        primary.append("Liquidations may amplify volatility.")
    if retail_pulse.get("memecoin_rotation"):
        primary.append("Retail speculation is increasing.")

    if retail_pulse.get("retail_sentiment") == "active" and "exchange_inflow" in signal_types:
        contradictions.append("Retail optimism and exchange inflows may be diverging.")

    return {
        "primary": primary,
        "contradictions": contradictions,
    }
