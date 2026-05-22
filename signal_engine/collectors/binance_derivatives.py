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
# MODULE: binance_derivatives
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
Binance Derivatives Collector

Collects derivatives market signals:

• funding rates
• open interest

Feeds:

• market_stress_engine
• volatility_engine
• trade_signal_engine

Source:
https://binance-docs.github.io/apidocs/futures/en/
"""

from __future__ import annotations

import requests
from datetime import datetime
from typing import List

from models.signal import Signal


COLLECTOR_META = {
    "collector_id": "binance_derivatives",
    "priority": 1,
    "timeout_sec": 10,
    "enabled": True,
    "tags": ["derivatives", "funding"]
}


FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def fetch_binance_derivatives_signals() -> List[Signal]:

    signals: List[Signal] = []

    try:

        r = requests.get(FUNDING_URL, timeout=10)

        if r.status_code != 200:
            return signals

        data = r.json()

        for item in data:

            symbol = item.get("symbol")

            if symbol not in SYMBOLS:
                continue

            funding = float(item.get("lastFundingRate", 0))

            signals.append(

                Signal(
                    timestamp=datetime.utcnow(),
                    source="binance",
                    signal_type="funding_rate",
                    entity=symbol.replace("USDT", ""),
                    title=f"{symbol} funding rate",
                    summary=f"Funding rate currently {funding}",
                    confidence=0.85,
                    sentiment_score=None,
                    raw_url="https://binance.com"
                )

            )

    except Exception:
        pass

    return signals
