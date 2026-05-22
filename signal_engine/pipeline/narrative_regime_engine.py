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
# MODULE: narrative_regime_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Any, Dict, List
from collections import defaultdict


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _unique_preserve(items: List[Any]) -> List[Any]:
    seen = set()
    out = []
    for item in items:
        key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _narrative_type_scores(snapshot: Dict[str, Any]) -> Dict[str, float]:
    scores = defaultdict(float)

    for row in _safe_list(snapshot.get("narratives")):
        row = _safe_dict(row)
        ntype = str(row.get("narrative_type") or "")
        conf = _safe_float(row.get("confidence"), 0.0)
        if ntype:
            scores[ntype] += conf

    for row in _safe_list(snapshot.get("narrative_correlations")):
        row = _safe_dict(row)
        ctype = str(row.get("correlation_type") or "")
        conf = _safe_float(row.get("confidence"), 0.0)

        if ctype == "defi_capital_rotation":
            scores["defi_expansion"] += conf * 0.9
        elif ctype == "institutional_accumulation":
            scores["institutional_accumulation"] += conf * 0.9
        elif ctype == "risk_on_speculation_cycle":
            scores["retail_speculation"] += conf * 0.9
        elif ctype == "market_stress_repricing":
            scores["stress_repricing"] += conf * 1.0
        elif ctype == "crypto_policy_repricing":
            scores["policy_repricing"] += conf * 1.0
        elif ctype == "news_liquidity_repricing":
            scores["news_repricing"] += conf * 0.8

    return dict(scores)


def _volatility_bias(snapshot: Dict[str, Any]) -> float:
    summary = _safe_dict(snapshot.get("signal_velocity_summary"))
    urgency = str(summary.get("broadcast_urgency") or "").lower()

    if urgency == "high":
        return 0.20
    if urgency == "medium":
        return 0.10
    return 0.0


def _stress_bias(snapshot: Dict[str, Any]) -> float:
    summary = _safe_dict(snapshot.get("market_stress_summary"))
    regime = str(summary.get("regime") or "")

    if regime == "severe_stress":
        return 0.35
    if regime == "elevated_stress":
        return 0.22
    if regime == "fragile_transition":
        return 0.10
    return 0.0


def _macro_bias(snapshot: Dict[str, Any]) -> float:
    summary = _safe_dict(snapshot.get("macro_liquidity_summary"))
    regime = str(summary.get("regime") or "")

    if regime in {"global_liquidity_expansion", "risk_on_liquidity"}:
        return 0.15
    if regime == "liquidity_contraction":
        return -0.15
    return 0.0


def _institutional_bias(snapshot: Dict[str, Any]) -> float:
    summary = _safe_dict(snapshot.get("institutional_flow_summary"))
    regime = str(summary.get("regime") or "")

    if regime in {"heavy_institutional_accumulation", "institutional_risk_on"}:
        return 0.16
    if regime == "institutional_risk_off":
        return -0.16
    return 0.0


def _classify_regime(scores: Dict[str, float], snapshot: Dict[str, Any]) -> str:
    stress = scores.get("stress_repricing", 0.0) + max(_stress_bias(snapshot), 0.0)
    defi = scores.get("defi_expansion", 0.0)
    inst = scores.get("institutional_accumulation", 0.0)
    retail = scores.get("retail_speculation", 0.0)
    policy = scores.get("policy_repricing", 0.0)

    positive = defi + inst + max(_macro_bias(snapshot), 0.0)
    speculative = retail + _volatility_bias(snapshot)
    defensive = stress + policy + abs(min(_macro_bias(snapshot), 0.0))

    if defensive >= max(positive, speculative) and defensive >= 0.8:
        return "defensive_repricing"

    if positive >= speculative and positive >= defensive and positive >= 0.8:
        return "institutional_expansion"

    if speculative >= positive and speculative >= defensive and speculative >= 0.7:
        return "speculative_rotation"

    return "mixed_transition"


def _broadcast_bias(regime: str) -> str:
    mapping = {
        "institutional_expansion": "bullish",
        "speculative_rotation": "risk_on",
        "defensive_repricing": "bearish",
        "mixed_transition": "neutral",
    }
    return mapping.get(regime, "neutral")


def _build_alerts(regime: str, scores: Dict[str, float]) -> List[Dict[str, Any]]:
    alerts = []

    if regime == "defensive_repricing":
        alerts.append({
            "type": "narrative_regime_stress",
            "severity": "high",
            "title": "Narrative regime shifted into defensive repricing",
        })

    if regime == "institutional_expansion":
        alerts.append({
            "type": "narrative_regime_expansion",
            "severity": "medium",
            "title": "Narrative regime favors institutional expansion",
        })

    if scores.get("policy_repricing", 0.0) >= 0.7:
        alerts.append({
            "type": "policy_narrative_risk",
            "severity": "medium",
            "title": "Policy-driven narrative pressure is elevated",
        })

    return alerts


def build_narrative_regime(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    scores = _narrative_type_scores(snapshot)
    regime = _classify_regime(scores, snapshot)

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    dominant = [x[0] for x in sorted_scores[:3]]

    alerts = _build_alerts(regime, scores)

    summary = {
        "regime": regime,
        "broadcast_bias": _broadcast_bias(regime),
        "dominant_narratives": dominant,
        "score_map": {k: round(v, 3) for k, v in scores.items()},
        "alert_count": len(alerts),
    }

    return {
        "narrative_regime": {
            "regime": regime,
            "scores": {k: round(v, 3) for k, v in scores.items()},
            "dominant_narratives": dominant,
        },
        "narrative_regime_summary": summary,
        "narrative_regime_alerts": alerts,
        "narrative_regime_endpoints": {
            "narrative_regime": "/api/toknclaw/narrative-regime",
            "narrative_regime_summary": "/api/toknclaw/narrative-regime/summary",
            "narrative_regime_alerts": "/api/toknclaw/narrative-regime/alerts",
        },
    }
