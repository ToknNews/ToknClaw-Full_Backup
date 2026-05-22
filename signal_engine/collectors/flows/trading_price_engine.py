#!/usr/bin/env python3
"""
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
# MODULE: trading_price_engine
# PURPOSE: Maintain a clean, high-quality price history for trading assets
#          (majors + midcaps) using centralized exchange perp markets.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This collector is designed to:
• fetch real-time perp prices for tradable assets
• normalize pricing across venues (OKX primary)
• maintain rolling price history for each asset
• overwrite stale or irrelevant memecoin data
• support trend, PnL, and execution logic
• remain additive and OpenClaw agent ready

Primary Inputs
--------------
OKX perp market API

Primary Output
--------------
/opt/toknclaw/data/token_price_history.json

Future Extensions
----------------
• multi-venue blending (Hyperliquid, Binance)
• VWAP smoothing
• volatility metrics
• spread tracking
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import json
import time
from datetime import datetime, timezone
from typing import Dict

import requests

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

OKX_URL = "https://www.okx.com/api/v5/market/tickers?instType=SWAP"

PRICE_PATH = Path("/opt/toknclaw/data/token_price_history.json")
PRICE_TMP = Path("/opt/toknclaw/data/token_price_history.tmp")

UNIVERSE = [
    "BTC","ETH","SOL","BNB","XRP",
    "DOGE","LINK","AVAX","ARB","OP",
    "INJ","PYTH","JUP","RNDR"
]

MAX_HISTORY = 200

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(x, d=0.0):
    try:
        return float(x)
    except:
        return d


# ---------------------------------------------------
# FETCH
# ---------------------------------------------------

def fetch_okx_prices() -> Dict[str, float]:

    try:
        r = requests.get(OKX_URL, timeout=10)
        data = r.json().get("data", [])
    except Exception as e:
        print("[TRADING PRICE] fetch error:", e)
        return {}

    out = {}

    for row in data:
        inst = row.get("instId", "")

        if "-USDT-SWAP" not in inst:
            continue

        symbol = inst.replace("-USDT-SWAP", "")

        if symbol not in UNIVERSE:
            continue

        price = safe_float(row.get("last"), 0.0)

        if price <= 0:
            continue

        out[symbol] = price

    return out


# ---------------------------------------------------
# STORAGE
# ---------------------------------------------------

def load_history():
    if not PRICE_PATH.exists():
        return {"tokens": {}}

    try:
        with open(PRICE_PATH) as f:
            return json.load(f)
    except:
        return {"tokens": {}}


def save_history(data):

    PRICE_TMP.parent.mkdir(parents=True, exist_ok=True)

    with open(PRICE_TMP, "w") as f:
        json.dump(data, f, indent=2)

    PRICE_TMP.replace(PRICE_PATH)


# ---------------------------------------------------
# MAIN UPDATE
# ---------------------------------------------------

def update_trading_prices():

    start = time.time()

    prices = fetch_okx_prices()

    history = load_history()
    tokens = history.setdefault("tokens", {})

    ts = now_iso()

    updated = 0

    for symbol, price in prices.items():

        series = tokens.setdefault(symbol, [])

        series.append({
            "timestamp": ts,
            "price_usd": price
        })

        if len(series) > MAX_HISTORY:
            tokens[symbol] = series[-MAX_HISTORY:]

        updated += 1

    save_history(history)

    runtime = round(time.time() - start, 2)

    print(f"[TRADING PRICE] updated={updated} runtime={runtime}s")


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    update_trading_prices()
