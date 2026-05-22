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
# MODULE: solana_pumpfun_tokens
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
Solana Pump.fun Activity Collector

Purpose
-------
Monitor recent Pump.fun program activity for early memecoin
launch detection and retail narrative enrichment.

Feeds
-----
• memecoin bot
• launch detection
• broadcast narratives
• social alerts
• newsletters
• migration correlation
• strategy engines
• ToknNews culture segments

Detection
---------
• recent Pump.fun signatures
• launch-like activity bursts
• token mint extraction from parsed transaction data
• retail issuance pressure
• token-level entity mapping for downstream migration logic

Notes
-----
Program list can be overridden with TOKN_SOL_PUMPFUN_PROGRAMS.

Author: TOKN Systems
"""

from __future__ import annotations

import os
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from signal_engine.collectors.registry import register_collector
from signal_engine.collectors.solana.solana_shared import (
    debug_log,
    dedupe_keep_order,
    get_log_messages,
    get_signatures_for_address,
    get_transaction,
    parse_csv_env,
)
from models.signal import Signal


DEFAULT_PUMPFUN_PROGRAMS = [
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
]

SIGNATURE_LIMIT = int(os.getenv("TOKN_SOL_PUMPFUN_SIGNATURE_LIMIT", "120"))
MAX_TX_SCAN = int(os.getenv("TOKN_SOL_PUMPFUN_MAX_TX_SCAN", "90"))
MAX_PER_RUN = int(os.getenv("TOKN_SOL_PUMPFUN_MAX_SIGNALS", "120"))

PUMPFUN_PROGRAMS = parse_csv_env(os.getenv("TOKN_SOL_PUMPFUN_PROGRAMS")) or DEFAULT_PUMPFUN_PROGRAMS

BASE_OR_STABLE_MINTS: Set[str] = {
    "So11111111111111111111111111111111111111112",   # SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",   # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",   # USDT
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",    # mSOL
    "7dHbWXad2mHs4mFSLriQjQF2g3Y8w1xY4tVx5xQ7K7z",    # common stSOL
}

LAUNCH_LOG_MARKERS = [
    "pump",
    "buy",
    "sell",
    "bonding",
    "mint",
    "create",
    "initialize",
    "launch",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _looks_like_token_mint(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    if len(value) < 20 or len(value) > 64:
        return False
    return True


def _looks_like_pumpfun_token(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    return value.endswith("pump") and _looks_like_token_mint(value)


def _looks_like_pumpfun_launch(logs: List[str]) -> bool:
    joined = " | ".join(logs).lower()
    return any(marker in joined for marker in LAUNCH_LOG_MARKERS)


def _iter_instruction_dicts(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    transaction = tx.get("transaction") or {}
    message = transaction.get("message") or {}
    meta = tx.get("meta") or {}

    top_level = message.get("instructions") or []
    for item in top_level:
        if isinstance(item, dict):
            out.append(item)

    inner_groups = meta.get("innerInstructions") or []
    for group in inner_groups:
        if not isinstance(group, dict):
            continue
        for item in group.get("instructions") or []:
            if isinstance(item, dict):
                out.append(item)

    return out


def _collect_candidate_mints(tx: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []

    # token balances
    meta = tx.get("meta") or {}
    for balance_group_key in ("preTokenBalances", "postTokenBalances"):
        for row in meta.get(balance_group_key) or []:
            if not isinstance(row, dict):
                continue
            mint = row.get("mint")
            if _looks_like_token_mint(mint):
                candidates.append(mint)

    # parsed instructions
    for ix in _iter_instruction_dicts(tx):
        parsed = ix.get("parsed")
        if not isinstance(parsed, dict):
            continue

        info = parsed.get("info") or {}
        if isinstance(info, dict):
            for key in (
                "mint",
                "tokenMint",
                "newMint",
                "baseMint",
                "quoteMint",
                "lpMint",
            ):
                mint = info.get(key)
                if _looks_like_token_mint(mint):
                    candidates.append(mint)

        ix_type = _safe_str(parsed.get("type")).lower()
        if ix_type in {
            "mintto",
            "minttochecked",
            "initializemint",
            "initializemint2",
            "create",
            "createaccount",
        } and isinstance(info, dict):
            mint = info.get("mint")
            if _looks_like_token_mint(mint):
                candidates.append(mint)

    # account keys fallback
    transaction = tx.get("transaction") or {}
    message = transaction.get("message") or {}
    account_keys = message.get("accountKeys") or []
    for key in account_keys:
        if isinstance(key, str) and _looks_like_pumpfun_token(key):
            candidates.append(key)
        elif isinstance(key, dict):
            pubkey = key.get("pubkey")
            if _looks_like_pumpfun_token(pubkey):
                candidates.append(pubkey)

    return candidates


def _select_primary_token_mint(tx: Dict[str, Any], logs: List[str]) -> Optional[str]:
    candidates = _collect_candidate_mints(tx)

    if not candidates:
        return None

    # strongest signal: explicit .pump mint
    for mint in candidates:
        if _looks_like_pumpfun_token(mint):
            return mint

    # remove base/stable assets
    filtered = [mint for mint in candidates if mint not in BASE_OR_STABLE_MINTS]
    if filtered:
        counts = Counter(filtered)
        return counts.most_common(1)[0][0]

    # final fallback: most common candidate
    counts = Counter(candidates)
    return counts.most_common(1)[0][0]


def _build_funny_name_signal(token_mint: str) -> Optional[Signal]:
    if not token_mint.endswith("pump"):
        return None

    return Signal(
        timestamp=utc_now(),
        source="chainstack",
        signal_type="solana_funny_name_candidate",
        entity=token_mint,
        title="Bitsy meme name candidate detected",
        summary=f"New Pump.fun token name candidate spotted: {token_mint}",
        confidence=0.58,
        sentiment_score=0.22,
        raw_url=f"https://solscan.io/token/{token_mint}",
    )


@register_collector(
    name="solana_pumpfun_tokens",
    priority=2,
    tags=["solana", "pumpfun", "memecoin", "retail", "broadcast"],
    category="onchain",
)
def fetch_solana_pumpfun_signals() -> List[Signal]:
    prefix = "SOLANA PUMPFUN"
    started = time.time()
    signals: List[Signal] = []

    signature_rows: List[Dict[str, Any]] = []

    for program_id in PUMPFUN_PROGRAMS:
        rows = get_signatures_for_address(program_id, SIGNATURE_LIMIT, prefix=prefix)
        debug_log(prefix, f"program={program_id[:8]} rows={len(rows)}")
        signature_rows.extend(rows)

    unique_signatures = dedupe_keep_order(
        [
            row.get("signature")
            for row in signature_rows
            if isinstance(row, dict) and row.get("signature")
        ]
    )[:MAX_TX_SCAN]

    launch_events = 0
    hourly_pressure = Counter()
    seen_token_mints: Set[str] = set()
    token_event_counts = Counter()

    for sig in unique_signatures:
        tx = get_transaction(sig, prefix=prefix)
        if not tx:
            continue

        logs = get_log_messages(tx)
        if not _looks_like_pumpfun_launch(logs):
            continue

        token_mint = _select_primary_token_mint(tx, logs)
        if not token_mint:
            debug_log(prefix, f"no token mint extracted signature={sig[:12]}")
            continue

        launch_events += 1
        token_event_counts[token_mint] += 1

        block_time = tx.get("blockTime")
        if isinstance(block_time, int):
            hour_bucket = block_time // 3600
            hourly_pressure[hour_bucket] += 1

        signals.append(
            Signal(
                timestamp=utc_now(),
                source="chainstack",
                signal_type="solana_pumpfun_activity",
                entity=token_mint,
                title="Pump.fun launch activity detected",
                summary=f"Recent Pump.fun transaction observed for token {token_mint}: {sig[:12]}",
                confidence=0.73,
                sentiment_score=0.28,
                raw_url=f"https://solscan.io/tx/{sig}",
            )
        )

        if token_mint not in seen_token_mints:
            seen_token_mints.add(token_mint)

            signals.append(
                Signal(
                    timestamp=utc_now(),
                    source="chainstack",
                    signal_type="solana_pumpfun_launch",
                    entity=token_mint,
                    title="Pump.fun token launch detected",
                    summary=f"New Pump.fun launch candidate detected for token {token_mint}",
                    confidence=0.79,
                    sentiment_score=0.33,
                    raw_url=f"https://solscan.io/token/{token_mint}",
                )
            )

            funny_signal = _build_funny_name_signal(token_mint)
            if funny_signal:
                signals.append(funny_signal)

        if len(signals) >= MAX_PER_RUN:
            debug_log(prefix, f"max signal cap reached max_per_run={MAX_PER_RUN}")
            break

    if launch_events:
        hottest_bucket_hits = max(hourly_pressure.values()) if hourly_pressure else launch_events
        hottest_tokens = token_event_counts.most_common(5)
        token_summary = ", ".join(f"{mint}({count})" for mint, count in hottest_tokens)

        signals.append(
            Signal(
                timestamp=utc_now(),
                source="chainstack",
                signal_type="solana_pumpfun_summary",
                entity="PUMPFUN_ACTIVITY",
                title="Pump.fun launch pressure building",
                summary=(
                    f"{launch_events} recent Pump.fun activity events observed; "
                    f"peak bucket count: {hottest_bucket_hits}; "
                    f"top tokens: {token_summary}"
                ),
                confidence=0.76,
                sentiment_score=0.31,
                raw_url=None,
            )
        )

    runtime = round(time.time() - started, 2)
    print(
        f"[{prefix}] signatures={len(unique_signatures)} "
        f"launch_events={launch_events} "
        f"unique_tokens={len(seen_token_mints)} "
        f"returned={len(signals)} "
        f"runtime={runtime}s"
    )

    return signals
