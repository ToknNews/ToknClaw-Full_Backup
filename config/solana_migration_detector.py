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
Solana Migration Detector

Purpose
-------
Detect Pump.fun token migration into Raydium / tradable Solana flow
using recent signal lake activity.

Responsibilities
----------------
• read recent Solana signals from signal lake
• identify migration candidates from Raydium pool init signals
• correlate migration with liquidity, swaps, velocity, and MEV
• emit structured migration signals for trading and broadcast
• produce meme trend candidates for ToknNews enrichment
• remain fully OpenClaw-agent compatible via config

Signals Produced
----------------
• solana_liquidity_migration
• solana_migration_watch
• solana_meme_trend_candidate
• solana_post_migration_dip_candidate
• solana_post_migration_breakout_candidate
• solana_migration_risk_alert

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
from runtime_config import load_config
from signal_lake import load_signal_lake


# ---------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------

ENV_PATH = "/opt/toknclaw/signal_engine/.env"
load_dotenv(ENV_PATH)

DEBUG = os.getenv("TOKN_DEBUG_COLLECTORS", "1") == "1"
CONFIG_FILE = "solana_migration_strategy.json"

STABLES: Set[str] = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
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
    if not value or not isinstance(value, str):
        return None

    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def load_strategy_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)
    if not isinstance(cfg, dict):
        return {
            "enabled": True,
            "lookback_minutes": 90,
            "max_pairs_per_run": 200,
            "migration_window_minutes": 45,
            "dip_buy": {
                "enabled": True,
                "min_liquidity_events": 1,
                "min_jupiter_swaps": 1,
                "min_velocity_signals": 1,
                "max_mev_signals": 8,
                "confidence": 0.83,
            },
            "breakout_follow": {
                "enabled": True,
                "min_jupiter_swaps": 2,
                "min_velocity_signals": 1,
                "max_mev_signals": 15,
                "confidence": 0.79,
            },
            "avoid_rules": {
                "enabled": True,
                "mev_spike_threshold": 20,
                "thin_liquidity_threshold": 1,
                "confidence": 0.84,
            },
        }
    return cfg


def recent_rows(lookback_minutes: int) -> List[Dict[str, Any]]:
    lake = load_signal_lake()
    rows = lake.get("signals", [])
    if not isinstance(rows, list):
        return []

    cutoff = utc_now() - timedelta(minutes=lookback_minutes)
    out: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        dt = parse_dt(row.get("timestamp"))
        if dt is None or dt < cutoff:
            continue
        out.append(row)

    return out


def split_pair(entity: str) -> Tuple[Optional[str], Optional[str]]:
    if not entity or not isinstance(entity, str):
        return None, None

    if " / " not in entity:
        return entity.strip(), None

    left, right = entity.split(" / ", 1)
    return left.strip(), right.strip()


def normalize_token_from_pair(entity: str) -> Optional[str]:
    left, right = split_pair(entity)

    if not left and not right:
        return None

    if left and right:
        if left in STABLES and right not in STABLES:
            return right
        if right in STABLES and left not in STABLES:
            return left
        if left not in STABLES:
            return left
        return right

    if left:
        return left

    return right


def short_token(token: str, n: int = 10) -> str:
    if not token:
        return "unknown"
    if len(token) <= n:
        return token
    return token[:n]


# ---------------------------------------------------
# AGGREGATION
# ---------------------------------------------------

def collect_migration_features(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    features: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "raydium_pool_inits": 0,
        "liquidity_events": 0,
        "jupiter_swaps": 0,
        "velocity_signals": 0,
        "mev_signals": 0,
        "thin_liquidity_alerts": 0,
        "pumpfun_activity": 0,
        "titles": [],
        "sources": set(),
    })

    for row in rows:
        signal_type = row.get("signal_type")
        entity = row.get("entity")
        title = row.get("title", "")
        source = row.get("source", "")

        token = normalize_token_from_pair(entity or "")
        if not token:
            continue

        bucket = features[token]

        if signal_type == "solana_raydium_pool_init":
            bucket["raydium_pool_inits"] += 1
        elif signal_type == "solana_liquidity_event":
            bucket["liquidity_events"] += 1
        elif signal_type == "solana_jupiter_swap":
            bucket["jupiter_swaps"] += 1
        elif signal_type == "solana_volume_velocity":
            bucket["velocity_signals"] += 1
        elif signal_type == "solana_mev_activity":
            bucket["mev_signals"] += 1
        elif signal_type == "solana_thin_liquidity_alert":
            bucket["thin_liquidity_alerts"] += 1
        elif signal_type == "solana_pumpfun_activity":
            bucket["pumpfun_activity"] += 1

        if title:
            bucket["titles"].append(title)

        if source:
            bucket["sources"].add(source)

    return features


