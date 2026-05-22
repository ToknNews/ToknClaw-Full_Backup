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
# MODULE: strategy_performance_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
strategy_performance_engine.py

ToknClaw Strategy Performance Engine

Purpose
-------
Evaluate strategy effectiveness over time using:
- strategy simulations
- backtests
- trade signals
- regime alignment
- risk metrics

Outputs
-------
snapshot["strategy_performance"]
snapshot["strategy_performance_summary"]
snapshot["strategy_performance_alerts"]
snapshot["strategy_performance_endpoints"]

Future Extensions
-----------------
• live trading performance
• Sharpe / Sortino ratios
• drawdown curves
• strategy retirement
• reinforcement learning strategy weighting
"""

from __future__ import annotations
from typing import Dict, List, Any


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# -------------------------------------------------------
# Sharpe proxy
# -------------------------------------------------------

def _sharpe_proxy(avg_return: float, win_rate: float):

    if avg_return == 0:
        return 0.0

    return round((avg_return * win_rate) * 4.0, 3)


# -------------------------------------------------------
# Drawdown proxy
# -------------------------------------------------------

def _drawdown_proxy(losses: float, trades: float):

    if trades == 0:
        return 0.0

    ratio = losses / trades

    return round(_clamp(ratio), 3)


# -------------------------------------------------------
# Strategy scoring
# -------------------------------------------------------

def _score_strategy(row):

    win_rate = _safe_float(row.get("hit_rate"))
    avg_return = _safe_float(row.get("avg_pnl_proxy"))
    trades = _safe_float(row.get("trade_count"))

    sharpe = _sharpe_proxy(avg_return, win_rate)

    trade_factor = min(trades / 10.0, 1.0)

    score = (
        win_rate * 0.45
        + sharpe * 0.35
        + trade_factor * 0.20
    )

    return round(score, 3), sharpe


# -------------------------------------------------------
# Performance computation
# -------------------------------------------------------

def _compute_rows(snapshot):

    strategies = _safe_list(
        _safe_dict(snapshot.get("strategy_simulation")).get("strategies")
    )

    rows = []

    for s in strategies:

        s = _safe_dict(s)

        wins = _safe_float(s.get("wins"))
        losses = _safe_float(s.get("losses"))
        trades = _safe_float(s.get("trade_count"))

        score, sharpe = _score_strategy(s)

        row = {
            "strategy_id": s.get("strategy_id"),
            "strategy_name": s.get("strategy_name"),
            "mode": s.get("mode"),
            "trade_count": trades,
            "wins": wins,
            "losses": losses,
            "hit_rate": _safe_float(s.get("hit_rate")),
            "avg_pnl_proxy": _safe_float(s.get("avg_pnl_proxy")),
            "sharpe_proxy": sharpe,
            "drawdown_proxy": _drawdown_proxy(losses, trades),
            "performance_score": score
        }

        rows.append(row)

    rows.sort(
        key=lambda x: (
            x.get("performance_score", 0),
            x.get("hit_rate", 0),
            x.get("trade_count", 0)
        ),
        reverse=True
    )

    return rows


# -------------------------------------------------------
# Alerts
# -------------------------------------------------------

def _build_alerts(rows):

    alerts = []

    for r in rows:

        score = _safe_float(r.get("performance_score"))
        win = _safe_float(r.get("hit_rate"))

        if score > 0.8 and win > 0.65:

            alerts.append({
                "type": "strategy_outperforming",
                "severity": "medium",
                "strategy_id": r.get("strategy_id"),
                "title": f'{r.get("strategy_name")} showing strong performance'
            })

        if score < 0.35 and r.get("trade_count", 0) > 3:

            alerts.append({
                "type": "strategy_underperforming",
                "severity": "high",
                "strategy_id": r.get("strategy_id"),
                "title": f'{r.get("strategy_name")} deteriorating'
            })

    return alerts[:20]


# -------------------------------------------------------
# Summary
# -------------------------------------------------------

def _build_summary(rows, alerts):

    if not rows:

        return {
            "strategy_count": 0,
            "top_strategy": None,
            "top_score": 0,
            "alert_count": len(alerts)
        }

    top = rows[0]

    return {
        "strategy_count": len(rows),
        "top_strategy": top.get("strategy_id"),
        "top_score": top.get("performance_score"),
        "top_hit_rate": top.get("hit_rate"),
        "top_sharpe_proxy": top.get("sharpe_proxy"),
        "alert_count": len(alerts)
    }


# -------------------------------------------------------
# Endpoints
# -------------------------------------------------------

def _endpoint_manifest():

    return {
        "strategy_performance": "/api/toknclaw/strategy-performance",
        "strategy_performance_summary": "/api/toknclaw/strategy-performance/summary",
        "strategy_performance_alerts": "/api/toknclaw/strategy-performance/alerts"
    }


# -------------------------------------------------------
# Public engine
# -------------------------------------------------------

def build_strategy_performance(snapshot: Dict[str, Any]):

    snapshot = _safe_dict(snapshot)

    rows = _compute_rows(snapshot)

    alerts = _build_alerts(rows)

    summary = _build_summary(rows, alerts)

    return {
        "rows": rows,
        "summary": summary,
        "alerts": alerts,
        "endpoints": _endpoint_manifest()
    }
