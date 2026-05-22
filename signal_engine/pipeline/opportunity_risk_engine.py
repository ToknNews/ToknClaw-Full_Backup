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
# MODULE: opportunity_risk_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_opportunity_risk_watchlists(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    convictions = _safe_list(_safe_dict(snapshot.get("conviction_scores")).get("items"))
    regime = _safe_dict(snapshot.get("market_regime"))
    risks = _safe_dict(snapshot.get("risks"))
    transition = _safe_dict(snapshot.get("regime_transition"))

    broadcast_bias = str(regime.get("broadcast_bias") or "neutral").lower()
    liquidity_regime = str(regime.get("liquidity_regime") or "balanced")
    primary_risks = _safe_list(risks.get("primary"))

    opportunities = []
    risk_watch = []

    for item in convictions:
        item = _safe_dict(item)
        score = _safe_float(item.get("conviction_score"), 0.0)
        entity = item.get("entity")

        if score >= 0.65 and broadcast_bias in {"bullish", "neutral"}:
            opportunities.append({
                "entity": entity,
                "conviction_score": score,
                "thesis": "Positive alignment across confidence, persistence, velocity, and sector leadership.",
                "state": item.get("state"),
                "sectors": item.get("sectors") or [],
                "supporting_sources": item.get("supporting_sources") or [],
                "supporting_urls": item.get("supporting_urls") or [],
            })

        if score < 0.45 or transition.get("transition_type") in {"regime_shift", "fragile"}:
            risk_watch.append({
                "entity": entity,
                "conviction_score": score,
                "risk_reason": "Low conviction or unstable regime context.",
                "state": item.get("state"),
                "sectors": item.get("sectors") or [],
                "supporting_sources": item.get("supporting_sources") or [],
                "supporting_urls": item.get("supporting_urls") or [],
            })

    if liquidity_regime == "liquidation_pressure":
        risk_watch.insert(0, {
            "entity": None,
            "conviction_score": 0.0,
            "risk_reason": "System-wide liquidation pressure detected.",
            "state": "macro_risk",
            "sectors": [],
            "supporting_sources": [],
            "supporting_urls": [],
        })

    for r in primary_risks:
        risk_watch.append({
            "entity": None,
            "conviction_score": 0.0,
            "risk_reason": str(r),
            "state": "macro_risk",
            "sectors": [],
            "supporting_sources": [],
            "supporting_urls": [],
        })

    opportunities = opportunities[:12]
    risk_watch = risk_watch[:12]

    summary = {
        "opportunity_count": len(opportunities),
        "risk_count": len(risk_watch),
        "top_opportunity": opportunities[0]["entity"] if opportunities else None,
        "top_risk": risk_watch[0]["risk_reason"] if risk_watch else None,
    }

    return {
        "opportunities": opportunities,
        "risks": risk_watch,
        "summary": summary,
    }
