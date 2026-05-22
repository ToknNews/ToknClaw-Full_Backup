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
# MODULE: solana_whale_clusters
# PURPOSE: Detect repeated large wallet activity clusters across tracked
#          Solana mints.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

• whale-flow monitoring
• memecoin bot context
• narrative intelligence
• broadcast large-wallet segments
• alerts and newsletters

Notes
-----
Requires TOKN_SOL_TRACKED_MINTS in .env.

Author: TOKN Systems
"""

from __future__ import annotations

import os
import time
from collections import Counter
from datetime import datetime
from typing import List

from signal_engine.collectors.registry import register_collector
from signal_engine.collectors.solana.solana_shared import (
    debug_log,
    get_token_largest_accounts,
    parse_csv_env,
)
from models.signal import Signal


TRACKED_MINTS = parse_csv_env(os.getenv("TOKN_SOL_TRACKED_MINTS"))
MIN_WHALE_BALANCE = float(os.getenv("TOKN_SOL_MIN_WHALE_BALANCE", "10000"))
MIN_CLUSTER_SIZE = int(os.getenv("TOKN_SOL_MIN_WHALE_CLUSTER_SIZE", "3"))


def _safe_float(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


@register_collector(
    name="solana_whale_clusters",
    priority=2,
    tags=["solana", "whales", "clusters", "broadcast", "trading"],
    category="onchain",
    execution="slow",
)
def fetch_solana_whale_cluster_signals() -> List[Signal]:
    prefix = "SOLANA WHALES"
    started = time.time()
    signals: List[Signal] = []

    if not TRACKED_MINTS:
        print(f"[{prefix}] no tracked mints configured")
        return signals

    cluster_count = 0

    for mint in TRACKED_MINTS:
        holders = get_token_largest_accounts(mint, prefix=prefix)
        if not holders:
            continue

        whale_accounts = []
        for holder in holders:
            amount = _safe_float(holder.get("uiAmount"))
            address = holder.get("address")
            if not address:
                continue
            if amount < MIN_WHALE_BALANCE:
                continue
            whale_accounts.append((address, amount))

        debug_log(prefix, f"mint={mint[:8]} whales={len(whale_accounts)}")

        if len(whale_accounts) < MIN_CLUSTER_SIZE:
            continue

        cluster_count += 1

        top_addresses = ", ".join([addr[:8] for addr, _ in whale_accounts[:3]])
        total_whale_balance = sum(amount for _, amount in whale_accounts)

        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_whale_cluster",
                entity=mint,
                title="Solana whale cluster detected",
                summary=(
                    f"Mint {mint} has {len(whale_accounts)} large holder accounts; "
                    f"top wallet cluster sample: {top_addresses}; "
                    f"combined balance {total_whale_balance:,.2f}"
                ),
                confidence=0.79,
                sentiment_score=0.12,
                raw_url=f"https://solscan.io/token/{mint}",
            )
        )

    if cluster_count:
        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_whale_cluster_summary",
                entity="SOLANA_WHALE_CLUSTERS",
                title="Solana whale clustering activity summary",
                summary=f"Detected whale clustering across {cluster_count} tracked Solana mints",
                confidence=0.76,
                sentiment_score=0.14,
                raw_url=None,
            )
        )

    runtime = round(time.time() - started, 2)
    print(
        f"[{prefix}] tracked={len(TRACKED_MINTS)} "
        f"clusters={cluster_count} returned={len(signals)} runtime={runtime}s"
    )

    return signals
