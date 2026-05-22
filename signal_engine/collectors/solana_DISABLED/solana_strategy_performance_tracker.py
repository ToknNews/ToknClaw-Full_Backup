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
# MODULE: solana_strategy_performance_tracker
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
Solana Strategy Performance Tracker

Purpose
-------
Evaluates historical performance of strategy signals using labeled outcomes.

This module transforms:
• raw signals
• outcome labels
• price returns

Into:
• strategy win rates
• average returns
• reliability scores
• agent-ready performance metrics

Feeds
-----
• OpenClaw agent tuning
• strategy optimizer engine
• risk weighting system
• ToknNews broadcast framing

Primary Inputs
--------------
/opt/toknclaw/data/signal_outcomes.json

Primary Outputs
---------------
/opt/toknclaw/data/strategy_performance.json

Agent Readiness
---------------
OpenClaw agents can tune:
• min_sample_size
• scoring weights
• strategy inclusion thresholds

Author: TOKN Systems
"""

from __future__ import annotations

import json
import time
import sys
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP (HARD FIX)
# ---------------------------------------------------


PROJECT_ROOT = Path("/opt/toknclaw/signal_engine")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.signal import Signal

# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

OUTCOMES_PATH = Path("/opt/toknclaw/data/signal_outcomes.json")
OUTPUT_PATH = Path("/opt/toknclaw/data/strategy_performance.json")
TMP_PATH = Path("/opt/toknclaw/data/strategy_performance.tmp")


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

MIN_SAMPLE_SIZE = 5
WIN_WEIGHT = 1.0
RETURN_WEIGHT = 0.5


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def load_outcomes() -> Dict[str, Any]:
    if not OUTCOMES_PATH.exists():
        return {}

    try:
        with open(OUTCOMES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_output(payload: Dict[str, Any]) -> None:
    with open(TMP_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    TMP_PATH.replace(OUTPUT_PATH)


def safe_float(v):
    try:
        return float(v)
    except:
        return None


# ---------------------------------------------------
# CORE AGGREGATION
# ---------------------------------------------------

def aggregate_performance(records: Dict[str, Any]) -> Dict[str, Any]:
    strategies: Dict[str, Dict[str, Any]] = {}

    for record in records.values():

        signal_type = record.get("signal_type")
        windows = record.get("windows", {})

        if not signal_type or not isinstance(windows, dict):
            continue

        strat = strategies.setdefault(signal_type, {
            "signal_type": signal_type,
            "count": 0,
            "wins": 0,
            "losses": 0,
            "returns": [],
        })

        for w in windows.values():

            label = w.get("label")
            ret = safe_float(w.get("return_pct"))

            if ret is None:
                continue

            strat["count"] += 1
            strat["returns"].append(ret)

            if label == "win":
                strat["wins"] += 1
            elif label == "loss":
                strat["losses"] += 1

    # finalize metrics
    results = {}

    for k, v in strategies.items():

        count = v["count"]
        if count < MIN_SAMPLE_SIZE:
            continue

        avg_return = sum(v["returns"]) / len(v["returns"]) if v["returns"] else 0
        win_rate = v["wins"] / count if count else 0

        score = (win_rate * WIN_WEIGHT) + (avg_return * RETURN_WEIGHT / 100)

        results[k] = {
            "signal_type": k,
            "sample_size": count,
            "win_rate": round(win_rate, 4),
            "avg_return_pct": round(avg_return, 4),
            "score": round(score, 4),
        }

    return results


# ---------------------------------------------------
# SIGNAL GENERATION
# ---------------------------------------------------

def build_performance_signals(results: Dict[str, Any]) -> List[Signal]:
    signals: List[Signal] = []

    ranked = sorted(results.values(), key=lambda x: x["score"], reverse=True)

    for r in ranked[:5]:

        signals.append(
            Signal(
                timestamp=None,
                source="toknclaw",
                signal_type="strategy_top_performer",
                entity=r["signal_type"],
                title="Top performing strategy",
                summary=f"{r['signal_type']} | win_rate={r['win_rate']} | avg_return={r['avg_return_pct']}%",
                confidence=0.9,
                sentiment_score=0.5,
                raw_url=None,
            )
        )

    for r in ranked[-5:]:

        signals.append(
            Signal(
                timestamp=None,
                source="toknclaw",
                signal_type="strategy_underperformer",
                entity=r["signal_type"],
                title="Underperforming strategy",
                summary=f"{r['signal_type']} | win_rate={r['win_rate']} | avg_return={r['avg_return_pct']}%",
                confidence=0.85,
                sentiment_score=-0.4,
                raw_url=None,
            )
        )

    return signals


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

def run_tracker() -> List[Signal]:

    start = time.time()

    data = load_outcomes()
    records = data.get("records", {})

    results = aggregate_performance(records)

    payload = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategies": results,
    }

    save_output(payload)

    signals = build_performance_signals(results)

    runtime = round(time.time() - start, 2)

    print(
        f"[STRATEGY PERFORMANCE] "
        f"strategies={len(results)} "
        f"signals={len(signals)} "
        f"runtime={runtime}s"
    )

    return signals


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    run_tracker()
