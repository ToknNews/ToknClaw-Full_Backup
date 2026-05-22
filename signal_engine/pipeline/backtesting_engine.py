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
# MODULE: backtesting_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
ToknClaw Backtesting Engine

Evaluates historical predictive power of:

• trade signals
• quant factors
• narrative correlations
• market regimes
• entity flows
• cluster signals

Uses historical snapshot archive as the dataset.

Outputs
-------
snapshot["backtests"]
snapshot["backtest_summary"]
snapshot["backtest_alerts"]
snapshot["backtest_endpoints"]

Future Ready
------------
• strategy simulation
• walk-forward optimization
• portfolio simulation
• multi-factor signal evaluation
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Any

SNAPSHOT_DIR = Path("/opt/toknclaw/data/snapshots")

LOOKBACK = 96   # 96 snapshots ≈ ~8 hours at 5m cadence


# ------------------------------------------------
# helpers
# ------------------------------------------------

def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except:
        return d


def _load_history(limit=LOOKBACK):

    files = sorted(
        SNAPSHOT_DIR.glob("snapshot_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )[:limit]

    history = []

    for p in reversed(files):
        try:
            history.append(json.loads(p.read_text()))
        except:
            continue

    return history


# ------------------------------------------------
# signal extraction
# ------------------------------------------------

def _extract_trade_signals(snapshot):

    signals = []

    for s in _safe_list(snapshot.get("trade_signals")):

        signals.append({
            "entity": s.get("entity"),
            "direction": s.get("direction"),
            "confidence": _safe_float(s.get("confidence")),
        })

    return signals


def _extract_quant_factors(snapshot):

    factors = []

    for q in _safe_list(snapshot.get("quant_factors")):

        factors.append({
            "entity": q.get("entity"),
            "factor": q.get("composite_factor"),
            "regime": q.get("regime_bucket"),
        })

    return factors


def _extract_narratives(snapshot):

    narratives = []

    for n in _safe_list(snapshot.get("narratives")):

        narratives.append({
            "type": n.get("narrative_type"),
            "entities": _safe_list(n.get("entities")),
            "confidence": _safe_float(n.get("confidence")),
        })

    return narratives


# ------------------------------------------------
# price proxy (placeholder)
# ------------------------------------------------

def _price_proxy(snapshot, entity):

    for cluster in _safe_list(snapshot.get("clusters")):

        if cluster.get("entity") == entity:
            return _safe_float(cluster.get("total_value_usd"))

    return None


# ------------------------------------------------
# signal evaluation
# ------------------------------------------------

def _evaluate_trade_signal(entity, direction, history):

    start = None
    end = None

    for snap in history:

        p = _price_proxy(snap, entity)

        if p is None:
            continue

        if start is None:
            start = p

        end = p

    if start is None or end is None:
        return None

    change = (end - start) / start

    if direction == "bullish":
        success = change > 0

    elif direction == "bearish":
        success = change < 0

    else:
        success = abs(change) < 0.02

    return {
        "entity": entity,
        "direction": direction,
        "return": round(change, 4),
        "success": success,
    }


# ------------------------------------------------
# trade signal backtest
# ------------------------------------------------

def _backtest_trade_signals(history):

    latest = history[-1]

    signals = _extract_trade_signals(latest)

    results = []

    for s in signals:

        r = _evaluate_trade_signal(
            s["entity"],
            s["direction"],
            history
        )

        if r:
            results.append(r)

    return results


# ------------------------------------------------
# quant factor validation
# ------------------------------------------------

def _backtest_quant_factors(history):

    latest = history[-1]

    factors = _extract_quant_factors(latest)

    results = []

    for f in factors:

        entity = f["entity"]

        start = None
        end = None

        for snap in history:

            p = _price_proxy(snap, entity)

            if p is None:
                continue

            if start is None:
                start = p

            end = p

        if start and end:

            change = (end - start) / start

            results.append({
                "entity": entity,
                "factor": f["factor"],
                "return": round(change, 4),
            })

    return results


# ------------------------------------------------
# narrative predictive power
# ------------------------------------------------

def _backtest_narratives(history):

    latest = history[-1]

    narratives = _extract_narratives(latest)

    results = []

    for n in narratives:

        for entity in n["entities"]:

            start = None
            end = None

            for snap in history:

                p = _price_proxy(snap, entity)

                if p is None:
                    continue

                if start is None:
                    start = p

                end = p

            if start and end:

                change = (end - start) / start

                results.append({
                    "entity": entity,
                    "narrative": n["type"],
                    "return": round(change, 4),
                })

    return results


# ------------------------------------------------
# metrics
# ------------------------------------------------

def _compute_metrics(trade_results):

    if not trade_results:
        return {}

    wins = sum(1 for r in trade_results if r["success"])
    total = len(trade_results)

    hit_rate = wins / total

    avg_return = sum(r["return"] for r in trade_results) / total

    return {
        "trade_count": total,
        "hit_rate": round(hit_rate, 3),
        "avg_return": round(avg_return, 4),
    }


# ------------------------------------------------
# alerts
# ------------------------------------------------

def _generate_alerts(metrics):

    alerts = []

    hit_rate = _safe_float(metrics.get("hit_rate"))

    if hit_rate > 0.65:

        alerts.append({
            "type": "high_signal_accuracy",
            "severity": "medium",
            "title": "Trading signals performing above historical baseline"
        })

    if hit_rate < 0.35:

        alerts.append({
            "type": "signal_decay",
            "severity": "high",
            "title": "Signal hit rate deteriorating"
        })

    return alerts


# ------------------------------------------------
# public engine
# ------------------------------------------------

def build_backtests(snapshot):

    history = _load_history()

    if len(history) < 5:
        return {}

    trade_results = _backtest_trade_signals(history)

    factor_results = _backtest_quant_factors(history)

    narrative_results = _backtest_narratives(history)

    metrics = _compute_metrics(trade_results)

    alerts = _generate_alerts(metrics)

    return {

        "trades": trade_results,
        "quant_factors": factor_results,
        "narratives": narrative_results,

        "metrics": metrics,
        "alerts": alerts,

        "endpoints": {
            "trade_backtests": "/api/toknclaw/backtests/trades",
            "factor_backtests": "/api/toknclaw/backtests/factors",
            "narrative_backtests": "/api/toknclaw/backtests/narratives"
        }

    }
