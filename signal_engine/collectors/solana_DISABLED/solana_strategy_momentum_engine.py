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
# MODULE: solana_strategy_momentum_engine
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
Solana Strategy Momentum Engine

Purpose
-------
Detect strict Solana momentum setups from the local signal lake.

This engine is designed to:
• detect acceleration, not just activity
• compare recent activity vs baseline activity
• require liquidity / routing support for entries
• penalize thin-liquidity or structurally weak tokens
• emit strict momentum entry / watch / avoid signals
• remain additive and OpenClaw-ready

Primary Input
-------------
/opt/toknclaw/data/signal_lake.json

Primary Output
--------------
Signals returned into snapshot pipeline

Agent Readiness
---------------
OpenClaw agents should tune:
• /opt/toknclaw/config/solana_strategy_momentum_engine.json

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

CONFIG_FILE = "solana_strategy_momentum_engine.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "lookback_hours": 12,
    "recent_window_minutes": 30,
    "baseline_window_minutes": 180,
    "max_tokens_scored": 120,
    "max_entry_signals": 6,
    "max_watch_signals": 8,
    "max_avoid_signals": 10,
    "excluded_entities": [
        "SOLANA",
        "SOLANA_ALPHA",
        "SOLANA_CULTURE",
        "SOLANA_MOMENTUM_STRATEGY",
        "SOLANA_DIP_STRATEGY",
        "SOLANA_MIGRATION_STRATEGY",
        "PUMPFUN",
        "PUMPFUN_ACTIVITY",
        "SOLANA_MINT_ACTIVITY",
        "SOLANA_VELOCITY",
        "JUPITER_SWAP_ACTIVITY",
        "RAYDIUM_POOL_ACTIVITY",
    ],
    "excluded_entity_prefixes": [
        "SOLANA_",
        "THEME_",
        "PUMPFUN_",
        "RAYDIUM_",
        "JUPITER_",
    ],
    "activity_weights": {
        "solana_jupiter_swap": 1.0,
        "solana_jupiter_swap_activity": 2.0,
        "solana_volume_velocity": 3.0,
        "solana_liquidity_depth": 1.6,
        "solana_liquidity_event": 1.4,
        "solana_raydium_pool_init": 2.2,
        "solana_raydium_pool_activity": 1.8,
        "solana_memecoin_trending": 1.2,
        "solana_memecoin_of_the_day": 1.8,
        "solana_alpha_entry_signal": 2.0,
        "solana_thin_liquidity_alert": -4.0,
        "solana_funny_name_candidate": 0.2,
        "solana_token_name_detected": 0.2,
        "solana_token_metadata_resolved": 0.2,
    },
    "entry_threshold": 11.5,
    "watch_threshold": 6.5,
    "avoid_threshold": -1.5,
    "min_recent_activity_score_for_entry": 6.0,
    "min_recent_activity_score_for_watch": 3.0,
    "min_acceleration_ratio_for_entry": 2.0,
    "min_acceleration_ratio_for_watch": 1.25,
    "require_liquidity_support_for_entry": True,
    "require_velocity_support_for_entry": True,
    "max_thin_liquidity_alerts_for_entry": 0,
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
        print(f"[SOLANA MOMENTUM] {message}")


def info_log(message: str) -> None:
    print(f"[SOLANA MOMENTUM] {message}")


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return deepcopy(DEFAULT_CONFIG)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)

    if not isinstance(merged.get("activity_weights"), dict):
        merged["activity_weights"] = deepcopy(DEFAULT_CONFIG["activity_weights"])

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

