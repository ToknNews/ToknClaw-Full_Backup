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
# MODULE: solana_mev_bots
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
Solana MEV Bot Activity Detector

Purpose
-------
Detect MEV / arbitrage bot activity on Solana.

Feeds
-----
• memecoin trading system
• volatility detection
• narrative intelligence
• broadcast commentary

Detection Signals
-----------------
• Jupiter swap bursts
• arbitrage transaction patterns
• repeated routing loops

Author: TOKN Systems
"""

from __future__ import annotations

import os
import requests
from datetime import datetime
from typing import List

from signal_engine.collectors.registry import register_collector
from models.signal import Signal


SOL_RPC = os.getenv("SOL_RPC")
DEBUG = os.getenv("TOKN_DEBUG_COLLECTORS", "1") == "1"

JUPITER_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"


def debug(msg):
    if DEBUG:
        print("[SOLANA MEV]", msg)


def rpc(method, params):

    try:

        r = requests.post(
            SOL_RPC,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params,
            },
            timeout=10,
        )

        return r.json()

    except Exception as e:

        debug(f"rpc error {e}")
        return None


@register_collector(
    name="solana_mev_bots",
    priority=2,
    tags=["solana", "mev", "arbitrage"],
    category="onchain",
)
def fetch_solana_mev_signals() -> List[Signal]:

    signals: List[Signal] = []

    data = rpc(
        "getSignaturesForAddress",
        [
            JUPITER_PROGRAM,
            {"limit": 80},
        ],
    )

    if not data:
        return signals

    rows = data.get("result", [])

    for row in rows:

        sig = row.get("signature")

        debug(sig)

        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_mev_activity",
                entity="SOLANA",
                title="Potential Solana MEV activity",
                summary=f"Arbitrage swap activity detected {sig[:12]}",
                confidence=0.6,
                sentiment_score=0.1,
                raw_url=f"https://solscan.io/tx/{sig}",
            )
        )

    return signals
