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
# MODULE: solana_price_enricher
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
Solana Price Enricher

Purpose
-------
Continuously fetches token prices for tracked entities
and stores time-series data for outcome + strategy evaluation.

Inputs
------
/opt/toknclaw/data/signal_outcomes.json

Output
------
/opt/toknclaw/data/token_price_history.json

Author: TOKN Systems
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import requests


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

OUTCOMES_PATH = Path("/opt/toknclaw/data/signal_outcomes.json")
PRICE_HISTORY_PATH = Path("/opt/toknclaw/data/token_price_history.json")
TMP_PATH = Path("/opt/toknclaw/data/token_price_history.tmp")


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

MAX_TOKENS_PER_RUN = 50
REQUEST_TIMEOUT = 10


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def write_atomic(path: Path, tmp: Path, payload: Dict[str, Any]):
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def get_price(token: str) -> Dict[str, float]:
    """
    Uses Dexscreener (fast + free)
    """
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
        r = requests.get(url, timeout=REQUEST_TIMEOUT)

        if r.status_code != 200:
            return {}

        data = r.json()
        pairs = data.get("pairs", [])

        if not pairs:
            return {}

        pair = pairs[0]

        return {
            "price_usd": float(pair.get("priceUsd", 0) or 0),
            "liquidity_usd": float(pair.get("liquidity", {}).get("usd", 0) or 0),
            "volume_24h": float(pair.get("volume", {}).get("h24", 0) or 0),
        }

    except Exception:
        return {}


# ---------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------

def run_price_enricher():

    outcomes = read_json(OUTCOMES_PATH, {})
    records = outcomes.get("records", {})

    if not isinstance(records, dict):
        print("[PRICE ENRICHER] no records")
        return

    history = read_json(PRICE_HISTORY_PATH, {"tokens": {}})
    tokens = history.setdefault("tokens", {})

    # collect unique tokens
    candidates = []

    for r in records.values():
        entity = str(r.get("entity", ""))
        if len(entity) > 20:
            candidates.append(entity)

    candidates = list(set(candidates))[:MAX_TOKENS_PER_RUN]

    print(f"[PRICE ENRICHER] tokens={len(candidates)}")

    for token in candidates:

        data = get_price(token)

        if not data:
            continue

        entry = {
            "timestamp": now_iso(),
            "price_usd": data["price_usd"],
            "liquidity_usd": data["liquidity_usd"],
            "volume_24h": data["volume_24h"],
        }

        token_series = tokens.setdefault(token, [])
        token_series.append(entry)

        # keep last 500 points
        if len(token_series) > 500:
            tokens[token] = token_series[-500:]

    history["updated_at"] = now_iso()

    write_atomic(PRICE_HISTORY_PATH, TMP_PATH, history)

    print(f"[PRICE ENRICHER] updated_tokens={len(candidates)}")


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    run_price_enricher()
