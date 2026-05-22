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
# MODULE: solana_first_liquidity
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
Solana First Liquidity Detector

Purpose
-------
Detect new liquidity pools appearing on Solana.

Feeds
-----
• memecoin trading system
• liquidity rotation engine
• broadcast narrative signals
• DeFi analytics

Detection
---------
• Raydium program activity
• new pool transactions

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

RAYDIUM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"


def debug(msg):
    if DEBUG:
        print("[SOLANA LP]", msg)


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
    name="solana_first_liquidity",
    priority=1,
    tags=["solana", "liquidity", "memecoin"],
    category="onchain",
)
def fetch_solana_first_liquidity_signals() -> List[Signal]:

    signals: List[Signal] = []

    data = rpc(
        "getSignaturesForAddress",
        [
            RAYDIUM_PROGRAM,
            {"limit": 50},
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
                signal_type="solana_liquidity_event",
                entity="SOLANA",
                title="Potential new liquidity pool",
                summary=f"Liquidity activity detected {sig[:10]}",
                confidence=0.65,
                sentiment_score=0.3,
                raw_url=f"https://solscan.io/tx/{sig}",
            )
        )

    return signals
