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
# MODULE: solana_raydium_pools
# PURPOSE: Detect Raydium initialization-style activity for newly tradable pairs.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

Feeds
-----
• memecoin bot
• narrative enrichment
• alerts
• broadcast segments
• newsletters

Notes
-----
Program list is env-overridable with TOKN_SOL_RAYDIUM_PROGRAMS.

Author: TOKN Systems
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Dict, List, Set

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


DEFAULT_RAYDIUM_PROGRAMS = [
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
]

SIGNATURE_LIMIT = int(os.getenv("TOKN_SOL_RAYDIUM_SIGNATURE_LIMIT", "80"))
MAX_TX_SCAN = int(os.getenv("TOKN_SOL_RAYDIUM_MAX_TX_SCAN", "60"))

RAYDIUM_PROGRAMS = parse_csv_env(os.getenv("TOKN_SOL_RAYDIUM_PROGRAMS")) or DEFAULT_RAYDIUM_PROGRAMS


def _looks_like_pool_init(logs: List[str]) -> bool:
    joined = " | ".join(logs).lower()
    return any(
        marker in joined
        for marker in [
            "initialize",
            "initialize2",
            "create pool",
            "init_pc_amount",
            "amm",
        ]
    )


def _extract_pair_from_tx(tx: Dict) -> List[str]:
    deltas = token_balance_deltas(tx)

    positive_mints = []
    for row in deltas:
        mint = row.get("mint")
        delta = row.get("delta", 0.0)
        if not mint:
            continue
        if abs(delta) <= 0:
            continue
        positive_mints.append(str(mint))

    pair = dedupe_keep_order(positive_mints)
    return pair[:2]


@register_collector(
    name="solana_raydium_pools",
    priority=2,
    tags=["solana", "raydium", "dex", "liquidity", "broadcast"],
    category="onchain",
)
def fetch_solana_raydium_pool_signals() -> List[Signal]:
    prefix = "SOLANA RAYDIUM"
    started = time.time()
    signals: List[Signal] = []

    signature_records = []
    for program_id in RAYDIUM_PROGRAMS:
        rows = get_signatures_for_address(program_id, SIGNATURE_LIMIT, prefix=prefix)
        debug_log(prefix, f"program={program_id[:8]} rows={len(rows)}")
        signature_records.extend(rows)

    unique_signatures = dedupe_keep_order(
        [row.get("signature") for row in signature_records if isinstance(row, dict) and row.get("signature")]
    )[:MAX_TX_SCAN]

    pool_events = 0
    hot_pairs: Set[str] = set()

    for sig in unique_signatures:
        tx = get_transaction(sig, prefix=prefix)
        if not tx:
            continue

        logs = get_log_messages(tx)
        if not _looks_like_pool_init(logs):
            continue

        pair = _extract_pair_from_tx(tx)
        pair_key = " / ".join(pair) if pair else f"RAYDIUM:{sig[:12]}"
        primary = pair[0] if pair else None
        hot_pairs.add(pair_key)
        pool_events += 1

        debug_log(prefix, f"pool_event signature={sig[:12]} pair={pair_key}")

        if pair_key in hot_pairs:
            continue

        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_raydium_pool_init",
                entity=primary,
                title="Raydium liquidity pool activity detected",
                summary=f"Potential new Raydium pool initialization observed for {pair_key}",
                confidence=0.78,
                sentiment_score=0.22,
                raw_url=f"https://solscan.io/tx/{sig}",
            )
        )

    if pool_events:
        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_raydium_pool_activity",
                entity="RAYDIUM_POOL_ACTIVITY",
                title="Raydium pool initialization activity",
                summary=f"{pool_events} recent Raydium initialization-style events observed across {len(hot_pairs)} pairs",
                confidence=0.72,
                sentiment_score=0.28,
                raw_url=None,
            )
        )

    runtime = round(time.time() - started, 2)
    print(
        f"[{prefix}] signatures={len(unique_signatures)} "
        f"pool_events={pool_events} pairs={len(hot_pairs)} "
        f"returned={len(signals)} runtime={runtime}s"
    )

    return signals
