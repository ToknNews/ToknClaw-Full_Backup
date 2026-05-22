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
# MODULE: solana_strategy_migration_engine
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
Solana Strategy Migration Engine

Purpose
-------
Evaluates post-launch Solana memecoin rotation and migration quality
using existing signal lake evidence.

This module is designed to detect:
• Pump.fun launches that appear to be rotating into tradable structure
• tokens gaining Raydium / liquidity confirmation
• post-launch continuation setups
• weak or shallow migration setups to avoid

Responsibilities
----------------
• read local signal lake only
• score tokens using recent migration-related evidence
• emit entry, watch, avoid, and summary strategy signals
• remain additive to current ToknClaw pipeline
• support OpenClaw agent tuning through config

Strategy Logic
--------------
Migration score is derived from recent evidence such as:
• pumpfun launch signals
• pumpfun activity density
• raydium pool initialization
• raydium pool activity
• jupiter swap activity
• liquidity depth
• thin liquidity warnings
• alpha / narrative / leaderboard confirmation

Primary Input
-------------
/opt/toknclaw/data/signal_lake.json

Primary Output
--------------
Signals returned into snapshot pipeline

Agent Readiness
---------------
OpenClaw agents should tune:
• /opt/toknclaw/config/solana_strategy_migration_engine.json

