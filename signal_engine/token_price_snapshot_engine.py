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
# MODULE: token_price_snapshot_engine
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
Token Price Snapshot Engine

Purpose
-------
Capture token prices over time for:

• outcome labeling
• strategy evaluation
• backtesting
• OpenClaw adaptive learning

Capabilities
------------
• extracts active tokens from latest snapshot
• fetches real-time price data from DexScreener (no RPC usage)
• stores rolling time-series per token
• maintains bounded history (memory safe)
• atomic writes (no corruption risk)
• resilient to API failures
• OpenClaw agent compatible (config driven)

Primary Input
-------------
/opt/toknclaw/data/snapshots/latest_snapshot.json

Primary Output
--------------
/opt/toknclaw/data/token_price_history.json

Author: TOKN Systems
"""

from __future__ import annotations

import json
import time
import requests
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, Any, List


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

DATA_PATH = Path("/opt/toknclaw/data/token_price_history.json")
TMP_PATH = Path("/opt/toknclaw/data/token_price_history.tmp")
SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot.json")


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

DEX_API = "https://api.dexscreener.com/latest/dex/tokens/"
MAX_TOKENS_PER_RUN = 50
MAX_HISTORY_PER_TOKEN = 100
REQUEST_TIMEOUT = 10


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json_atomic(data: Dict[str, Any]) -> None:
    with open(TMP_PATH, "w") as f:
        json.dump(data, f, indent=2)
    TMP_PATH.replace(DATA_PATH)


def extract_tokens(snapshot: Dict[str, Any]) -> List[str]:
    tokens = set()

    for s in snapshot.get("signals", []):
        if not isinstance(s, dict):
            continue

        entity = str(s.get("entity") or "").strip()

        if (
            len(entity) >= 20
            and "SOLANA_" not in entity
            and "ACTIVITY" not in entity
            and "SUMMARY" not in entity
        ):
            tokens.add(entity)

    return list(tokens)[:MAX_TOKENS_PER_RUN]


def fetch_price(token: str) -> Dict[str, float] | None:
    try:
        url = DEX_API + token
        r = requests.get(url, timeout=REQUEST_TIMEOUT)

        if r.status_code != 200:
            return None

        data = r.json()
        pairs = data.get("pairs", [])

        if not pairs:
            return None

        best = pairs[0]

        return {
            "price_usd": float(best.get("priceUsd") or 0),
            "liquidity_usd": float(best.get("liquidity", {}).get("usd") or 0),
            "volume_24h": float(best.get("volume", {}).get("h24") or 0),
        }

    except Exception:
        return None


# ---------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------

def run_price_snapshot() -> None:

    snapshot = load_json(SNAPSHOT_PATH, {})
    store = load_json(DATA_PATH, {
        "tokens": {},
        "updated_at": now_iso(),
        "schema_version": 1,
    })

    tokens = extract_tokens(snapshot)

    print(f"[PRICE SNAPSHOT] tokens_selected={len(tokens)}")

    updated_count = 0

    for token in tokens:

        price_data = fetch_price(token)

        if not price_data:
            continue

        token_history = store["tokens"].setdefault(token, [])

        token_history.append({
            "timestamp": now_iso(),
            "price_usd": price_data["price_usd"],
            "liquidity_usd": price_data["liquidity_usd"],
            "volume_24h": price_data["volume_24h"],
        })

        if len(token_history) > MAX_HISTORY_PER_TOKEN:
            store["tokens"][token] = token_history[-MAX_HISTORY_PER_TOKEN:]

        updated_count += 1

    store["updated_at"] = now_iso()

    save_json_atomic(store)

    print(
        f"[PRICE SNAPSHOT] updated_tokens={updated_count} "
        f"tracked_total={len(store['tokens'])}"
    )


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main():
    try:
        run_price_snapshot()
    except Exception as e:
        print("[PRICE SNAPSHOT] failed:", e)
        raise


if __name__ == "__main__":
    main()
