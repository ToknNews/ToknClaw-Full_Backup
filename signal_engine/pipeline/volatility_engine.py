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
# MODULE: volatility_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Any, Dict, List


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


def _liquidation_volatility(snapshot: Dict[str, Any]) -> float:
    score = 0.0

    metrics = _safe_dict(snapshot.get("metrics"))
    liq_usd = _safe_float(metrics.get("defi_liquidations_usd"), 0.0)
    if liq_usd > 0:
        score += _clamp(liq_usd / 500_000_000) * 0.65

    for cluster in _safe_list(snapshot.get("clusters")):
        cluster = _safe_dict(cluster)
        if str(cluster.get("cluster_type") or "") == "defi_liquidation":
            score += 0.25

    return _clamp(score)


def _velocity_volatility(snapshot: Dict[str, Any]) -> float:
    summary = _safe_dict(snapshot.get("signal_velocity_summary"))
    urgency = str(summary.get("broadcast_urgency") or "").lower()

    if urgency == "high":
        return 0.75
    if urgency == "medium":
        return 0.50
    return 0.20


def _stress_volatility(snapshot: Dict[str, Any]) -> float:
    summary = _safe_dict(snapshot.get("market_stress_summary"))
    regime = str(summary.get("regime") or "")

    if regime == "severe_stress":
        return 0.90
    if regime == "elevated_stress":
        return 0.70
    if regime == "fragile_transition":
        return 0.45
    return 0.20


def _macro_volatility(snapshot: Dict[str, Any]) -> float:
    summary = _safe_dict(snapshot.get("macro_liquidity_summary"))
    regime = str(summary.get("regime") or "")

    if regime == "liquidity_contraction":
        return 0.75
    if regime == "neutral_liquidity":
        return 0.45
    return 0.20


def _retail_volatility(snapshot: Dict[str, Any]) -> float:
    retail = _safe_dict(snapshot.get("retail_pulse"))

    score = 0.0
    if bool(retail.get("memecoin_rotation")):
        score += 0.40
    if str(retail.get("retail_sentiment") or "").lower() == "risk_on":
        score += 0.20

    return _clamp(score)


def _classify_regime(factors: Dict[str, float]) -> str:
    score = (
        factors["liquidation_volatility"] * 0.28 +
        factors["velocity_volatility"] * 0.22 +
        factors["stress_volatility"] * 0.24 +
        factors["macro_volatility"] * 0.16 +
        factors["retail_volatility"] * 0.10
    )

    if score >= 0.78:
        return "extreme_volatility"
    if score >= 0.60:
        return "high_volatility"
    if score >= 0.38:
        return "elevated_volatility"
    return "contained_volatility"


def _build_alerts(regime: str, factors: Dict[str, float]) -> List[Dict[str, Any]]:
    alerts = []

    if regime in {"extreme_volatility", "high_volatility"}:
        alerts.append({
            "type": "volatility_regime_warning",
            "severity": "high" if regime == "extreme_volatility" else "medium",
            "title": f"{regime} detected",
        })

    if factors["liquidation_volatility"] >= 0.70:
        alerts.append({
            "type": "liquidation_volatility",
            "severity": "high",
            "title": "Liquidation-driven volatility is elevated",
        })

    return alerts


def build_volatility(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    factors = {
        "liquidation_volatility": round(_liquidation_volatility(snapshot), 2),
        "velocity_volatility": round(_velocity_volatility(snapshot), 2),
        "stress_volatility": round(_stress_volatility(snapshot), 2),
        "macro_volatility": round(_macro_volatility(snapshot), 2),
        "retail_volatility": round(_retail_volatility(snapshot), 2),
    }

    regime = _classify_regime(factors)
    alerts = _build_alerts(regime, factors)

    summary = {
        "regime": regime,
        "factors": factors,
        "alert_count": len(alerts),
    }

    return {
        "volatility": {
            "regime": regime,
            "factors": factors,
        },
        "volatility_summary": summary,
        "volatility_alerts": alerts,
        "volatility_endpoints": {
            "volatility": "/api/toknclaw/volatility",
            "volatility_summary": "/api/toknclaw/volatility/summary",
            "volatility_alerts": "/api/toknclaw/volatility/alerts",
        },
    }
