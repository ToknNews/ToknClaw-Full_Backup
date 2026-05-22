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
# MODULE: solana_token_mints
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
Solana Token Mint Collector

Purpose
-------
Detect recently observed token mint activity on Solana.

Feeds
-----
• memecoin bot
• narrative engine
• broadcast enrichment
• alerts
• social content
• newsletters

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
    flatten_instructions,
    get_log_messages,
    get_signatures_for_address,
    get_transaction,
)
from models.signal import Signal


TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
}

SIGNATURE_LIMIT = int(os.getenv("TOKN_SOL_MINT_SIGNATURE_LIMIT", "120"))
MAX_TX_SCAN = int(os.getenv("TOKN_SOL_MINT_MAX_TX_SCAN", "80"))

MINT_TYPES = {
    "initializeMint",
    "initializeMint2",
    "mintTo",
    "mintToChecked",
}


def _extract_mints_from_ixs(instructions: List[Dict]) -> Set[str]:
    mints: Set[str] = set()

    for ix in instructions:
        if not isinstance(ix, dict):
            continue

        parsed = ix.get("parsed")
        if not isinstance(parsed, dict):
            continue

        ix_type = parsed.get("type")
        if ix_type not in MINT_TYPES:
            continue

        info = parsed.get("info")
        if not isinstance(info, dict):
            continue

        mint = info.get("mint")
        if isinstance(mint, str) and mint:
            mints.add(mint)

    return mints


@register_collector(
    name="solana_token_mints",
    priority=2,
    tags=["solana", "mint", "retail", "memecoin", "broadcast"],
    category="onchain",
)
def fetch_solana_token_mints_signals() -> List[Signal]:
    prefix = "SOLANA MINT"
    started = time.time()
    signals: List[Signal] = []

    signature_records: List[Dict] = []

    for program_id in TOKEN_PROGRAMS:
        rows = get_signatures_for_address(program_id, SIGNATURE_LIMIT, prefix=prefix)
        debug_log(prefix, f"program={program_id[:8]} rows={len(rows)}")
        signature_records.extend(rows)

    unique_signatures = dedupe_keep_order(
        [row.get("signature") for row in signature_records if isinstance(row, dict) and row.get("signature")]
    )[:MAX_TX_SCAN]

    debug_log(prefix, f"unique_signatures={len(unique_signatures)}")

    detected_mints: Set[str] = set()
    mint_tx_count = 0

    for sig in unique_signatures:
        tx = get_transaction(sig, prefix=prefix)
        if not tx:
            continue

        instructions = flatten_instructions(tx)
        found = _extract_mints_from_ixs(instructions)

        if found:
            mint_tx_count += 1
            debug_log(prefix, f"signature={sig[:12]} found_mints={len(found)}")

        detected_mints.update(found)

    now = datetime.utcnow()

    for mint in sorted(detected_mints):
        signals.append(
            Signal(
                timestamp=now,
                source="chainstack",
                signal_type="solana_token_mint",
                entity=mint,
                title="New Solana token mint observed",
                summary=f"Mint activity observed for token {mint}",
                confidence=0.86,
                sentiment_score=None,
                raw_url=f"https://solscan.io/token/{mint}",
            )
        )

    if detected_mints:
        signals.append(
            Signal(
                timestamp=now,
                source="chainstack",
                signal_type="solana_mint_activity",
                entity="SOLANA_MINT_ACTIVITY",
                title="Solana mint activity spike",
                summary=f"{len(detected_mints)} unique token mints observed across {mint_tx_count} recent transactions",
                confidence=0.74,
                sentiment_score=0.35,
                raw_url=None,
            )
        )

    runtime = round(time.time() - started, 2)
    print(
        f"[{prefix}] signatures={len(unique_signatures)} "
        f"mint_txs={mint_tx_count} unique_mints={len(detected_mints)} "
        f"returned={len(signals)} runtime={runtime}s"
    )

    return signals
