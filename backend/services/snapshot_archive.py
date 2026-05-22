#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — SNAPSHOT ARCHIVE SERVICE
# ============================================================
#
# ████████╗ ██████╗ ██╗  ██╗███╗   ██╗ ██████╗██╗      █████╗ ██╗    ██╗
# ╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║██╔════╝██║     ██╔══██╗██║    ██║
#    ██║   ██║   ██║█████╔╝ ██╔██╗ ██║██║     ██║     ███████║██║ █╗ ██║
#    ██║   ██║   ██║██╔═██╗ ██║╚██╗██║██║     ██║     ██╔══██║██║███╗██║
#    ██║   ╚██████╔╝██║  ██╗██║ ╚████║╚██████╗███████╗██║  ██║╚███╔███╔╝
#    ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
#
# SYSTEM: ToknClaw Market Intelligence
# MODULE: snapshot_archive
# PURPOSE:
# - Persist time-series snapshots for frontend charts
# - Preserve real signal intelligence (entities)
# - Compute aggregate signal distribution correctly
# ============================================================
"""

import json
from pathlib import Path
from datetime import datetime

BASE = Path("/opt/toknclaw/data/snapshots")
ARCHIVE = BASE / "history.jsonl"

ARCHIVE.parent.mkdir(parents=True, exist_ok=True)


def build_snapshot(payload: dict):
    snapshot = payload.get("snapshot", payload)

    # 🔴 FORCE PORTFOLIO INTO SNAPSHOT
    if "portfolio" not in snapshot:
        paper = payload.get("paper") or payload.get("paper_trading_state") or {}
        snapshot["portfolio"] = paper.get("portfolio", {})

    trade_signals = snapshot.get("trade_signals", {})
    rows = trade_signals.get("rows", [])

    entities = {}

    # -----------------------------
    # ENTITY INTELLIGENCE (UNCHANGED)
    # -----------------------------
    for row in rows:
        entity = row.get("entity")
        if not entity:
            continue

        entities[entity] = {
            "direction": row.get("direction"),
            "confidence": row.get("confidence"),
            "score": row.get("score_breakdown", {}),
            "reasons": row.get("reasons", []),
        }

    # -----------------------------
    # 🔴 FIXED AGGREGATES (REAL COUNTS)
    # -----------------------------
    agg = {
        "strong_bullish": 0,
        "bullish": 0,
        "bearish": 0,
        "strong_bearish": 0,
        "no_trade": 0,
    }

    for row in rows:
        direction = str(row.get("direction", "")).lower()

        if "strong_bullish" in direction:
            agg["strong_bullish"] += 1
        elif "bullish" in direction:
            agg["bullish"] += 1
        elif "strong_bearish" in direction:
            agg["strong_bearish"] += 1
        elif "bearish" in direction:
            agg["bearish"] += 1
        else:
            agg["no_trade"] += 1

    # -----------------------------
    # PORTFOLIO (SOURCE OF TRUTH FIX)
    # -----------------------------
    import json
    from pathlib import Path

    paper_path = Path("/opt/toknclaw/data/paper_trading_state.json")

    try:
        paper = json.loads(paper_path.read_text())
        portfolio = paper.get("portfolio", {}) or {}
    except Exception:
        portfolio = {}

    equity = portfolio.get("equity_usd", 0)
    gross = portfolio.get("gross_exposure_usd", 0)
    unrealized = portfolio.get("unrealized_pnl_usd", 0)
    starting_cash = portfolio.get("starting_cash_usd", 0)

    # 🔴 CORRECT REALIZED PNL
    realized = equity - starting_cash if equity and starting_cash else 0

    if equity and equity > 0:
        deployed_pct = (gross / equity) * 100
        idle_cash_pct = max(0, 100 - deployed_pct)
        unrealized_pct = (unrealized / equity) * 100
        realized_pct = (realized / equity) * 100
    else:
        deployed_pct = 0
        idle_cash_pct = 100
        unrealized_pct = 0
        realized_pct = 0

    return {
        "ts": datetime.utcnow().isoformat(),

        # 🔴 REAL INTELLIGENCE
        "entities": entities,

        # 🔴 FIXED AGGREGATES
        "aggregates": agg,

        # 🔴 CONTEXT
        "signal_count": len(snapshot.get("signals", [])),

        # 🔴 CORRECT PORTFOLIO (NOW FROM PAPER STATE)
        "portfolio": {
            "equity": equity,
            "deployed_pct": deployed_pct,
            "idle_cash_pct": idle_cash_pct,
            "unrealized_pct": unrealized_pct,
            "realized_pct": realized_pct,
        }
    }

def append_snapshot(payload: dict):
    snap = build_snapshot(payload)

    try:
        with open(ARCHIVE, "a") as f:
            f.write(json.dumps(snap) + "\n")
    except Exception as e:
        print(f"[Snapshot Archive Error] {e}")
