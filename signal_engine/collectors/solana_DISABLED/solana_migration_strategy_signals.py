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
# MODULE: solana_migration_strategy_signals
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
Solana Migration Strategy Signals

Purpose
-------
Convert migration detector outputs into explicit strategy-ready
signals that OpenClaw agents can act on, tune, and evaluate over time.

Responsibilities
----------------
• read recent migration-related signals from signal lake
• synthesize explicit entry / avoid / monitor signals
• provide agent-readable strategy framing
• support backtesting and later adaptive optimization

Signals Produced
----------------
• solana_strategy_entry_dip_buy
• solana_strategy_entry_breakout_follow
• solana_strategy_monitor_migration
• solana_strategy_avoid_migration

Author: TOKN Systems
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def debug_log(message: str) -> None:
    if DEBUG:
        print(f"[SOLANA MIGRATION STRATEGY] {message}")


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
    if isinstance(cfg, dict):
        return cfg
    return {"enabled": True, "lookback_minutes": 90}


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


# ---------------------------------------------------
# COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="solana_migration_strategy_signals",
    priority=1,
    tags=["solana", "strategy", "migration", "agents", "trading"],
    timeout=8,
)
def fetch_solana_migration_strategy_signals() -> List[Signal]:
    cfg = load_strategy_config()
    if not cfg.get("enabled", True):
        debug_log("disabled by config")
        return []

    lookback_minutes = int(cfg.get("lookback_minutes", 90))
    rows = recent_rows(lookback_minutes)

    by_token: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    tracked_types = {
        "solana_liquidity_migration",
        "solana_migration_watch",
        "solana_meme_trend_candidate",
        "solana_post_migration_dip_candidate",
        "solana_post_migration_breakout_candidate",
        "solana_migration_risk_alert",
    }

    for row in rows:
        st = row.get("signal_type")
        token = row.get("entity")
        if st not in tracked_types or not token:
            continue
        by_token[token][st] += 1

    signals: List[Signal] = []
    now = utc_now()

    for token, counts in by_token.items():
        if counts.get("solana_migration_watch", 0) > 0:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_strategy_monitor_migration",
                    entity=token,
                    title="Monitor migration candidate",
                    summary=(
                        f"Monitor token {token} for post-migration structure, "
                        f"liquidity retention, and reaction quality."
                    ),
                    confidence=0.71,
                    sentiment_score=0.18,
                    raw_url=None,
                )
            )

        if counts.get("solana_post_migration_dip_candidate", 0) > 0:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_strategy_entry_dip_buy",
                    entity=token,
                    title="Strategy entry: dip-buy candidate",
                    summary=(
                        f"OpenClaw agents may evaluate token {token} for a post-migration "
                        f"dip-buy entry using controlled risk and short holding windows."
                    ),
                    confidence=0.84,
                    sentiment_score=0.51,
                    raw_url=None,
                )
            )

        if counts.get("solana_post_migration_breakout_candidate", 0) > 0:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_strategy_entry_breakout_follow",
                    entity=token,
                    title="Strategy entry: breakout-follow candidate",
                    summary=(
                        f"OpenClaw agents may evaluate token {token} for continuation / "
                        f"breakout-follow behavior after migration and early market acceptance."
                    ),
                    confidence=0.79,
                    sentiment_score=0.46,
                    raw_url=None,
                )
            )

        if counts.get("solana_migration_risk_alert", 0) > 0:
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_strategy_avoid_migration",
                    entity=token,
                    title="Strategy avoid: migration risk elevated",
                    summary=(
                        f"Avoid or reduce risk on token {token}. "
                        f"Migration signal exists, but execution risk is elevated."
                    ),
                    confidence=0.85,
                    sentiment_score=-0.48,
                    raw_url=None,
                )
            )

    debug_log(
        f"rows={len(rows)} tracked_tokens={len(by_token)} signals_returned={len(signals)}"
    )

    return signals
