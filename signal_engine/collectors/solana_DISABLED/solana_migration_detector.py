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
# MODULE: solana_migration_detector
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
Solana Liquidity Migration Detector

Purpose
-------
Detect when Solana meme tokens appear to migrate from Pump.fun-style
early activity into Raydium pool creation and active trading flow.

Responsibilities
----------------
• read recent Solana rows from signal lake
• normalize token identifiers from single-token and pair entities
• correlate Pump.fun activity with Raydium pool init
• enrich with liquidity / swap / velocity / MEV context
• emit structured migration signals for trading and broadcast use
• include production debug diagnostics for troubleshooting

Signals Produced
----------------
• solana_liquidity_migration
• solana_migration_watch
• solana_post_migration_dip_candidate
• solana_post_migration_breakout_candidate
• solana_migration_risk_alert
• solana_meme_trend_candidate

Author: TOKN Systems
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

from signal_engine.collectors.registry import register_collector
from models.signal import Signal
from signal_lake import load_signal_lake


# ---------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------

ENV_PATH = "/opt/toknclaw/signal_engine/.env"
load_dotenv(ENV_PATH)

DEBUG = os.getenv("TOKN_DEBUG_COLLECTORS", "1") == "1"

LOOKBACK_MINUTES = int(os.getenv("TOKN_SOL_MIGRATION_LOOKBACK_MINUTES", "180"))
MAX_ROWS = int(os.getenv("TOKN_SOL_MIGRATION_MAX_ROWS", "4000"))
MIN_RAYDIUM_POOLS = int(os.getenv("TOKN_SOL_MIGRATION_MIN_RAYDIUM_POOLS", "1"))
MIN_PUMPFUN_ACTIVITY = int(os.getenv("TOKN_SOL_MIGRATION_MIN_PUMPFUN_ACTIVITY", "1"))
MIN_CONFIRMATION_COUNT = int(os.getenv("TOKN_SOL_MIGRATION_MIN_CONFIRMATIONS", "1"))
MAX_MEV_FOR_DIP = int(os.getenv("TOKN_SOL_MIGRATION_MAX_MEV_FOR_DIP", "12"))
HIGH_MEV_RISK = int(os.getenv("TOKN_SOL_MIGRATION_HIGH_MEV_RISK", "30"))

