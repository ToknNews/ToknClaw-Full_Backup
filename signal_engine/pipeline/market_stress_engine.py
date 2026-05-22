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
# MODULE: market_stress_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
market_stress_engine.py

ToknClaw Market Stress Engine

Purpose
-------
Detect and summarize market stress conditions affecting crypto.

Outputs
-------
snapshot["market_stress"]
snapshot["market_stress_summary"]
snapshot["market_stress_alerts"]
snapshot["market_stress_entities"]
snapshot["market_stress_regime"]
snapshot["market_stress_endpoints"]

Design
------
• resilient to missing data
• future-proof for macro / derivatives / regulation collectors
• compatible with current ToknClaw snapshot fields
"""

from __future__ import annotations

from typing import Dict, List, Any


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

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


# -------------------------------------------------------
# Snapshot accessors
# -------------------------------------------------------

def _clusters(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(c) for c in _safe_list(snapshot.get("clusters"))]


def _signals(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(s) for s in _safe_list(snapshot.get("signals"))]


def _correlations(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(c) for c in _safe_list(snapshot.get("narrative_correlations"))]


def _narratives(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(n) for n in _safe_list(snapshot.get("narratives"))]


def _market_regime(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("market_regime"))


def _macro_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("macro_liquidity_summary"))


def _macro_alerts(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(a) for a in _safe_list(snapshot.get("macro_liquidity_alerts"))]


def _institutional_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("institutional_flow_summary"))


def _institutional_alerts(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(a) for a in _safe_list(snapshot.get("institutional_flow_alerts"))]


def _velocity_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("signal_velocity_summary"))


def _velocity_alerts(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    signal_velocity = _safe_dict(snapshot.get("signal_velocity"))
    return [_safe_dict(a) for a in _safe_list(signal_velocity.get("alerts"))]


def _risks(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("risks"))


# -------------------------------------------------------
# Stress factor computations
# -------------------------------------------------------

def _liquidation_stress_factor(snapshot: Dict[str, Any]) -> float:
    score = 0.0

    for cluster in _clusters(snapshot):
        ctype = str(cluster.get("cluster_type") or "")
        value = _safe_float(cluster.get("total_value_usd"), 0.0)

        if ctype == "defi_liquidation":
            score += 0.45 + _clamp(value / 500_000_000) * 0.25

    metrics = _safe_dict(snapshot.get("metrics"))
    liq_usd = _safe_float(metrics.get("defi_liquidations_usd"), 0.0)

    if liq_usd > 0:
        score += _clamp(liq_usd / 500_000_000) * 0.20

    return _clamp(score)


def _macro_stress_factor(snapshot: Dict[str, Any]) -> float:
    summary = _macro_summary(snapshot)
    regime = str(summary.get("regime") or "")
    alerts = _macro_alerts(snapshot)

    score = 0.0

    if regime == "liquidity_contraction":
        score += 0.55
    elif regime == "neutral_liquidity":
        score += 0.20

    for alert in alerts:
        atype = str(alert.get("type") or "")
        if atype in {"dollar_pressure", "macro_liquidity_tightening"}:
            score += 0.18
        elif atype == "rates_tailwind":
            score -= 0.10

    return _clamp(score)


def _institutional_stress_factor(snapshot: Dict[str, Any]) -> float:
    summary = _institutional_summary(snapshot)
    regime = str(summary.get("regime") or "")
    alerts = _institutional_alerts(snapshot)

    score = 0.0

    if regime == "institutional_risk_off":
        score += 0.60
    elif regime == "institutional_rotation":
        score += 0.20
    elif regime == "heavy_institutional_accumulation":
        score -= 0.15

    for alert in alerts:
        atype = str(alert.get("type") or "")
        if atype == "institutional_risk_off":
            score += 0.20

    return _clamp(score)


def _policy_stress_factor(snapshot: Dict[str, Any]) -> float:
    score = 0.0

    for corr in _correlations(snapshot):
        ctype = str(corr.get("correlation_type") or "")
        conf = _safe_float(corr.get("confidence"), 0.0)

        if ctype == "crypto_policy_repricing":
            score += conf * 0.70

    for signal in _signals(snapshot):
        title = str(signal.get("title") or "").lower()
        summary = str(signal.get("summary") or "").lower()
        blob = f"{title} {summary}"

        if any(x in blob for x in ["sec", "cftc", "lawsuit", "regulation", "regulatory", "enforcement", "policy"]):
            score += 0.08

    return _clamp(score)


def _narrative_stress_factor(snapshot: Dict[str, Any]) -> float:
    score = 0.0

    for corr in _correlations(snapshot):
        ctype = str(corr.get("correlation_type") or "")
        conf = _safe_float(corr.get("confidence"), 0.0)

        if ctype == "market_stress_repricing":
            score += conf * 0.70
        elif ctype == "news_liquidity_repricing":
            score += conf * 0.25

    regime = _market_regime(snapshot)
    if str(regime.get("name") or "") == "mixed_transition":
        score += 0.12

    alignment = str(regime.get("narrative_alignment") or "")
    if alignment in {"mixed", "fragmented"}:
        score += 0.10

    return _clamp(score)


def _velocity_stress_factor(snapshot: Dict[str, Any]) -> float:
    summary = _velocity_summary(snapshot)
    alerts = _velocity_alerts(snapshot)

    urgency = str(summary.get("broadcast_urgency") or "").lower()

    score = 0.0

    if urgency == "high":
        score += 0.20
    elif urgency == "medium":
        score += 0.10

    for alert in alerts:
        atype = str(alert.get("type") or "")
        if atype in {"regime_shift_warning", "cluster_breakout", "correlation_acceleration"}:
            score += 0.10
        if atype == "entity_velocity_spike":
            score += 0.05

    return _clamp(score)


def _retail_fragility_factor(snapshot: Dict[str, Any]) -> float:
    score = 0.0

    retail_pulse = _safe_dict(snapshot.get("retail_pulse"))
    if bool(retail_pulse.get("memecoin_rotation")):
        score += 0.18

    if str(retail_pulse.get("retail_sentiment") or "").lower() == "risk_on":
        score += 0.10

    risks = _risks(snapshot)
    primary = _safe_list(risks.get("primary"))

    for risk in primary:
        text = str(risk)
        if "Retail speculation is increasing." in text:
            score += 0.18

    return _clamp(score)


# -------------------------------------------------------
# Regime classification
# -------------------------------------------------------

def _classify_market_stress_regime(factors: Dict[str, float]) -> str:
    score = (
        factors["liquidation_stress"] * 0.24 +
        factors["macro_stress"] * 0.18 +
        factors["institutional_stress"] * 0.16 +
        factors["policy_stress"] * 0.14 +
        factors["narrative_stress"] * 0.14 +
        factors["velocity_stress"] * 0.08 +
        factors["retail_fragility"] * 0.06
    )

    if score >= 0.78:
        return "severe_stress"
    if score >= 0.60:
        return "elevated_stress"
    if score >= 0.40:
        return "fragile_transition"
    return "contained_stress"


# -------------------------------------------------------
# Entity stress rows
# -------------------------------------------------------

def _build_entity_rows(snapshot: Dict[str, Any], stress_regime: str) -> List[Dict[str, Any]]:
    rows = []

    cross_asset = _safe_list(snapshot.get("cross_asset_intelligence"))
    quant_rows = _safe_list(snapshot.get("quant_factors"))

    quant_map = {}
    for row in quant_rows:
        row = _safe_dict(row)
        entity = str(row.get("entity") or "").upper()
        if entity:
            quant_map[entity] = row

    entity_names = []

    for cluster in _clusters(snapshot):
        entity = str(cluster.get("entity") or "").upper()
        if entity:
            entity_names.append(entity)

    entity_names = _unique_preserve(entity_names)

    supporting_urls = []
    for signal in _signals(snapshot):
        url = signal.get("source_url") or signal.get("raw_url")
        if url:
            supporting_urls.append(str(url))
    supporting_urls = _unique_preserve(supporting_urls)

    for entity in entity_names:
        score = 0.0
        cluster_types = []
        total_value = 0.0

        for cluster in _clusters(snapshot):
            c_entity = str(cluster.get("entity") or "").upper()
            if c_entity != entity:
                continue

            ctype = str(cluster.get("cluster_type") or "")
            value = _safe_float(cluster.get("total_value_usd"), 0.0)

            cluster_types.append(ctype)
            total_value += value

            if ctype == "defi_liquidation":
                score += 0.40
            elif ctype == "whale_activity":
                score += min(value / 2_000_000_000, 0.20)
            elif ctype == "news_theme":
                score += 0.05

        q = _safe_dict(quant_map.get(entity))
        score += _safe_float(q.get("stress_factor"), 0.0) * 0.45
        score += _safe_float(q.get("policy_risk_factor"), 0.0) * 0.20

        for relation in cross_asset:
            relation = _safe_dict(relation)
            entities = [str(e).upper() for e in _safe_list(relation.get("entities"))]

            if entity not in entities:
                continue

            rtype = str(relation.get("relation_type") or "")
            conf = _safe_float(relation.get("confidence"), 0.0)

            if rtype in {"crypto_policy_repricing", "crypto_rates_pressure"}:
                score += conf * 0.20

        if stress_regime == "severe_stress":
            score += 0.08
        elif stress_regime == "elevated_stress":
            score += 0.04

        rows.append({
            "entity": entity,
            "entity_stress_score": round(_clamp(score), 2),
            "cluster_count": len([c for c in _clusters(snapshot) if str(c.get("entity") or "").upper() == entity]),
            "cluster_types": _unique_preserve(cluster_types),
            "total_value_usd": round(total_value, 2),
            "supporting_urls": supporting_urls[:10],
        })

    rows.sort(
        key=lambda x: (
            x.get("entity_stress_score", 0.0),
            x.get("total_value_usd", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    return rows


# -------------------------------------------------------
# Alerts
# -------------------------------------------------------

def _build_alerts(factors: Dict[str, float], stress_regime: str, entity_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts = []

    if factors["liquidation_stress"] >= 0.70:
        alerts.append({
            "type": "liquidation_cascade_risk",
            "severity": "high",
            "title": "Liquidation stress is elevated",
        })

    if factors["macro_stress"] >= 0.65:
        alerts.append({
            "type": "macro_headwind",
            "severity": "high",
            "title": "Macro conditions are creating significant market stress",
        })

    if factors["policy_stress"] >= 0.60:
        alerts.append({
            "type": "policy_repricing_risk",
            "severity": "high",
            "title": "Policy/regulation repricing risk is elevated",
        })

    if stress_regime == "severe_stress":
        alerts.append({
            "type": "severe_market_stress",
            "severity": "high",
            "title": "Severe market stress regime detected",
        })
    elif stress_regime == "elevated_stress":
        alerts.append({
            "type": "elevated_market_stress",
            "severity": "medium",
            "title": "Elevated market stress regime detected",
        })

    for row in entity_rows[:5]:
        if _safe_float(row.get("entity_stress_score"), 0.0) >= 0.75:
            alerts.append({
                "type": "entity_stress_hotspot",
                "severity": "medium",
                "entity": row.get("entity"),
                "title": f'{row.get("entity")} is a stress hotspot',
            })

    return alerts[:25]


# -------------------------------------------------------
# Endpoint manifest
# -------------------------------------------------------

def _endpoint_manifest() -> Dict[str, str]:
    return {
        "market_stress": "/api/toknclaw/market-stress",
        "market_stress_summary": "/api/toknclaw/market-stress/summary",
        "market_stress_alerts": "/api/toknclaw/market-stress/alerts",
        "market_stress_entities": "/api/toknclaw/market-stress/entities",
        "market_stress_regime": "/api/toknclaw/market-stress/regime",
    }


# -------------------------------------------------------
# Main engine
# -------------------------------------------------------

def build_market_stress(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    factors = {
        "liquidation_stress": round(_liquidation_stress_factor(snapshot), 2),
        "macro_stress": round(_macro_stress_factor(snapshot), 2),
        "institutional_stress": round(_institutional_stress_factor(snapshot), 2),
        "policy_stress": round(_policy_stress_factor(snapshot), 2),
        "narrative_stress": round(_narrative_stress_factor(snapshot), 2),
        "velocity_stress": round(_velocity_stress_factor(snapshot), 2),
        "retail_fragility": round(_retail_fragility_factor(snapshot), 2),
    }

    stress_regime = _classify_market_stress_regime(factors)
    entity_rows = _build_entity_rows(snapshot, stress_regime)
    alerts = _build_alerts(factors, stress_regime, entity_rows)

    summary = {
        "regime": stress_regime,
        "top_entity": entity_rows[0]["entity"] if entity_rows else None,
        "top_entity_stress_score": entity_rows[0]["entity_stress_score"] if entity_rows else 0.0,
        "tracked_entity_count": len(entity_rows),
        "alert_count": len(alerts),
        "factors": factors,
    }

    return {
        "market_stress": {
            "factors": factors,
            "entities": entity_rows,
        },
        "market_stress_summary": summary,
        "market_stress_alerts": alerts,
        "market_stress_entities": entity_rows,
        "market_stress_regime": stress_regime,
        "market_stress_endpoints": _endpoint_manifest(),
    }
