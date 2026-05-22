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
# MODULE: solana_volume_velocity
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
Solana Volume Velocity Collector

Purpose
-------
Detect short-term velocity and repeated swap activity across
Jupiter-routed Solana transactions.

Feeds
-----
• memecoin trading bot
• velocity / momentum analysis
• narrative enrichment
• broadcast alerts
• newsletter and social content

Detection
---------
• repeated recent swap routes
• repeated mint pair appearances
• short-burst retail activity
• momentum clustering

Author: TOKN Systems
"""

from __future__ import annotations

import os
import time
from collections import Counter
from datetime import datetime
from typing import Dict, List

from signal_engine.collectors.registry import register_collector
from signal_engine.collectors.solana.solana_shared import (
    debug_log,
    dedupe_keep_order,
    get_log_messages,
    get_signatures_for_address,
    get_transaction,
    parse_csv_env,
    token_balance_deltas,
)
from models.signal import Signal


DEFAULT_JUPITER_PROGRAMS = [
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
]

SIGNATURE_LIMIT = int(os.getenv("TOKN_SOL_VELOCITY_SIGNATURE_LIMIT", "120"))
MAX_TX_SCAN = int(os.getenv("TOKN_SOL_VELOCITY_MAX_TX_SCAN", "100"))
MIN_PAIR_HITS = int(os.getenv("TOKN_SOL_VELOCITY_MIN_PAIR_HITS", "3"))

JUPITER_PROGRAMS = parse_csv_env(os.getenv("TOKN_SOL_JUPITER_PROGRAMS")) or DEFAULT_JUPITER_PROGRAMS


def _looks_like_swap(logs: List[str]) -> bool:
    joined = " | ".join(logs).lower()
    return any(marker in joined for marker in ["swap", "route", "jupiter"])


def _pair_from_tx(tx: Dict) -> str | None:
    deltas = token_balance_deltas(tx)

    moved = []
    for row in deltas:
        mint = row.get("mint")
        delta = row.get("delta", 0.0)
        if not mint:
            continue
        if abs(delta) <= 0:
            continue
        moved.append(str(mint))

    moved = dedupe_keep_order(moved)

    if len(moved) >= 2:
        return f"{moved[0]} / {moved[1]}"
    if len(moved) == 1:
        return moved[0]

    return None


@register_collector(
    name="solana_volume_velocity",
    priority=2,
    tags=["solana", "velocity", "momentum", "broadcast", "trading"],
    category="onchain",
)
def fetch_solana_volume_velocity_signals() -> List[Signal]:
    prefix = "SOLANA VELOCITY"
    started = time.time()
    signals: List[Signal] = []

    signature_rows = []

    for program_id in JUPITER_PROGRAMS:
        rows = get_signatures_for_address(program_id, SIGNATURE_LIMIT, prefix=prefix)
        debug_log(prefix, f"program={program_id[:8]} rows={len(rows)}")
        signature_rows.extend(rows)

    unique_signatures = dedupe_keep_order(
        [row.get("signature") for row in signature_rows if isinstance(row, dict) and row.get("signature")]
    )[:MAX_TX_SCAN]

    pair_counter: Counter = Counter()
    scanned_swaps = 0

    for sig in unique_signatures:
        tx = get_transaction(sig, prefix=prefix)
        if not tx:
            continue

        logs = get_log_messages(tx)
        if not _looks_like_swap(logs):
            continue

        pair = _pair_from_tx(tx)
        if not pair:
            continue

        pair_counter[pair] += 1
        scanned_swaps += 1

    debug_log(prefix, f"scanned_swaps={scanned_swaps} tracked_pairs={len(pair_counter)}")

    now = datetime.utcnow()

    for pair, count in pair_counter.most_common():
        if count < MIN_PAIR_HITS:
            continue

        signals.append(
            Signal(
                timestamp=now,
                source="chainstack",
                signal_type="solana_volume_velocity",
                entity=pair,
                title="Solana swap velocity building",
                summary=f"Pair {pair} appeared {count} times in recent Jupiter-routed activity",
                confidence=0.78,
                sentiment_score=0.25,
                raw_url=None,
            )
        )

    if pair_counter:
        top_pair, top_hits = pair_counter.most_common(1)[0]
        signals.append(
            Signal(
                timestamp=now,
                source="chainstack",
                signal_type="solana_velocity_summary",
                entity="SOLANA_VELOCITY",
                title="Solana velocity activity summary",
                summary=f"Tracked {scanned_swaps} recent swap events; hottest pair: {top_pair} ({top_hits} hits)",
                confidence=0.72,
                sentiment_score=0.22,
                raw_url=None,
            )
        )

    runtime = round(time.time() - started, 2)
    print(
        f"[{prefix}] signatures={len(unique_signatures)} "
        f"swaps={scanned_swaps} pairs={len(pair_counter)} "
        f"returned={len(signals)} runtime={runtime}s"
    )

    return signals
