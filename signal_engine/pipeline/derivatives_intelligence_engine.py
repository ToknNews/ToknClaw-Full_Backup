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
# MODULE: derivatives_intelligence_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
derivatives_intelligence_engine.py

ToknClaw Derivatives Intelligence Engine

Purpose
-------
Aggregate derivatives-related market intelligence across:
- liquidation pressure
- leverage stress
- crowding
- squeeze setup risk
- funding/perp bias
- open interest style pressure
- basis-style stress

Outputs
-------
snapshot["derivatives_intelligence"]
snapshot["derivatives_summary"]
snapshot["derivatives_alerts"]
snapshot["derivatives_entities"]
snapshot["derivatives_regime"]
snapshot["derivatives_endpoints"]

Design Goals
------------
• future-proof
• collector-agnostic
• works with current ToknClaw snapshot fields
• improves automatically as derivatives collectors are added
"""

from __future__ import annotations

from typing import Dict, List, Any
from collections import defaultdict


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


# -------------------------------------------------------
# Snapshot helpers
# -------------------------------------------------------

def _clusters(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(c) for c in _safe_list(snapshot.get("clusters"))]


def _signals(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(s) for s in _safe_list(snapshot.get("signals"))]


def _trade_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}

    for row in _safe_list(snapshot.get("trade_signals")):
        row = _safe_dict(row)
        entity = _safe_str(row.get("entity")).upper()
        if entity:
            out[entity] = row

    return out


def _quant_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}

    for row in _safe_list(snapshot.get("quant_factors")):
        row = _safe_dict(row)
        entity = _safe_str(row.get("entity")).upper()
        if entity:
            out[entity] = row

    return out


def _entity_intel_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = _safe_dict(snapshot.get("entity_intelligence"))
    return {str(k).upper(): _safe_dict(v) for k, v in raw.items()}


def _volatility_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("volatility_summary"))


def _market_stress_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("market_stress_summary"))


def _macro_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("macro_liquidity_summary"))


def _institutional_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("institutional_flow_summary"))


def _velocity_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("signal_velocity_summary"))


def _metrics(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("metrics"))


# -------------------------------------------------------
# Factor calculations
# -------------------------------------------------------

def _liquidation_pressure(snapshot: Dict[str, Any]) -> float:
    score = 0.0

    metrics = _metrics(snapshot)
    liq_usd = _safe_float(metrics.get("defi_liquidations_usd"), 0.0)

    if liq_usd > 0:
        score += _clamp(liq_usd / 500_000_000) * 0.70

    for cluster in _clusters(snapshot):
        ctype = _safe_str(cluster.get("cluster_type"))
        value = _safe_float(cluster.get("total_value_usd"), 0.0)

        if ctype == "defi_liquidation":
            score += 0.20 + (_clamp(value / 500_000_000) * 0.10)

    return _clamp(score)


def _leverage_pressure(snapshot: Dict[str, Any]) -> float:
    vol = _volatility_summary(snapshot)
    stress = _market_stress_summary(snapshot)
    velocity = _velocity_summary(snapshot)

    score = 0.0

    vol_regime = _safe_str(vol.get("regime"))
    if vol_regime in {"extreme_volatility", "high_volatility"}:
        score += 0.35
    elif vol_regime == "elevated_volatility":
        score += 0.18

    stress_regime = _safe_str(stress.get("regime"))
    if stress_regime == "severe_stress":
        score += 0.35
    elif stress_regime == "elevated_stress":
        score += 0.20

    urgency = _safe_str(velocity.get("broadcast_urgency")).lower()
    if urgency == "high":
        score += 0.15
    elif urgency == "medium":
        score += 0.08

    return _clamp(score)


def _funding_bias(snapshot: Dict[str, Any]) -> float:
    trade_map = _trade_map(snapshot)
    quant_map = _quant_map(snapshot)

    bullish = 0.0
    bearish = 0.0

    for entity, trade in trade_map.items():
        direction = _safe_str(trade.get("direction"))
        confidence = _safe_float(trade.get("confidence"), 0.0)
        q = _safe_dict(quant_map.get(entity))
        speculation = _safe_float(q.get("speculation_factor"), 0.0)

        if direction in {"bullish", "strong_bullish"}:
            bullish += confidence * (0.7 + speculation * 0.3)
        elif direction in {"bearish", "strong_bearish"}:
            bearish += confidence * (0.7 + speculation * 0.3)

    if bullish == 0 and bearish == 0:
        return 0.50

    total = bullish + bearish
    raw = bullish / total if total > 0 else 0.50

    return round(_clamp(raw), 4)


def _open_interest_pressure(snapshot: Dict[str, Any]) -> float:
    trade_map = _trade_map(snapshot)
    quant_map = _quant_map(snapshot)

    score = 0.0
    count = 0

    for entity, trade in trade_map.items():
        direction = _safe_str(trade.get("direction"))
        confidence = _safe_float(trade.get("confidence"), 0.0)
        q = _safe_dict(quant_map.get(entity))

        momentum = _safe_float(q.get("momentum_factor"), 0.0)
        liquidity = _safe_float(q.get("liquidity_factor"), 0.0)
        stress = _safe_float(q.get("stress_factor"), 0.0)

        local = confidence * 0.45 + momentum * 0.25 + liquidity * 0.20 + stress * 0.10

        if direction in {"strong_bullish", "strong_bearish"}:
            local += 0.10

        score += local
        count += 1

    if count == 0:
        return 0.0

    return _clamp(score / count)


def _crowding_risk(snapshot: Dict[str, Any]) -> float:
    trade_map = _trade_map(snapshot)
    quant_map = _quant_map(snapshot)

    bullish = 0
    bearish = 0
    strong = 0

    for entity, trade in trade_map.items():
        direction = _safe_str(trade.get("direction"))
        q = _safe_dict(quant_map.get(entity))
        speculation = _safe_float(q.get("speculation_factor"), 0.0)

        if direction in {"bullish", "strong_bullish"}:
            bullish += 1
        elif direction in {"bearish", "strong_bearish"}:
            bearish += 1

        if direction in {"strong_bullish", "strong_bearish"} or speculation >= 0.70:
            strong += 1

    total = bullish + bearish
    if total == 0:
        return 0.0

    imbalance = abs(bullish - bearish) / total
    intensity = strong / total

    return _clamp(imbalance * 0.55 + intensity * 0.45)


def _basis_stress(snapshot: Dict[str, Any]) -> float:
    macro = _macro_summary(snapshot)
    inst = _institutional_summary(snapshot)
    stress = _market_stress_summary(snapshot)

    score = 0.0

    macro_regime = _safe_str(macro.get("regime"))
    if macro_regime == "liquidity_contraction":
        score += 0.35
    elif macro_regime == "neutral_liquidity":
        score += 0.12

    inst_regime = _safe_str(inst.get("regime"))
    if inst_regime == "institutional_risk_off":
        score += 0.25

    stress_regime = _safe_str(stress.get("regime"))
    if stress_regime == "severe_stress":
        score += 0.25
    elif stress_regime == "elevated_stress":
        score += 0.15

    return _clamp(score)


def _squeeze_risk(snapshot: Dict[str, Any], funding_bias: float, crowding_risk: float) -> Dict[str, float]:
    trade_map = _trade_map(snapshot)

    bullish_count = 0
    bearish_count = 0

    for trade in trade_map.values():
        direction = _safe_str(trade.get("direction"))
        if direction in {"bullish", "strong_bullish"}:
            bullish_count += 1
        elif direction in {"bearish", "strong_bearish"}:
            bearish_count += 1

    total = bullish_count + bearish_count
    if total == 0:
        return {
            "short_squeeze_risk": 0.0,
            "long_squeeze_risk": 0.0,
        }

    bullish_ratio = bullish_count / total
    bearish_ratio = bearish_count / total

    short_squeeze_risk = _clamp((1.0 - funding_bias) * 0.55 + bearish_ratio * 0.20 + crowding_risk * 0.25)
    long_squeeze_risk = _clamp(funding_bias * 0.55 + bullish_ratio * 0.20 + crowding_risk * 0.25)

    return {
        "short_squeeze_risk": round(short_squeeze_risk, 2),
        "long_squeeze_risk": round(long_squeeze_risk, 2),
    }


def _derivatives_confidence(snapshot: Dict[str, Any]) -> float:
    metrics = _metrics(snapshot)
    score = 0.35

    if _safe_float(metrics.get("defi_liquidations_usd"), 0.0) > 0:
        score += 0.20

    if _safe_str(_volatility_summary(snapshot).get("regime")):
        score += 0.15

    if _safe_str(_market_stress_summary(snapshot).get("regime")):
        score += 0.15

    if len(_safe_list(snapshot.get("trade_signals"))) > 0:
        score += 0.10

    return round(_clamp(score), 2)


# -------------------------------------------------------
# Regime classification
# -------------------------------------------------------

def _classify_regime(factors: Dict[str, float]) -> str:
    liquidation = factors["liquidation_pressure"]
    leverage = factors["leverage_pressure"]
    funding = factors["funding_bias"]
    oi = factors["open_interest_pressure"]
    crowding = factors["crowding_risk"]
    basis = factors["basis_stress"]
    short_sq = factors["short_squeeze_risk"]
    long_sq = factors["long_squeeze_risk"]

    stress_score = liquidation * 0.28 + leverage * 0.24 + basis * 0.18 + crowding * 0.15 + oi * 0.15

    if stress_score >= 0.78:
        return "stressed_unwind"

    if short_sq >= 0.72 and funding <= 0.45:
        return "short_squeeze_setup"

    if long_sq >= 0.72 and funding >= 0.55:
        return "long_squeeze_setup"

    if funding >= 0.62 and stress_score <= 0.50:
        return "bullish_leverage"

    if funding <= 0.38 and stress_score <= 0.50:
        return "bearish_leverage"

    return "balanced_derivatives"


# -------------------------------------------------------
# Entity-level derivatives intelligence
# -------------------------------------------------------

def _build_entity_rows(snapshot: Dict[str, Any], regime: str, factors: Dict[str, float]) -> List[Dict[str, Any]]:
    trade_map = _trade_map(snapshot)
    quant_map = _quant_map(snapshot)
    entity_intel = _entity_intel_map(snapshot)

    rows = []

    supporting_urls = []
    for signal in _signals(snapshot):
        url = signal.get("source_url") or signal.get("raw_url")
        if url:
            supporting_urls.append(str(url))
    supporting_urls = _unique_preserve(supporting_urls)

    entities = set()
    entities.update(trade_map.keys())
    entities.update(quant_map.keys())
    entities.update(entity_intel.keys())

    for entity in sorted(entities):
        trade = _safe_dict(trade_map.get(entity))
        quant = _safe_dict(quant_map.get(entity))
        intel = _safe_dict(entity_intel.get(entity))

        direction = _safe_str(trade.get("direction"))
        confidence = _safe_float(trade.get("confidence"), 0.0)
        momentum = _safe_float(quant.get("momentum_factor"), 0.0)
        speculation = _safe_float(quant.get("speculation_factor"), 0.0)
        stress = _safe_float(quant.get("stress_factor"), 0.0)
        liquidity = _safe_float(quant.get("liquidity_factor"), 0.0)
        velocity = _safe_float(intel.get("max_velocity_score"), 0.0)

        derivatives_score = (
            confidence * 0.20 +
            momentum * 0.18 +
            speculation * 0.20 +
            stress * 0.20 +
            liquidity * 0.12 +
            velocity * 0.10
        )

        squeeze_tag = None
        if direction in {"bearish", "strong_bearish"} and factors["short_squeeze_risk"] >= 0.65:
            squeeze_tag = "short_squeeze_risk"
        elif direction in {"bullish", "strong_bullish"} and factors["long_squeeze_risk"] >= 0.65:
            squeeze_tag = "long_squeeze_risk"

        rows.append({
            "entity": entity,
            "direction": direction or None,
            "derivatives_score": round(_clamp(derivatives_score), 2),
            "trade_confidence": round(confidence, 2),
            "momentum_factor": round(momentum, 2),
            "speculation_factor": round(speculation, 2),
            "stress_factor": round(stress, 2),
            "liquidity_factor": round(liquidity, 2),
            "velocity_score": round(velocity, 2),
            "squeeze_tag": squeeze_tag,
            "supporting_urls": supporting_urls[:10],
        })

    rows.sort(
        key=lambda x: (
            x.get("derivatives_score", 0.0),
            x.get("trade_confidence", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    return rows[:100]


# -------------------------------------------------------
# Alerts
# -------------------------------------------------------

def _build_alerts(factors: Dict[str, float], regime: str, entity_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts = []

    if regime == "stressed_unwind":
        alerts.append({
            "type": "derivatives_unwind",
            "severity": "high",
            "title": "Derivatives regime indicates stressed unwind conditions",
        })

    if regime == "short_squeeze_setup":
        alerts.append({
            "type": "short_squeeze_setup",
            "severity": "high",
            "title": "Derivatives regime indicates short squeeze setup",
        })

    if regime == "long_squeeze_setup":
        alerts.append({
            "type": "long_squeeze_setup",
            "severity": "high",
            "title": "Derivatives regime indicates long squeeze setup",
        })

    if factors["liquidation_pressure"] >= 0.70:
        alerts.append({
            "type": "liquidation_pressure",
            "severity": "high",
            "title": "Liquidation pressure is elevated",
        })

    if factors["crowding_risk"] >= 0.70:
        alerts.append({
            "type": "crowding_risk",
            "severity": "medium",
            "title": "Derivatives crowding risk is elevated",
        })

    for row in entity_rows[:5]:
        if _safe_float(row.get("derivatives_score"), 0.0) >= 0.75:
            alerts.append({
                "type": "entity_derivatives_hotspot",
                "severity": "medium",
                "entity": row.get("entity"),
                "title": f'{row.get("entity")} is a derivatives hotspot',
            })

    return alerts[:25]


# -------------------------------------------------------
# Endpoints
# -------------------------------------------------------

def _endpoint_manifest() -> Dict[str, str]:
    return {
        "derivatives_intelligence": "/api/toknclaw/derivatives",
        "derivatives_summary": "/api/toknclaw/derivatives/summary",
        "derivatives_alerts": "/api/toknclaw/derivatives/alerts",
        "derivatives_entities": "/api/toknclaw/derivatives/entities",
        "derivatives_regime": "/api/toknclaw/derivatives/regime",
    }


# -------------------------------------------------------
# Main engine
# -------------------------------------------------------

def build_derivatives_intelligence(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    funding_bias = _funding_bias(snapshot)
    crowding_risk = _crowding_risk(snapshot)
    squeeze = _squeeze_risk(snapshot, funding_bias, crowding_risk)

    factors = {
        "liquidation_pressure": round(_liquidation_pressure(snapshot), 2),
        "leverage_pressure": round(_leverage_pressure(snapshot), 2),
        "funding_bias": round(funding_bias, 2),
        "open_interest_pressure": round(_open_interest_pressure(snapshot), 2),
        "crowding_risk": round(crowding_risk, 2),
        "basis_stress": round(_basis_stress(snapshot), 2),
        "short_squeeze_risk": squeeze["short_squeeze_risk"],
        "long_squeeze_risk": squeeze["long_squeeze_risk"],
        "derivatives_confidence": _derivatives_confidence(snapshot),
    }

    regime = _classify_regime(factors)
    entity_rows = _build_entity_rows(snapshot, regime, factors)
    alerts = _build_alerts(factors, regime, entity_rows)

    summary = {
        "regime": regime,
        "top_entity": entity_rows[0]["entity"] if entity_rows else None,
        "top_derivatives_score": entity_rows[0]["derivatives_score"] if entity_rows else 0.0,
        "tracked_entity_count": len(entity_rows),
        "alert_count": len(alerts),
        "factors": factors,
    }

    return {
        "derivatives_intelligence": {
            "factors": factors,
            "entities": entity_rows,
        },
        "derivatives_summary": summary,
        "derivatives_alerts": alerts,
        "derivatives_entities": entity_rows,
        "derivatives_regime": regime,
        "derivatives_endpoints": _endpoint_manifest(),
    }
