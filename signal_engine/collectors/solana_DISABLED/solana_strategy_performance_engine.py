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
# MODULE: solana_strategy_performance_engine
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
Strategy Performance Engine

Purpose
-------
Evaluates historical signal outcomes and produces performance metrics
per strategy and signal type.

This is the feedback loop for:
• allocator weighting
• OpenClaw agent tuning
• dashboard reporting

Inputs
------
/opt/toknclaw/data/signal_outcomes.json

Outputs
-------
Signals only (no file writes)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------
# BOOTSTRAP
# ---------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.signal import Signal


# ---------------------------------------------------
# PATH
# ---------------------------------------------------

OUTCOMES_PATH = Path("/opt/toknclaw/data/signal_outcomes.json")


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def read_outcomes() -> Dict[str, Any]:
    if not OUTCOMES_PATH.exists():
        return {}

    try:
        import json
        with open(OUTCOMES_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def safe_float(v: Any) -> float:
    try:
        return float(v)
    except:
        return 0.0


# ---------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------

def fetch_solana_strategy_performance_signals() -> List[Signal]:

    from datetime import datetime, timezone

    data = read_outcomes()
    records = data.get("records", {})

    if not isinstance(records, dict):
        return []

    stats: Dict[str, Dict[str, Any]] = {}

    for rec in records.values():

        if not isinstance(rec, dict):
            continue

        signal_type = str(rec.get("signal_type", "unknown"))
        maturity = rec.get("maturity_status", {})

        if not isinstance(maturity, dict):
            continue

        # -------------------------------------------
        # ONLY USE BEST AVAILABLE WINDOW (avoid spam)
        # -------------------------------------------

        best_return = None

        for window in maturity.values():

            if not isinstance(window, dict):
                continue

            if not window.get("matured"):
                continue

            if not window.get("price_available"):
                continue

            ret = window.get("forward_return_pct")

            if ret is None:
                continue

            ret = safe_float(ret)

            # take first valid (smallest timeframe bias)
            best_return = ret
            break

        if best_return is None:
            continue

        strat = stats.setdefault(signal_type, {
            "count": 0,
            "wins": 0,
            "losses": 0,
            "returns": [],
        })

        strat["count"] += 1
        strat["returns"].append(best_return)

        if best_return > 0:
            strat["wins"] += 1
        elif best_return < 0:
            strat["losses"] += 1

    signals: List[Signal] = []

    for strat_name, s in stats.items():

        count = s["count"]
        wins = s["wins"]
        losses = s["losses"]
        returns = s["returns"]

        # -------------------------------------------
        # MIN SAMPLE FILTER (CRITICAL)
        # -------------------------------------------

        if count < 5:
            continue

        win_rate = wins / max(1, (wins + losses))
        avg_return = sum(returns) / len(returns) if returns else 0.0

        # EXPECTANCY (more stable version)
        expectancy = (win_rate * avg_return) - ((1 - win_rate) * abs(avg_return))

        signals.append(
            Signal(
                timestamp=datetime.now(timezone.utc),
                source="toknclaw",
                signal_type="solana_strategy_performance",
                entity=strat_name,
                title=f"Strategy performance: {strat_name}",
                summary=(
                    f"trades={count} "
                    f"win_rate={round(win_rate,3)} "
                    f"avg_return={round(avg_return,4)} "
                    f"expectancy={round(expectancy,4)}"
                ),
                confidence=0.85,
                sentiment_score=expectancy,
                raw_url=None,
            )
        )

    print(
        f"[STRATEGY PERFORMANCE] strategies={len(signals)} "
        f"records_processed={len(records)}"
    )

    return signals

# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main():
    fetch_solana_strategy_performance_signals()


if __name__ == "__main__":
    main()
