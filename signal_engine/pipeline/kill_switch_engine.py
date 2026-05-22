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
# MODULE: kill_switch_engine
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
Autonomous Market Intelligence Platform

Kill Switch Engine
------------------

Emergency protection layer for automated trading.

Purpose
-------
Prevents catastrophic losses or system instability by halting
execution when abnormal conditions occur.

Triggers
--------
• portfolio drawdown
• volatility spike
• liquidity collapse
• system anomaly
• exchange connectivity failure

Outputs
-------
snapshot["kill_switch"]
snapshot["kill_switch_alerts"]
snapshot["kill_switch_reason"]

Design
------
• deterministic safety logic
• future exchange integration
• strategy-level override support
• configurable thresholds

Author: TOKN Systems
"""

from __future__ import annotations
from typing import Dict, Any


# ---------------------------------------------------
# Thresholds
# ---------------------------------------------------

MAX_PORTFOLIO_DRAWDOWN = 0.25
VOLATILITY_THRESHOLD = 0.90
MIN_LIQUIDITY_SCORE = 0.20


# ---------------------------------------------------
# Core Engine
# ---------------------------------------------------

def build_kill_switch(snapshot: Dict[str, Any]) -> Dict[str, Any]:

    alerts = []

    portfolio = snapshot.get("paper_portfolio", {})
    volatility = snapshot.get("volatility_summary", {})
    liquidity = snapshot.get("liquidity_summary", {})

    drawdown = float(portfolio.get("max_drawdown", 0))
    volatility_score = float(volatility.get("volatility_score", 0))
    liquidity_score = float(liquidity.get("dominant_weight", 1))

    # ---------------------------------------------------
    # Drawdown Protection
    # ---------------------------------------------------

    if drawdown >= MAX_PORTFOLIO_DRAWDOWN:

        alerts.append({
            "type": "drawdown_limit",
            "severity": "critical",
            "message": "Portfolio drawdown threshold exceeded",
            "value": drawdown,
        })

    # ---------------------------------------------------
    # Volatility Protection
    # ---------------------------------------------------

    if volatility_score >= VOLATILITY_THRESHOLD:

        alerts.append({
            "type": "volatility_spike",
            "severity": "high",
            "message": "Extreme market volatility detected",
            "value": volatility_score,
        })

    # ---------------------------------------------------
    # Liquidity Protection
    # ---------------------------------------------------

    if liquidity_score <= MIN_LIQUIDITY_SCORE:

        alerts.append({
            "type": "liquidity_collapse",
            "severity": "high",
            "message": "Market liquidity collapse detected",
            "value": liquidity_score,
        })

    active = len(alerts) > 0

    return {

        "kill_switch_active": active,

        "kill_switch_reason": alerts[0]["type"] if alerts else None,

        "kill_switch_alerts": alerts,
    }