# ---------------------------------------------------
# COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="solana_migration_detector",
    priority=1,
    tags=["solana", "migration", "raydium", "trading", "broadcast", "memecoin"],
    timeout=10,
)
def fetch_solana_migration_signals() -> List[Signal]:
    cfg = load_strategy_config()

    if not cfg.get("enabled", True):
        debug_log("disabled by config")
        return []

    lookback_minutes = int(cfg.get("lookback_minutes", 90))
    max_pairs_per_run = int(cfg.get("max_pairs_per_run", 200))

    rows = recent_rows(lookback_minutes)
    features = collect_migration_features(rows)

    signals: List[Signal] = []
    now = utc_now()

    candidate_count = 0

    for token, f in list(features.items())[:max_pairs_per_run]:
        has_migration = f["raydium_pool_inits"] > 0
        if not has_migration:
            continue

        candidate_count += 1

        # Base migration signal
        signals.append(
            Signal(
                timestamp=now,
                source="toknclaw",
                signal_type="solana_liquidity_migration",
                entity=token,
                title="Solana liquidity migration detected",
                summary=(
                    f"Token {token} appears to have migrated into active Raydium / "
                    f"tradable flow. raydium_pool_inits={f['raydium_pool_inits']}, "
                    f"liquidity_events={f['liquidity_events']}, "
                    f"jupiter_swaps={f['jupiter_swaps']}, "
                    f"velocity_signals={f['velocity_signals']}, "
                    f"mev_signals={f['mev_signals']}."
                ),
                confidence=0.86,
                sentiment_score=0.38,
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
                    f"Watch token {token} for post-migration price behavior, "
                    f"liquidity retention, and volume continuation."
                ),
                confidence=0.74,
                sentiment_score=0.20,
                raw_url=None,
            )
        )

        # Broadcast / culture hook
        if f["jupiter_swaps"] > 0 or f["velocity_signals"] > 0:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_meme_trend_candidate",
                    entity=token,
                    title="Solana meme trend candidate",
                    summary=(
                        f"Token {short_token(token)} shows migration + market activity. "
                        f"This is a candidate for ToknNews meme trend coverage, "
                        f"Bitsy humor review, and culture-anchor commentary."
                    ),
                    confidence=0.78,
                    sentiment_score=0.46,
                    raw_url=None,
                )
            )

        # Dip-buy heuristic
        dip_cfg = cfg.get("dip_buy", {})
        if (
            dip_cfg.get("enabled", True)
            and f["liquidity_events"] >= int(dip_cfg.get("min_liquidity_events", 1))
            and f["jupiter_swaps"] >= int(dip_cfg.get("min_jupiter_swaps", 1))
            and f["velocity_signals"] >= int(dip_cfg.get("min_velocity_signals", 1))
            and f["mev_signals"] <= int(dip_cfg.get("max_mev_signals", 8))
        ):
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_post_migration_dip_candidate",
                    entity=token,
                    title="Post-migration dip-buy candidate",
                    summary=(
                        f"Token {token} fits dip-buy migration profile: "
                        f"liquidity present, swaps active, velocity positive, "
                        f"and MEV pressure still manageable."
                    ),
                    confidence=float(dip_cfg.get("confidence", 0.83)),
                    sentiment_score=0.52,
                    raw_url=None,
                )
            )

        # Breakout-follow heuristic
        breakout_cfg = cfg.get("breakout_follow", {})
        if (
            breakout_cfg.get("enabled", True)
            and f["jupiter_swaps"] >= int(breakout_cfg.get("min_jupiter_swaps", 2))
            and f["velocity_signals"] >= int(breakout_cfg.get("min_velocity_signals", 1))
            and f["mev_signals"] <= int(breakout_cfg.get("max_mev_signals", 15))
        ):
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_post_migration_breakout_candidate",
                    entity=token,
                    title="Post-migration breakout follow candidate",
                    summary=(
                        f"Token {token} fits breakout-follow profile after migration. "
                        f"Consider continuation strategy rather than immediate fade."
                    ),
                    confidence=float(breakout_cfg.get("confidence", 0.79)),
                    sentiment_score=0.49,
                    raw_url=None,
                )
            )

        # Avoid / risk signal
        avoid_cfg = cfg.get("avoid_rules", {})
        if (
            avoid_cfg.get("enabled", True)
            and (
                f["mev_signals"] >= int(avoid_cfg.get("mev_spike_threshold", 20))
                or f["thin_liquidity_alerts"] >= int(avoid_cfg.get("thin_liquidity_threshold", 1))
            )
        ):
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_migration_risk_alert",
                    entity=token,
                    title="Migration risk alert",
                    summary=(
                        f"Token {token} shows migration, but execution risk is elevated. "
                        f"mev_signals={f['mev_signals']}, "
                        f"thin_liquidity_alerts={f['thin_liquidity_alerts']}."
                    ),
                    confidence=float(avoid_cfg.get("confidence", 0.84)),
                    sentiment_score=-0.44,
                    raw_url=None,
                )
            )

    debug_log(
        f"rows={len(rows)} tokens_scored={len(features)} "
        f"migration_candidates={candidate_count} signals_returned={len(signals)}"
    )

    return signals