def build_entity_windows(rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    now = utc_now()
    recent_minutes = safe_int(cfg.get("recent_window_minutes", 30), 30)
    baseline_minutes = safe_int(cfg.get("baseline_window_minutes", 180), 180)
    recent_cutoff = now - timedelta(minutes=recent_minutes)
    baseline_cutoff = now - timedelta(minutes=baseline_minutes)

    activity_weights = cfg.get("activity_weights", {})

    entities: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        signal_type = clean_text(row.get("signal_type"))
        entity = clean_text(row.get("entity"))
        title = clean_text(row.get("title"))
        ts = parse_dt(row.get("timestamp"))

        if not signal_type or not entity or ts is None:
            continue

        if is_excluded_entity(entity, cfg):
            continue

        if ts < baseline_cutoff:
            continue

        state = entities.setdefault(
            entity,
            {
                "entity": entity,
                "recent_score": 0.0,
                "baseline_score": 0.0,
                "recent_count": 0,
                "baseline_count": 0,
                "recent_types": Counter(),
                "baseline_types": Counter(),
                "titles": [],
            },
        )

        weight = safe_float(activity_weights.get(signal_type, 0.0), 0.0)

        if ts >= recent_cutoff:
            state["recent_score"] += weight
            state["recent_count"] += 1
            state["recent_types"][signal_type] += 1
        else:
            state["baseline_score"] += weight
            state["baseline_count"] += 1
            state["baseline_types"][signal_type] += 1

        if title and len(state["titles"]) < 6:
            state["titles"].append(title)

    return entities


def finalize_scores(entities: Dict[str, Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for entity, state in entities.items():
        recent_score = safe_float(state.get("recent_score", 0.0), 0.0)
        baseline_score = safe_float(state.get("baseline_score", 0.0), 0.0)

        recent_types: Counter = state.get("recent_types", Counter())
        baseline_types: Counter = state.get("baseline_types", Counter())

        acceleration_ratio = (
            recent_score / baseline_score
            if baseline_score > 0
            else (recent_score if recent_score > 0 else 0.0)
        )

        liquidity_support = (
            recent_types.get("solana_liquidity_depth", 0)
            + recent_types.get("solana_liquidity_event", 0)
            + recent_types.get("solana_raydium_pool_init", 0)
            + recent_types.get("solana_raydium_pool_activity", 0)
        )

        velocity_support = (
            recent_types.get("solana_volume_velocity", 0)
            + recent_types.get("solana_jupiter_swap_activity", 0)
        )

        thin_liquidity_alerts = recent_types.get("solana_thin_liquidity_alert", 0)

        alpha_confirm = recent_types.get("solana_alpha_entry_signal", 0)
        trending_confirm = recent_types.get("solana_memecoin_trending", 0)
        memecoin_confirm = recent_types.get("solana_memecoin_of_the_day", 0)

        score = recent_score

        if acceleration_ratio >= 2.0:
            score += 2.0
        elif acceleration_ratio >= 1.5:
            score += 1.0

        if liquidity_support > 0:
            score += 1.2

        if velocity_support > 0:
            score += 1.2

        if alpha_confirm > 0:
            score += 1.4

        if trending_confirm > 0:
            score += 0.8

        if memecoin_confirm > 0:
            score += 1.0

        if thin_liquidity_alerts > 0:
            score -= thin_liquidity_alerts * 2.2

        reasons: List[str] = []

        if acceleration_ratio >= 2.0:
            reasons.append("hard_acceleration")
        elif acceleration_ratio >= 1.5:
            reasons.append("acceleration")

        if liquidity_support > 0:
            reasons.append(f"liquidity_support x{liquidity_support}")

        if velocity_support > 0:
            reasons.append(f"velocity_support x{velocity_support}")

        if alpha_confirm > 0:
            reasons.append("alpha_confirm")

        if trending_confirm > 0:
            reasons.append("trending_confirm")

        if memecoin_confirm > 0:
            reasons.append("memecoin_of_the_day")

        if thin_liquidity_alerts > 0:
            reasons.append(f"thin_liquidity x{thin_liquidity_alerts}")

        state["score"] = round(score, 4)
        state["acceleration_ratio"] = round(acceleration_ratio, 4)
        state["liquidity_support"] = liquidity_support
        state["velocity_support"] = velocity_support
        state["thin_liquidity_alerts"] = thin_liquidity_alerts
        state["reasons"] = reasons
        state["top_recent_types"] = recent_types.most_common(6)
        state["top_baseline_types"] = baseline_types.most_common(6)

        out.append(state)

    out.sort(
        key=lambda x: (
            safe_float(x.get("score", 0.0), 0.0),
            safe_float(x.get("acceleration_ratio", 0.0), 0.0),
            safe_int(x.get("recent_count", 0), 0),
        ),
        reverse=True,
    )

    return out


# ---------------------------------------------------
# DECISION BUILDERS
# ---------------------------------------------------

def build_summary_text(state: Dict[str, Any]) -> str:
    entity = clean_text(state.get("entity"))
    score = safe_float(state.get("score", 0.0), 0.0)
    recent_score = safe_float(state.get("recent_score", 0.0), 0.0)
    baseline_score = safe_float(state.get("baseline_score", 0.0), 0.0)
    acceleration_ratio = safe_float(state.get("acceleration_ratio", 0.0), 0.0)
    liquidity_support = safe_int(state.get("liquidity_support", 0), 0)
    velocity_support = safe_int(state.get("velocity_support", 0), 0)

    reasons = ", ".join(state.get("reasons", [])) or "none"

    return (
        f"{entity} momentum score={score:.2f} | "
        f"recent_score={recent_score:.2f} | baseline_score={baseline_score:.2f} | "
        f"acceleration={acceleration_ratio:.2f} | "
        f"liquidity_support={liquidity_support} | velocity_support={velocity_support} | "
        f"reasons={reasons}"
    )


def build_entry_signal(rank: int, state: Dict[str, Any]) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="solana_strategy_entry_momentum",
        entity=state["entity"],
        title=f"Solana momentum entry candidate #{rank}",
        summary=build_summary_text(state),
        confidence=0.84,
        sentiment_score=0.42,
        raw_url=None,
    )


def build_watch_signal(rank: int, state: Dict[str, Any]) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="solana_strategy_watch_momentum",
        entity=state["entity"],
        title=f"Solana momentum watch candidate #{rank}",
        summary=build_summary_text(state),
        confidence=0.76,
        sentiment_score=0.24,
        raw_url=None,
    )


def build_avoid_signal(state: Dict[str, Any]) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="solana_strategy_avoid_momentum",
        entity=state["entity"],
        title="Avoid Solana momentum setup",
        summary=build_summary_text(state),
        confidence=0.79,
        sentiment_score=-0.28,
        raw_url=None,
    )


