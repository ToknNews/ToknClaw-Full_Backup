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
# MODULE: coingecko_markets
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
CoinGecko Market Collector

Purpose
-------

Collects market data signals from CoinGecko.

Signals include:

• price movement
• market cap
• trading volume
• top crypto assets

These signals feed:

• quant_factor_engine
• signal_velocity_engine
• liquidity_rotation_engine
• trade_signal_engine

API
---

https://api.coingecko.com/api/v3/coins/markets

Author: TOKN Systems
"""

from __future__ import annotations

import requests
from datetime import datetime
from typing import List

from models.signal import Signal


# ---------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"

REQUEST_TIMEOUT = 10

TOP_MARKET_LIMIT = 30


# ---------------------------------------------------
# COLLECTOR META
# ---------------------------------------------------

COLLECTOR_META = {
    "collector_id": "coingecko_markets",
    "priority": 1,
    "timeout_sec": 10,
    "enabled": True,
    "tags": ["market", "price", "volume"]
}


# ---------------------------------------------------
# COLLECTOR ENTRYPOINT
# ---------------------------------------------------

def fetch_coingecko_market_signals() -> List[Signal]:

    signals: List[Signal] = []

    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": TOP_MARKET_LIMIT,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "24h"
    }

    try:

        r = requests.get(COINGECKO_URL, params=params, timeout=REQUEST_TIMEOUT)

        if r.status_code != 200:
            return signals

        data = r.json()

        for asset in data:

            symbol = asset.get("symbol", "").upper()

            price = asset.get("current_price")

            market_cap = asset.get("market_cap")

            volume = asset.get("total_volume")

            change_24h = asset.get("price_change_percentage_24h")

            signals.append(

                Signal(
                    timestamp=datetime.utcnow(),
                    source="coingecko",
                    signal_type="market_data",
                    entity=symbol,
                    title=f"{symbol} market update",
                    summary=f"Price ${price}, market cap ${market_cap}, 24h volume ${volume}, change {change_24h}%",
                    confidence=0.85,
                    sentiment_score=None,
                    raw_url=f"https://www.coingecko.com/en/coins/{asset.get('id')}"
                )

            )

    except Exception:

        pass

    return signals
