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
# MODULE: solana_token_metadata
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
Solana Token Metadata Collector

Purpose
-------
Enrich Solana token mints with metadata.

Feeds
-----
• memecoin trading bot
• narrative intelligence engine
• broadcast segments
• newsletter analytics
• entity intelligence graph

Data Sources
------------
• Solana RPC
• Token supply queries

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


def debug(msg):
    if DEBUG:
        print("[SOLANA META]", msg)


def get_token_supply(mint: str):

    try:

        r = requests.post(
            SOL_RPC,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenSupply",
                "params": [mint],
            },
            timeout=10,
        )

        data = r.json()

        return data.get("result", {}).get("value")

    except Exception as e:
        debug(f"supply error {mint}: {e}")
        return None


@register_collector(
    name="solana_token_metadata",
    priority=3,
    tags=["solana", "metadata", "broadcast"],
    category="onchain",
)
def fetch_solana_token_metadata_signals() -> List[Signal]:

    signals: List[Signal] = []

    # placeholder for tracked mints from entity graph later
    tracked = os.getenv("TOKN_SOL_TRACKED_MINTS", "")

    if not tracked:
        debug("no tracked mints configured")
        return signals

    mints = [x.strip() for x in tracked.split(",") if x.strip()]

    for mint in mints:

        supply = get_token_supply(mint)

        if not supply:
            continue

        amount = supply.get("uiAmount")

        debug(f"{mint} supply={amount}")

        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_token_metadata",
                entity=mint,
                title="Solana token metadata update",
                summary=f"Token {mint} supply: {amount}",
                confidence=0.70,
                sentiment_score=None,
                raw_url=f"https://solscan.io/token/{mint}",
            )
        )

    return signals
