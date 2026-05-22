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
# MODULE: solana_jupiter_swaps
# PURPOSE: Detect Jupiter swap-route activity for momentum and narrative enrichment.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

Feeds
-----
• trading bot context
• retail momentum
• broadcast enrichment
• newsletter analytics
• social alerts

Notes
-----
Program list is env-overridable with TOKN_SOL_JUPITER_PROGRAMS.

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
    short_addr,
    token_balance_deltas,
)
from models.signal import Signal


DEFAULT_JUPITER_PROGRAMS = [
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
]

SIGNATURE_LIMIT = int(os.getenv("TOKN_SOL_JUPITER_SIGNATURE_LIMIT", "80"))
MAX_TX_SCAN = int(os.getenv("TOKN_SOL_JUPITER_MAX_TX_SCAN", "60"))

JUPITER_PROGRAMS = parse_csv_env(os.getenv("TOKN_SOL_JUPITER_PROGRAMS")) or DEFAULT_JUPITER_PROGRAMS


def _looks_like_jupiter_swap(logs: List[str]) -> bool:
    joined = " | ".join(logs).lower()
    return any(marker in joined for marker in ["route", "swap", "jupiter"])


def _pair_from_deltas(tx: Dict) -> str | None:
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
    name="solana_jupiter_swaps",
    priority=2,
    tags=["solana", "jupiter", "swaps", "retail", "broadcast"],
    category="onchain",
)
def fetch_solana_jupiter_swap_signals() -> List[Signal]:
    prefix = "SOLANA JUPITER"
    started = time.time()
    signals: List[Signal] = []

    signature_records = []
    for program_id in JUPITER_PROGRAMS:
        rows = get_signatures_for_address(program_id, SIGNATURE_LIMIT, prefix=prefix)
        debug_log(prefix, f"program={program_id[:8]} rows={len(rows)}")
        signature_records.extend(rows)

    unique_signatures = dedupe_keep_order(
        [row.get("signature") for row in signature_records if isinstance(row, dict) and row.get("signature")]
    )[:MAX_TX_SCAN]

    pair_counter: Counter = Counter()
    swap_events = 0

    for sig in unique_signatures:
        tx = get_transaction(sig, prefix=prefix)
        if not tx:
            continue

        logs = get_log_messages(tx)
        if not _looks_like_jupiter_swap(logs):
            continue

        pair = _pair_from_deltas(tx) or f"JUPITER:{sig[:10]}"
        primary = pair.split(" / ")[0] if pair and " / " in pair else pair
        pair_counter[pair] += 1
        swap_events += 1

        debug_log(prefix, f"swap_event signature={sig[:12]} pair={pair}")

        if pair_counter[pair] > 3:
            continue

        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_jupiter_swap",
                entity=primary,
                title="Jupiter swap route detected",
                summary=f"Recent Jupiter swap activity observed for {pair}",
                confidence=0.73,
                sentiment_score=0.18,
                raw_url=f"https://solscan.io/tx/{sig}",
            )
        )

    if swap_events:
        hot_pair, hot_count = pair_counter.most_common(1)[0]
        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_jupiter_swap_activity",
                entity="JUPITER_SWAP_ACTIVITY",
                title="Jupiter swap activity building",
                summary=f"{swap_events} recent Jupiter swap events observed; hottest route: {hot_pair} ({hot_count} events)",
                confidence=0.69,
                sentiment_score=0.2,
                raw_url=None,
            )
        )

    runtime = round(time.time() - started, 2)
    print(
        f"[{prefix}] signatures={len(unique_signatures)} "
        f"swap_events={swap_events} hot_pairs={len(pair_counter)} "
        f"returned={len(signals)} runtime={runtime}s"
    )

    return signals