STABLE_OR_BASE_ASSETS: Set[str] = {
    "So11111111111111111111111111111111111111112",   # SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",   # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",   # USDT
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",    # mSOL
    "7dHbWXad2mHs4mFSLriQjQF2g3Y8w1xY4tVx5xQ7K7z",    # stSOL common
}


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def debug_log(message: str) -> None:
    if DEBUG:
        print(f"[SOLANA MIGRATION] {message}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if not isinstance(value, str):
        return None

    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def is_probable_token(value: Any) -> bool:
    return isinstance(value, str) and 20 <= len(value.strip()) <= 60


def split_pair(entity: str) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(entity, str) or not entity.strip():
        return None, None

    if " / " in entity:
        left, right = entity.split(" / ", 1)
        return left.strip(), right.strip()

    if "/" in entity:
        left, right = entity.split("/", 1)
        return left.strip(), right.strip()

    return entity.strip(), None


def extract_primary_token(entity: Any) -> Optional[str]:
    if not isinstance(entity, str) or not entity.strip():
        return None

    left, right = split_pair(entity)

    if right is None:
        return left if is_probable_token(left) else None

    candidates = [x for x in (left, right) if is_probable_token(x)]
    if not candidates:
        return None

    non_base = [x for x in candidates if x not in STABLE_OR_BASE_ASSETS]
    if non_base:
        return non_base[0]

    return candidates[0]


def recent_rows() -> List[Dict[str, Any]]:
    lake = load_signal_lake()
    rows = lake.get("signals", [])
    if not isinstance(rows, list):
        return []

    cutoff = utc_now() - timedelta(minutes=LOOKBACK_MINUTES)
    out: List[Dict[str, Any]] = []

    for row in rows[-MAX_ROWS:]:
        if not isinstance(row, dict):
            continue

        dt = parse_dt(row.get("timestamp"))
        if dt is None or dt < cutoff:
            continue

        out.append(row)

    return out


def score_confidence(
    pumpfun_count: int,
    raydium_count: int,
    liquidity_count: int,
    jupiter_count: int,
    velocity_count: int,
    mev_count: int,
) -> float:
    score = 0.68

    if pumpfun_count >= 1:
        score += 0.06
    if raydium_count >= 1:
        score += 0.08
    if liquidity_count >= 1:
        score += 0.05
    if jupiter_count >= 1:
        score += 0.04
    if velocity_count >= 1:
        score += 0.04

    if mev_count >= HIGH_MEV_RISK:
        score -= 0.08
    elif mev_count >= 10:
        score -= 0.03

    return max(0.51, min(0.93, round(score, 2)))


# ---------------------------------------------------
# COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="solana_migration_detector",
    priority=1,
    tags=["solana", "migration", "raydium", "pumpfun", "trading", "broadcast"],
    timeout=10,
)
def fetch_solana_migration_signals() -> List[Signal]:
    rows = recent_rows()

    token_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {
            "pumpfun_activity": 0,
            "raydium_pool_init": 0,
            "liquidity_event": 0,
            "jupiter_swap": 0,
            "volume_velocity": 0,
            "mev_activity": 0,
            "thin_liquidity_alert": 0,
        }
    )

    seen_types = set()

    for row in rows:
        signal_type = row.get("signal_type")
        entity = row.get("entity")
        token = extract_primary_token(entity)

        if not token:
            continue

        seen_types.add(signal_type)

        if signal_type in ("solana_pumpfun_activity", "solana_pumpfun_stream_event"):
            token_stats[token]["pumpfun_activity"] += 1

        elif signal_type in ("solana_raydium_pool_init", "solana_raydium_stream_event"):
            token_stats[token]["raydium_pool_init"] += 1

        elif signal_type == "solana_liquidity_event":
            token_stats[token]["liquidity_event"] += 1

        elif signal_type in ("solana_jupiter_swap", "solana_jupiter_stream_event"):
            token_stats[token]["jupiter_swap"] += 1

        elif signal_type == "solana_volume_velocity":
            token_stats[token]["volume_velocity"] += 1

        elif signal_type == "solana_mev_activity":
            token_stats[token]["mev_activity"] += 1

        elif signal_type == "solana_thin_liquidity_alert":
            token_stats[token]["thin_liquidity_alert"] += 1

    now = utc_now()
    signals: List[Signal] = []

    candidate_tokens = 0
    migrated_tokens = 0

    for token, stats in token_stats.items():
        pumpfun_count = stats["pumpfun_activity"]
        raydium_count = stats["raydium_pool_init"]
        liquidity_count = stats["liquidity_event"]
        jupiter_count = stats["jupiter_swap"]
        velocity_count = stats["volume_velocity"]
        mev_count = stats["mev_activity"]
        thin_count = stats["thin_liquidity_alert"]

        if pumpfun_count < MIN_PUMPFUN_ACTIVITY:
            continue

        candidate_tokens += 1

        confirmation_count = 0
        if liquidity_count > 0:
            confirmation_count += 1
        if jupiter_count > 0:
            confirmation_count += 1
        if velocity_count > 0:
            confirmation_count += 1

        if raydium_count < MIN_RAYDIUM_POOLS or confirmation_count < MIN_CONFIRMATION_COUNT:
            continue

        migrated_tokens += 1
        confidence = score_confidence(
            pumpfun_count=pumpfun_count,
            raydium_count=raydium_count,
            liquidity_count=liquidity_count,
            jupiter_count=jupiter_count,
            velocity_count=velocity_count,
            mev_count=mev_count,
        )

        signals.append(
            Signal(
                timestamp=now,
                source="toknclaw",
                signal_type="solana_liquidity_migration",
                entity=token,
                title="Solana liquidity migration detected",
                summary=(
                    f"Token {token} shows Pump.fun-to-Raydium migration behavior. "
                    f"pumpfun_activity={pumpfun_count}, "
                    f"raydium_pool_init={raydium_count}, "
                    f"liquidity_event={liquidity_count}, "
                    f"jupiter_swap={jupiter_count}, "
                    f"volume_velocity={velocity_count}, "
                    f"mev_activity={mev_count}."
                ),
                confidence=confidence,
                sentiment_score=0.34,
                raw_url=None,
            )
        )

        signals.append(
            Signal(
                timestamp=now,
                source="toknclaw",
                signal_type="solana_migration_watch",
                entity=token,
                title="Migration watch candidate",
                summary=(
                    f"Monitor {token} for post-migration price reaction, "
                    f"liquidity retention, and secondary momentum."
                ),
                confidence=max(0.55, confidence - 0.06),
                sentiment_score=0.22,
                raw_url=None,
            )
        )

        if jupiter_count > 0 or velocity_count > 0:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_meme_trend_candidate",
                    entity=token,
                    title="Solana meme trend candidate",
                    summary=(
                        f"{token} has migrated into active trading flow and may be relevant for "
                        f"ToknNews culture coverage, Bitsy commentary, and meme trend watchlists."
                    ),
                    confidence=max(0.54, confidence - 0.08),
                    sentiment_score=0.41,
                    raw_url=None,
                )
            )

        if (
            liquidity_count > 0
            and jupiter_count > 0
            and velocity_count > 0
            and mev_count <= MAX_MEV_FOR_DIP
        ):
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_post_migration_dip_candidate",
                    entity=token,
                    title="Post-migration dip-buy candidate",
                    summary=(
                        f"{token} fits an early post-migration dip-buy profile: "
                        f"Raydium live, liquidity present, swaps active, velocity positive, "
                        f"and MEV not yet excessive."
                    ),
                    confidence=max(0.58, confidence - 0.02),
                    sentiment_score=0.48,
                    raw_url=None,
                )
            )

        if jupiter_count >= 2 and velocity_count >= 1 and mev_count < HIGH_MEV_RISK:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_post_migration_breakout_candidate",
                    entity=token,
                    title="Post-migration breakout follow candidate",
                    summary=(
                        f"{token} shows signs of tradable continuation after migration."
                    ),
                    confidence=max(0.56, confidence - 0.04),
                    sentiment_score=0.44,
                    raw_url=None,
                )
            )

        if thin_count > 0 or mev_count >= HIGH_MEV_RISK:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_migration_risk_alert",
                    entity=token,
                    title="Migration risk alert",
                    summary=(
                        f"{token} has migration behavior but elevated execution risk. "
                        f"thin_liquidity_alert={thin_count}, mev_activity={mev_count}."
                    ),
                    confidence=max(0.57, confidence - 0.01),
                    sentiment_score=-0.39,
                    raw_url=None,
                )
            )

    debug_log(
        f"rows={len(rows)} "
        f"token_stats={len(token_stats)} "
        f"candidate_tokens={candidate_tokens} "
        f"migrated_tokens={migrated_tokens} "
        f"signals_returned={len(signals)} "
        f"seen_types={sorted([x for x in seen_types if isinstance(x, str)])[:20]}"
    )

    return signals
