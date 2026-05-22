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
# MODULE: run_collectors
# PURPOSE: Runs ToknClaw collectors continuously based on per-collector schedules
#          and appends their outputs into the rolling signal lake.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

Responsibilities
----------------
• load environment
• read collector schedule config
• discover collectors
• run due collectors only
• append signals to signal lake
• emit runtime diagnostics
• support PM2 daemon execution
• minimize unnecessary API / RPC usage

Primary Output
--------------
/opt/toknclaw/data/signal_lake.json

Author: TOKN Systems
"""

from __future__ import annotations

from signal_engine import bootstrap
import os
import time
from datetime import datetime
from typing import Any, Dict

from dotenv import load_dotenv

from signal_engine.pipeline.collector_loader import discover_collectors
from signal_engine.runtime_config import load_config
from signal_engine.signal_lake import append_signals, load_signal_lake


# ---------------------------------------------------
# SAFE COLLECTOR IMPORTS (NO CHAINSTACK / SOLANA)
# ---------------------------------------------------

try:
    import signal_engine.collectors.coingecko_markets
    import signal_engine.collectors.binance_derivatives
    import signal_engine.collectors.cryptopanic
    import signal_engine.collectors.rss_news
    import signal_engine.collectors.rss_global_news
    import signal_engine.collectors.defillama_metrics
    import signal_engine.collectors.reddit_sentiment
    import signal_engine.collectors.stablecoin_liquidity
    import signal_engine.collectors.dexscreener_pairs
    import signal_engine.collectors.x_trending
    print("[COLLECTOR INIT] base collectors loaded")
except Exception as e:
    print(f"[COLLECTOR INIT] error: {e}")


# ---------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------

ENV_PATH = "/opt/toknclaw/signal_engine/.env"
load_dotenv(ENV_PATH)


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

LOOP_SLEEP_SEC = float(os.getenv("TOKN_COLLECTOR_LOOP_SLEEP_SEC", "2"))
MAX_SIGNAL_LAKE_SIZE = int(os.getenv("TOKN_SIGNAL_LAKE_MAX_SIGNALS", "5000"))


def utc_now_ts() -> float:
    return time.time()


def load_schedule() -> Dict[str, Any]:
    cfg = load_config("collector_schedule.json")
    return {
        "default_interval_sec": int(cfg.get("default_interval_sec", 300)),
        "collectors": dict(cfg.get("collectors", {})),
    }


def get_last_run_ts(collector_name: str, lake: Dict[str, Any]) -> float | None:
    row = lake.get("collector_runs", {}).get(collector_name)
    if not isinstance(row, dict):
        return None

    last_run_at = row.get("last_run_at")
    if not isinstance(last_run_at, str):
        return None

    try:
        return datetime.fromisoformat(last_run_at).timestamp()
    except Exception:
        return None


def is_due(collector_name: str, lake: Dict[str, Any], schedule_cfg: Dict[str, Any], now_ts: float) -> bool:
    default_interval = int(schedule_cfg.get("default_interval_sec", 300))
    per_collector = schedule_cfg.get("collectors", {})

    interval = int(per_collector.get(collector_name, default_interval))
    last_run_ts = get_last_run_ts(collector_name, lake)

    if last_run_ts is None:
        return True

    return (now_ts - last_run_ts) >= interval


# ---------------------------------------------------
# CORE LOOP
# ---------------------------------------------------

def run_once() -> None:
    schedule_cfg = load_schedule()
    collectors = discover_collectors()
    lake = load_signal_lake()

    print(f"[COLLECTOR DEBUG] discovered={len(collectors)}")

    now_ts = utc_now_ts()
    due = []

    for collector in collectors:
        name = collector["collector_name"]
        if is_due(name, lake, schedule_cfg, now_ts):
            due.append(collector)

    if not due:
        print("[COLLECTOR DAEMON] no collectors due")
        return

    print(f"[COLLECTOR DAEMON] due={len(due)} discovered={len(collectors)}")

    for collector in due:
        name = collector["collector_name"]
        func = collector["function"]

        start = time.time()

        try:
            raw = func()

            if raw is None:
                signals = []
            elif isinstance(raw, list):
                signals = raw
            elif isinstance(raw, tuple):
                signals = list(raw)
            elif isinstance(raw, dict):
                signals = [raw]
            else:
                try:
                    signals = list(raw)
                except Exception:
                    signals = []

            append_signals(
                new_signals=signals,
                collector_name=name,
                max_signals=MAX_SIGNAL_LAKE_SIZE,
            )

            runtime = round(time.time() - start, 2)
            print(f"[COLLECTOR DAEMON] {name} count={len(signals)} runtime={runtime}s")

        except Exception as e:
            runtime = round(time.time() - start, 2)
            print(f"[COLLECTOR DAEMON] {name} failed runtime={runtime}s error={e}")


def main() -> None:
    print("[COLLECTOR DAEMON] started")

    while True:
        try:
            run_once()
        except Exception as e:
            print(f"[COLLECTOR DAEMON] loop error: {e}")

        time.sleep(LOOP_SLEEP_SEC)


if __name__ == "__main__":
    main()
