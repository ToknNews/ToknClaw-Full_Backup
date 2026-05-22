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
# MODULE: macro_liquidity_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
macro_liquidity_engine.py

ToknClaw Macro Liquidity Engine

Purpose
-------
Detect macro liquidity conditions that influence crypto markets.

Outputs
-------
snapshot["macro_liquidity"]
snapshot["macro_liquidity_summary"]
snapshot["macro_liquidity_alerts"]
snapshot["macro_liquidity_factors"]
snapshot["macro_liquidity_regime"]
snapshot["macro_liquidity_endpoints"]

Inputs used
-----------
snapshot["signals"]
snapshot["clusters"]
snapshot["cross_asset_intelligence"]
snapshot["metrics"]
snapshot["quant_factors"]
snapshot["market_regime"]

Design goals
------------
• deterministic
• collector-agnostic
• resilient to missing macro feeds
• cross-asset aware
• future ready for CPI/Fed/Economics collectors
"""

from __future__ import annotations

from typing import Dict, List, Any
from collections import defaultdict
import time


# -----------------------------------------------------
# helpers
# -----------------------------------------------------

def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _unique(items):
    seen = set()
    out = []

    for i in items:
        k = repr(i)

        if k in seen:
            continue

        seen.add(k)
        out.append(i)

    return out


# -----------------------------------------------------
# macro signal extraction
# -----------------------------------------------------

def _extract_macro_signals(snapshot):

    signals = _safe_list(snapshot.get("signals"))

    macro = {
        "rates": [],
        "dollar": [],
        "inflation": [],
        "equities": [],
        "commodities": [],
        "liquidity": [],
    }

    for s in signals:

        s = _safe_dict(s)

        stype = str(s.get("signal_type") or "")
        source = str(s.get("source") or "")
        title = str(s.get("title") or "").lower()

        if "rate" in title or "treasury" in title:
            macro["rates"].append(s)

        if "dollar" in title or "dxy" in title:
            macro["dollar"].append(s)

        if "inflation" in title or "cpi" in title:
            macro["inflation"].append(s)

        if "s&p" in title or "nasdaq" in title or "equity" in title:
            macro["equities"].append(s)

        if "oil" in title or "gold" in title or "commodity" in title:
            macro["commodities"].append(s)

        if stype in {"exchange_flow", "liquidity_event"}:
            macro["liquidity"].append(s)

    return macro


# -----------------------------------------------------
# macro factors
# -----------------------------------------------------

def _rates_factor(macro):

    signals = macro["rates"]

    if not signals:
        return 0.5

    score = 0

    for s in signals:

        text = str(s.get("title") or "").lower()

        if "fall" in text or "decline" in text:
            score += 0.7

        if "rise" in text or "higher" in text:
            score -= 0.7

    return _clamp(0.5 + score * 0.1)


def _dollar_factor(macro):

    signals = macro["dollar"]

    if not signals:
        return 0.5

    score = 0

    for s in signals:

        text = str(s.get("title") or "").lower()

        if "weaken" in text:
            score += 0.8

        if "strengthen" in text:
            score -= 0.8

    return _clamp(0.5 + score * 0.1)


def _equity_risk_factor(macro):

    signals = macro["equities"]

    if not signals:
        return 0.5

    score = 0

    for s in signals:

        text = str(s.get("title") or "").lower()

        if "rally" in text or "up" in text:
            score += 0.7

        if "selloff" in text or "crash" in text:
            score -= 0.9

    return _clamp(0.5 + score * 0.1)


def _inflation_factor(macro):

    signals = macro["inflation"]

    if not signals:
        return 0.5

    score = 0

    for s in signals:

        text = str(s.get("title") or "").lower()

        if "cooling" in text or "lower inflation" in text:
            score += 0.8

        if "rising inflation" in text:
            score -= 0.8

    return _clamp(0.5 + score * 0.1)


def _liquidity_factor(macro):

    flows = macro["liquidity"]

    if not flows:
        return 0.5

    size = len(flows)

    score = size * 0.08

    return _clamp(0.5 + score)


# -----------------------------------------------------
# regime classification
# -----------------------------------------------------

def _classify_liquidity_regime(factors):

    score = (
        factors["rates"] * 0.25 +
        factors["dollar"] * 0.20 +
        factors["equities"] * 0.20 +
        factors["inflation"] * 0.20 +
        factors["liquidity"] * 0.15
    )

    if score >= 0.70:
        return "global_liquidity_expansion"

    if score >= 0.55:
        return "risk_on_liquidity"

    if score <= 0.35:
        return "liquidity_contraction"

    return "neutral_liquidity"


# -----------------------------------------------------
# alerts
# -----------------------------------------------------

def _build_macro_alerts(factors, regime):

    alerts = []

    if factors["rates"] > 0.75:
        alerts.append({
            "type": "rates_tailwind",
            "severity": "medium",
            "title": "Rates trend supportive for crypto risk assets"
        })

    if factors["dollar"] < 0.30:
        alerts.append({
            "type": "dollar_pressure",
            "severity": "high",
            "title": "Strong dollar creating risk asset pressure"
        })

    if regime == "liquidity_contraction":
        alerts.append({
            "type": "macro_liquidity_tightening",
            "severity": "high",
            "title": "Global liquidity tightening detected"
        })

    return alerts


# -----------------------------------------------------
# endpoints
# -----------------------------------------------------

def _endpoint_manifest():

    return {
        "macro_liquidity": "/api/toknclaw/macro/liquidity",
        "macro_liquidity_summary": "/api/toknclaw/macro/liquidity/summary",
        "macro_liquidity_alerts": "/api/toknclaw/macro/liquidity/alerts",
        "macro_liquidity_regime": "/api/toknclaw/macro/liquidity/regime",
    }


# -----------------------------------------------------
# main engine
# -----------------------------------------------------

def build_macro_liquidity(snapshot: Dict[str, Any]):

    snapshot = _safe_dict(snapshot)

    macro = _extract_macro_signals(snapshot)

    factors = {
        "rates": _rates_factor(macro),
        "dollar": _dollar_factor(macro),
        "equities": _equity_risk_factor(macro),
        "inflation": _inflation_factor(macro),
        "liquidity": _liquidity_factor(macro),
    }

    regime = _classify_liquidity_regime(factors)

    alerts = _build_macro_alerts(factors, regime)

    summary = {
        "regime": regime,
        "rates_factor": round(factors["rates"], 2),
        "dollar_factor": round(factors["dollar"], 2),
        "equity_risk_factor": round(factors["equities"], 2),
        "inflation_factor": round(factors["inflation"], 2),
        "liquidity_factor": round(factors["liquidity"], 2),
        "alert_count": len(alerts),
    }

    return {
        "macro_liquidity": macro,
        "macro_liquidity_factors": factors,
        "macro_liquidity_regime": regime,
        "macro_liquidity_alerts": alerts,
        "macro_liquidity_summary": summary,
        "macro_liquidity_endpoints": _endpoint_manifest(),
    }