def build_summary_signal(
    tokens_scored: int,
    entries: int,
    watch: int,
    avoid: int,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="solana_momentum_strategy_summary",
        entity="SOLANA_MOMENTUM_STRATEGY",
        title="Solana momentum strategy summary",
        summary=(
            f"Momentum strategy evaluated {tokens_scored} tokens | "
            f"entries={entries} | watch={watch} | avoid={avoid}"
        ),
        confidence=0.83,
        sentiment_score=0.17,
        raw_url=None,
    )


# ---------------------------------------------------
# PUBLIC COLLECTOR
# ---------------------------------------------------

def fetch_solana_strategy_momentum_signals() -> List[Signal]:
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

    entities = build_entity_windows(rows, cfg)
    scored_states = finalize_scores(entities, cfg)

    max_tokens_scored = safe_int(cfg.get("max_tokens_scored", 120), 120)
    scored_states = scored_states[:max_tokens_scored]

    entry_threshold = safe_float(cfg.get("entry_threshold", 11.5), 11.5)
    watch_threshold = safe_float(cfg.get("watch_threshold", 6.5), 6.5)
    avoid_threshold = safe_float(cfg.get("avoid_threshold", -1.5), -1.5)

    min_recent_entry = safe_float(cfg.get("min_recent_activity_score_for_entry", 6.0), 6.0)
    min_recent_watch = safe_float(cfg.get("min_recent_activity_score_for_watch", 3.0), 3.0)
    min_accel_entry = safe_float(cfg.get("min_acceleration_ratio_for_entry", 2.0), 2.0)
    min_accel_watch = safe_float(cfg.get("min_acceleration_ratio_for_watch", 1.25), 1.25)

    require_liquidity = bool(cfg.get("require_liquidity_support_for_entry", True))
    require_velocity = bool(cfg.get("require_velocity_support_for_entry", True))
    max_thin_for_entry = safe_int(cfg.get("max_thin_liquidity_alerts_for_entry", 0), 0)

    max_entries = safe_int(cfg.get("max_entry_signals", 6), 6)
    max_watch = safe_int(cfg.get("max_watch_signals", 8), 8)
    max_avoid = safe_int(cfg.get("max_avoid_signals", 10), 10)

    entries: List[Dict[str, Any]] = []
    watch: List[Dict[str, Any]] = []
    avoid: List[Dict[str, Any]] = []

    for state in scored_states:
        score = safe_float(state.get("score", 0.0), 0.0)
        recent_score = safe_float(state.get("recent_score", 0.0), 0.0)
        accel = safe_float(state.get("acceleration_ratio", 0.0), 0.0)
        liquidity_support = safe_int(state.get("liquidity_support", 0), 0)
        velocity_support = safe_int(state.get("velocity_support", 0), 0)
        thin_alerts = safe_int(state.get("thin_liquidity_alerts", 0), 0)

        entry_ok = True

        if score < entry_threshold:
            entry_ok = False

        if recent_score < min_recent_entry:
            entry_ok = False

        if accel < min_accel_entry:
            entry_ok = False

        if require_liquidity and liquidity_support <= 0:
            entry_ok = False

        if require_velocity and velocity_support <= 0:
            entry_ok = False

        if thin_alerts > max_thin_for_entry:
            entry_ok = False

        if entry_ok and len(entries) < max_entries:
            entries.append(state)
            continue

        watch_ok = True

        if score < watch_threshold:
            watch_ok = False

        if recent_score < min_recent_watch:
            watch_ok = False

        if accel < min_accel_watch:
            watch_ok = False

        if watch_ok and len(watch) < max_watch:
            watch.append(state)
            continue

        if score <= avoid_threshold and len(avoid) < max_avoid:
            avoid.append(state)

    signals.extend([build_entry_signal(i + 1, s) for i, s in enumerate(entries)])
    signals.extend([build_watch_signal(i + 1, s) for i, s in enumerate(watch)])
    signals.extend([build_avoid_signal(s) for s in avoid])
    signals.append(build_summary_signal(len(scored_states), len(entries), len(watch), len(avoid)))

    runtime = round(time.time() - started, 2)

    info_log(
        f"rows={len(rows)} "
        f"tokens_scored={len(scored_states)} "
        f"entries={len(entries)} "
        f"watch={len(watch)} "
        f"avoid={len(avoid)} "
        f"signals_returned={len(signals)} "
        f"runtime={runtime}s"
    )

    return signals


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    fetch_solana_strategy_momentum_signals()