Author: TOKN Systems
"""

from __future__ import annotations

import sys
import time
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

PROJECT_ROOT = Path("/opt/toknclaw/signal_engine")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

from models.signal import Signal
from runtime_config import load_config
from signal_lake import load_signal_lake


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

CONFIG_FILE = "solana_strategy_migration_engine.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "lookback_hours": 12,
    "max_tokens_scored": 150,
    "max_entry_signals": 6,
    "max_watch_signals": 10,
    "max_avoid_signals": 10,
    "entry_score_threshold": 10.0,
    "watch_score_threshold": 5.5,
    "avoid_score_threshold": -2.0,
    "min_signal_count_for_entry": 4,
    "excluded_entity_prefixes": [
        "SOLANA_",
        "PUMPFUN_",
        "THEME_",
        "RAYDIUM_",
        "JUPITER_",
    ],
    "excluded_entities": [
        "SOLANA",
        "PUMPFUN",
        "PUMPFUN_ACTIVITY",
        "SOLANA_ALPHA",
        "SOLANA_CULTURE",
        "SOLANA_MINT_ACTIVITY",
        "RAYDIUM_POOL_ACTIVITY",
        "JUPITER_SWAP_ACTIVITY",
        "SOLANA_VELOCITY",
        "SOLANA_DIP_STRATEGY",
        "SOLANA_MOMENTUM_STRATEGY",
    ],
    "weights": {
        "solana_pumpfun_launch": 2.4,
        "solana_pumpfun_activity": 1.1,
        "solana_raydium_pool_init": 3.0,
        "solana_raydium_pool_activity": 1.8,
        "solana_liquidity_event": 1.6,
        "solana_liquidity_depth": 1.8,
        "solana_jupiter_swap": 1.0,
        "solana_jupiter_swap_activity": 1.5,
        "solana_volume_velocity": 1.4,
        "solana_velocity_summary": 0.6,
        "solana_alpha_entry_signal": 2.0,
        "solana_memecoin_trending": 1.5,
        "solana_memecoin_of_the_day": 2.2,
        "solana_memecoin_narrative_candidate": 1.1,
        "solana_bitsy_watchlist": 0.4,
        "solana_token_name_detected": 0.2,
        "solana_token_symbol_detected": 0.2,
        "solana_token_metadata_resolved": 0.3,
        "solana_funny_name_candidate": 0.2,
        "solana_thin_liquidity_alert": -3.0,
        "solana_strategy_avoid_dip_buy": -1.0,
        "solana_strategy_avoid_momentum": -1.4,
    },
}


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def parse_dt(value: Any) -> Optional[datetime]:
    text = clean_text(value)
    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)

        return dt.astimezone(UTC)
    except Exception:
        return None


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[SOLANA MIGRATION STRATEGY] {message}")


def info_log(message: str) -> None:
    print(f"[SOLANA MIGRATION STRATEGY] {message}")


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return deepcopy(DEFAULT_CONFIG)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)

    if not isinstance(merged.get("weights"), dict):
        merged["weights"] = deepcopy(DEFAULT_CONFIG["weights"])

    return merged


def object_signals_only(rows: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in rows:
        if isinstance(row, dict):
            out.append(row)
            continue

        if hasattr(row, "__dict__"):
            try:
                out.append(dict(row.__dict__))
            except Exception:
                continue

    return out


def recent_rows(rows: List[Dict[str, Any]], hours: int) -> List[Dict[str, Any]]:
    cutoff = utc_now() - timedelta(hours=hours)
    out: List[Dict[str, Any]] = []

    for row in rows:
        ts = parse_dt(row.get("timestamp"))
        if ts is None:
            continue

        if ts >= cutoff:
            out.append(row)

    return out


def is_excluded_entity(entity: str, cfg: Dict[str, Any]) -> bool:
    entity = clean_text(entity)
    if not entity:
        return True

    if entity in set(cfg.get("excluded_entities", [])):
        return True

    for prefix in cfg.get("excluded_entity_prefixes", []):
        if entity.upper().startswith(clean_text(prefix).upper()):
            return True

    if "/" in entity:
        return True

    if len(entity) < 20:
        return True

    return False


# ---------------------------------------------------
# SCORING
# ---------------------------------------------------

def score_tokens(rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    weights = cfg.get("weights", {})

    scores: Dict[str, float] = defaultdict(float)
    counts: Dict[str, int] = defaultdict(int)
    type_counts: Dict[str, Counter] = defaultdict(Counter)
    reasons: Dict[str, List[str]] = defaultdict(list)

    for row in rows:
        signal_type = clean_text(row.get("signal_type"))
        entity = clean_text(row.get("entity"))

        if not signal_type or not entity:
            continue

        if is_excluded_entity(entity, cfg):
            continue

        weight = safe_float(weights.get(signal_type, 0.0), 0.0)

        scores[entity] += weight
        counts[entity] += 1
        type_counts[entity][signal_type] += 1

    results: Dict[str, Dict[str, Any]] = {}

    for entity, score in scores.items():
        top_types = type_counts[entity].most_common(6)

        token_reasons: List[str] = []

        for signal_type, count in top_types:
            token_reasons.append(f"{signal_type} x{count}")

        # structure checks
        has_launch = type_counts[entity]["solana_pumpfun_launch"] > 0
        has_raydium = (
            type_counts[entity]["solana_raydium_pool_init"] > 0
            or type_counts[entity]["solana_raydium_pool_activity"] > 0
        )
        has_swaps = (
            type_counts[entity]["solana_jupiter_swap"] > 0
            or type_counts[entity]["solana_jupiter_swap_activity"] > 0
        )
        has_depth = type_counts[entity]["solana_liquidity_depth"] > 0
        has_thin_liquidity = type_counts[entity]["solana_thin_liquidity_alert"] > 0
        has_alpha = type_counts[entity]["solana_alpha_entry_signal"] > 0

        # migration bonus / penalties
        adjusted_score = score

        if has_launch and has_raydium:
            adjusted_score += 2.5
            token_reasons.append("launch_to_raydium")

        if has_raydium and has_swaps:
            adjusted_score += 1.5
            token_reasons.append("swap_confirmation")

        if has_depth:
            adjusted_score += 1.0
            token_reasons.append("liquidity_depth")

        if has_alpha:
            adjusted_score += 1.0
            token_reasons.append("alpha_confirmation")

        if has_thin_liquidity:
            adjusted_score -= 2.0
            token_reasons.append("thin_liquidity_penalty")

        results[entity] = {
            "entity": entity,
            "score": round(adjusted_score, 4),
            "signal_count": counts[entity],
            "top_types": top_types,
            "reasons": token_reasons,
            "has_launch": has_launch,
            "has_raydium": has_raydium,
            "has_swaps": has_swaps,
            "has_depth": has_depth,
            "has_alpha": has_alpha,
            "has_thin_liquidity": has_thin_liquidity,
        }

    return results


# ---------------------------------------------------
# SIGNAL BUILDERS
# ---------------------------------------------------

def build_entry_signal(rank: int, row: Dict[str, Any]) -> Signal:
    entity = row["entity"]
    score = row["score"]
    reasons = ", ".join(row["reasons"][:5])

    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="solana_strategy_entry_migration",
        entity=entity,
        title=f"Solana migration entry candidate #{rank}",
        summary=f"{entity} qualifies for post-launch migration entry | score={score:.2f} | reasons={reasons}",
        confidence=0.85,
        sentiment_score=0.39,
        raw_url=None,
    )


def build_watch_signal(rank: int, row: Dict[str, Any]) -> Signal:
    entity = row["entity"]
    score = row["score"]
    reasons = ", ".join(row["reasons"][:5])

    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="solana_strategy_watch_migration",
        entity=entity,
        title=f"Solana migration watch candidate #{rank}",
        summary=f"{entity} is on migration watchlist | score={score:.2f} | reasons={reasons}",
        confidence=0.77,
        sentiment_score=0.24,
        raw_url=None,
    )


def build_avoid_signal(row: Dict[str, Any]) -> Signal:
    entity = row["entity"]
    score = row["score"]
    reasons = ", ".join(row["reasons"][:5])

    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="solana_strategy_avoid_migration",
        entity=entity,
        title="Avoid Solana migration setup",
        summary=f"{entity} scores poorly for migration continuation | score={score:.2f} | reasons={reasons}",
        confidence=0.79,
        sentiment_score=-0.27,
        raw_url=None,
    )


def build_summary_signal(
    total_scored: int,
    entry_count: int,
    watch_count: int,
    avoid_count: int,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="solana_migration_strategy_summary",
        entity="SOLANA_MIGRATION_STRATEGY",
        title="Solana migration strategy summary",
        summary=(
            f"Migration strategy evaluated {total_scored} tokens | "
            f"entries={entry_count} | watch={watch_count} | avoid={avoid_count}"
        ),
        confidence=0.82,
        sentiment_score=0.14,
        raw_url=None,
    )


# ---------------------------------------------------
# PUBLIC COLLECTOR
# ---------------------------------------------------

def fetch_solana_strategy_migration_signals() -> List[Signal]:
    started = time.time()
    cfg = load_engine_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        info_log("disabled by config")
        return signals

    lake = load_signal_lake()
    raw_rows = lake.get("signals", [])
    rows = object_signals_only(raw_rows)

    lookback_hours = safe_int(cfg.get("lookback_hours", 12), 12)
    rows = recent_rows(rows, lookback_hours)

    scored = score_tokens(rows, cfg)

    ranked = sorted(
        scored.values(),
        key=lambda x: (x["score"], x["signal_count"]),
        reverse=True,
    )

    max_tokens_scored = safe_int(cfg.get("max_tokens_scored", 150), 150)
    ranked = ranked[:max_tokens_scored]

    entry_threshold = safe_float(cfg.get("entry_score_threshold", 10.0), 10.0)
    watch_threshold = safe_float(cfg.get("watch_score_threshold", 5.5), 5.5)
    avoid_threshold = safe_float(cfg.get("avoid_score_threshold", -2.0), -2.0)
    min_signal_count_for_entry = safe_int(cfg.get("min_signal_count_for_entry", 4), 4)

    max_entry_signals = safe_int(cfg.get("max_entry_signals", 6), 6)
    max_watch_signals = safe_int(cfg.get("max_watch_signals", 10), 10)
    max_avoid_signals = safe_int(cfg.get("max_avoid_signals", 10), 10)

    entry_rows: List[Dict[str, Any]] = []
    watch_rows: List[Dict[str, Any]] = []
    avoid_rows: List[Dict[str, Any]] = []

    for row in ranked:
        score = row["score"]

        qualifies_entry = (
            score >= entry_threshold
            and row["signal_count"] >= min_signal_count_for_entry
            and row["has_launch"]
            and row["has_raydium"]
            and (row["has_swaps"] or row["has_depth"])
            and not row["has_thin_liquidity"]
        )

        qualifies_watch = (
            score >= watch_threshold
            and row["has_launch"]
            and (row["has_raydium"] or row["has_swaps"])
        )

        qualifies_avoid = (
            score <= avoid_threshold
            or row["has_thin_liquidity"]
        )

        if qualifies_entry and len(entry_rows) < max_entry_signals:
            entry_rows.append(row)
            continue

        if qualifies_watch and len(watch_rows) < max_watch_signals:
            watch_rows.append(row)
            continue

        if qualifies_avoid and len(avoid_rows) < max_avoid_signals:
            avoid_rows.append(row)

    entry_signals = [
        build_entry_signal(rank=i + 1, row=row)
        for i, row in enumerate(entry_rows)
    ]

    watch_signals = [
        build_watch_signal(rank=i + 1, row=row)
        for i, row in enumerate(watch_rows)
    ]

    avoid_signals = [
        build_avoid_signal(row=row)
        for row in avoid_rows
    ]

    signals.extend(entry_signals)
    signals.extend(watch_signals)
    signals.extend(avoid_signals)

    signals.append(
        build_summary_signal(
            total_scored=len(ranked),
            entry_count=len(entry_signals),
            watch_count=len(watch_signals),
            avoid_count=len(avoid_signals),
        )
    )

    runtime = round(time.time() - started, 2)

    info_log(
        f"rows={len(rows)} "
        f"tokens_scored={len(ranked)} "
        f"entries={len(entry_signals)} "
        f"watch={len(watch_signals)} "
        f"avoid={len(avoid_signals)} "
        f"signals_returned={len(signals)} "
        f"runtime={runtime}s"
    )

    return signals


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    fetch_solana_strategy_migration_signals()
