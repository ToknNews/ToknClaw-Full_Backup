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
# MODULE: solana_liquidity_depth
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
Solana Liquidity Depth Collector

Purpose
-------
Estimate recent Solana liquidity quality from Raydium pool activity
and token movement size.

Feeds
-----
• execution risk controls
• slippage monitoring
• memecoin trade quality scoring
• broadcast risk narratives
• newsletter analysis

Detection
---------
• recent Raydium activity
• thin-liquidity patterns
• shallow movement size
• liquidity imbalance risk

Author: TOKN Systems
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
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


DEFAULT_RAYDIUM_PROGRAMS = [
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
]

SIGNATURE_LIMIT = int(os.getenv("TOKN_SOL_DEPTH_SIGNATURE_LIMIT", "80"))
MAX_TX_SCAN = int(os.getenv("TOKN_SOL_DEPTH_MAX_TX_SCAN", "60"))
THIN_LIQUIDITY_THRESHOLD = float(os.getenv("TOKN_SOL_THIN_LIQUIDITY_THRESHOLD", "1000"))

RAYDIUM_PROGRAMS = parse_csv_env(os.getenv("TOKN_SOL_RAYDIUM_PROGRAMS")) or DEFAULT_RAYDIUM_PROGRAMS


def _looks_like_pool_activity(logs: List[str]) -> bool:
    joined = " | ".join(logs).lower()
    return any(marker in joined for marker in ["initialize", "amm", "pool", "swap"])


def _pair_stats_from_tx(tx: Dict) -> tuple[str | None, float]:
    deltas = token_balance_deltas(tx)

    moved = []
    total_abs = 0.0

    for row in deltas:
        mint = row.get("mint")
        delta = abs(float(row.get("delta", 0.0)))
        if not mint or delta <= 0:
            continue
        moved.append(str(mint))
        total_abs += delta

    moved = dedupe_keep_order(moved)

    if len(moved) >= 2:
        return f"{moved[0]} / {moved[1]}", total_abs
    if len(moved) == 1:
        return moved[0], total_abs

    return None, total_abs


@register_collector(
    name="solana_liquidity_depth",
    priority=2,
    tags=["solana", "liquidity", "depth", "execution", "broadcast"],
    category="onchain",
)
def fetch_solana_liquidity_depth_signals() -> List[Signal]:
    prefix = "SOLANA DEPTH"
    started = time.time()
    signals: List[Signal] = []

    signature_rows = []

    for program_id in RAYDIUM_PROGRAMS:
        rows = get_signatures_for_address(program_id, SIGNATURE_LIMIT, prefix=prefix)
        debug_log(prefix, f"program={program_id[:8]} rows={len(rows)}")
        signature_rows.extend(rows)

    unique_signatures = dedupe_keep_order(
        [row.get("signature") for row in signature_rows if isinstance(row, dict) and row.get("signature")]
    )[:MAX_TX_SCAN]

    pair_samples: Dict[str, List[float]] = defaultdict(list)

    for sig in unique_signatures:
        tx = get_transaction(sig, prefix=prefix)
        if not tx:
            continue

        logs = get_log_messages(tx)
        if not _looks_like_pool_activity(logs):
            continue

        pair, total_abs = _pair_stats_from_tx(tx)
        if not pair:
            continue

        pair_samples[pair].append(total_abs)

    debug_log(prefix, f"tracked_pairs={len(pair_samples)}")

    now = datetime.utcnow()

    for pair, samples in pair_samples.items():
        avg_depth_proxy = sum(samples) / len(samples) if samples else 0.0

        signals.append(
            Signal(
                timestamp=now,
                source="chainstack",
                signal_type="solana_liquidity_depth",
                entity=pair,
                title="Solana liquidity depth estimate updated",
                summary=(
                    f"Recent depth proxy for {pair}: "
                    f"avg movement size {avg_depth_proxy:,.2f} across {len(samples)} samples"
                ),
                confidence=0.74,
                sentiment_score=0.10,
                raw_url=None,
            )
        )

        if avg_depth_proxy < THIN_LIQUIDITY_THRESHOLD:
            signals.append(
                Signal(
                    timestamp=now,
                    source="chainstack",
                    signal_type="solana_thin_liquidity_alert",
                    entity=pair,
                    title="Thin Solana liquidity detected",
                    summary=(
                        f"Pair {pair} is showing shallow recent liquidity "
                        f"with avg depth proxy {avg_depth_proxy:,.2f}"
                    ),
                    confidence=0.80,
                    sentiment_score=-0.18,
                    raw_url=None,
                )
            )

    runtime = round(time.time() - started, 2)
    print(
        f"[{prefix}] signatures={len(unique_signatures)} "
        f"pairs={len(pair_samples)} returned={len(signals)} runtime={runtime}s"
    )

    return signals
