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
# MODULE: fred_rates
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
FRED Macro Economic Collector

Purpose
-------

Collect macroeconomic signals from the Federal Reserve Economic Data (FRED) API.

This collector feeds macro signals into the ToknClaw intelligence engine.

Signals power:

• macro_liquidity_engine
• market_regime_engine
• cross_asset_intelligence_engine
• market_stress_engine

Collected Data Categories
-------------------------

Treasury yields
Inflation indicators
Dollar strength
Liquidity conditions
Economic activity
Market volatility

Design Goals
------------

• stable API ingestion
• resilient to missing data
• minimal noise signals
• compatible with Signal model
• low API usage footprint

Author: TOKN Systems
"""

from __future__ import annotations

import os
import requests
from datetime import datetime
from typing import List, Optional

from models.signal import Signal


# ---------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------

FRED_API_KEY = os.getenv("FRED_API_KEY")

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

REQUEST_TIMEOUT = 10


# ---------------------------------------------------
# MACRO SERIES REGISTRY
# ---------------------------------------------------

SERIES = {

    # ---------------------------------------------------
    # MARKET INDICATORS
    # ---------------------------------------------------

    "SP500": "S&P500 Index",
    "VIXCLS": "VIX Volatility Index",

    # ---------------------------------------------------
    # TREASURY YIELDS
    # ---------------------------------------------------

    "DGS2": "US 2Y Treasury Yield",
    "DGS5": "US 5Y Treasury Yield",
    "DGS10": "US 10Y Treasury Yield",
    "DGS30": "US 30Y Treasury Yield",

    # ---------------------------------------------------
    # POLICY RATES
    # ---------------------------------------------------

    "FEDFUNDS": "Federal Funds Rate",
    "SOFR": "Secured Overnight Financing Rate",

    # ---------------------------------------------------
    # INFLATION
    # ---------------------------------------------------

    "CPIAUCSL": "US CPI Inflation",
    "CPILFESL": "Core CPI",
    "PCEPI": "PCE Inflation",
    "PCEPILFE": "Core PCE",

    # ---------------------------------------------------
    # LIQUIDITY
    # ---------------------------------------------------

    "WALCL": "Fed Balance Sheet",
    "M2SL": "Money Supply M2",

    # ---------------------------------------------------
    # ECONOMIC ACTIVITY
    # ---------------------------------------------------

    "UNRATE": "US Unemployment Rate",
    "PAYEMS": "Nonfarm Payrolls",
    "INDPRO": "Industrial Production",

    # ---------------------------------------------------
    # DOLLAR
    # ---------------------------------------------------

    "DTWEXBGS": "Dollar Index Broad"
}


# ---------------------------------------------------
# INTERNAL FETCH FUNCTION
# ---------------------------------------------------

def _fetch_series(series_id: str) -> Optional[float]:

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1
    }

    try:

        r = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)

        if r.status_code != 200:
            return None

        data = r.json()

        observations = data.get("observations")

        if not observations:
            return None

        value = observations[0].get("value")

        if value in (".", None):
            return None

        return float(value)

    except Exception:
        return None


# ---------------------------------------------------
# COLLECTOR ENTRYPOINT
# ---------------------------------------------------

def fetch_fred_rates_signals() -> List[Signal]:

    if not FRED_API_KEY:

        print("[FRED] missing API key")

        return []

    signals: List[Signal] = []

    now = datetime.utcnow()

    for series_id, name in SERIES.items():

        value = _fetch_series(series_id)

        if value is None:
            continue

        signals.append(

            Signal(
                timestamp=now,
                source="fred",
                signal_type="macro_indicator",
                entity=series_id,
                title=name,
                summary=f"{name} latest reading: {value}",
                confidence=0.92,
                sentiment_score=None,
                raw_url=f"https://fred.stlouisfed.org/series/{series_id}"
            )

        )

    return signals
