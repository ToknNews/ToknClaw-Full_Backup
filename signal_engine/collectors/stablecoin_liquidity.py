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
# MODULE: stablecoin_liquidity
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
Stablecoin Liquidity Collector

Tracks stablecoin market liquidity using DefiLlama.

Signals feed:

• macro_liquidity_engine
• institutional_flow_engine
• liquidity_rotation_engine

Source:
https://defillama.com/docs/api
"""

from __future__ import annotations

import requests
from datetime import datetime
from typing import List

from models.signal import Signal


COLLECTOR_META = {
    "collector_id": "stablecoin_liquidity",
    "priority": 1,
    "timeout_sec": 10,
    "enabled": True,
    "tags": ["macro", "liquidity", "stablecoins"]
}


URL = "https://stablecoins.llama.fi/stablecoins"


def fetch_stablecoin_liquidity_signals() -> List[Signal]:

    signals: List[Signal] = []

    try:

        r = requests.get(URL, timeout=10)

        if r.status_code != 200:
            return signals

        data = r.json()

        for coin in data.get("peggedAssets", [])[:10]:

            symbol = coin.get("symbol")

            supply = coin.get("circulating", {}).get("peggedUSD")

            if not supply:
                continue

            signals.append(

                Signal(
                    timestamp=datetime.utcnow(),
                    source="defillama",
                    signal_type="stablecoin_supply",
                    entity=symbol,
                    title=f"{symbol} circulating supply",
                    summary=f"{symbol} stablecoin supply approximately ${supply:,.0f}",
                    confidence=0.9,
                    sentiment_score=None,
                    raw_url="https://defillama.com/stablecoins"
                )

            )

    except Exception:
        pass

    return signals
