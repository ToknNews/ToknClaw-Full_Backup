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
# MODULE: market_structure_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
market_structure_engine.py

ToknClaw Market Structure Engine

Purpose
-------
Detect structural conditions in the crypto market using:
- cluster concentration
- exchange / custody concentration
- stablecoin concentration
- whale flow dominance
- liquidity rotation
- macro liquidity
- institutional flow regime
- market stress regime
- velocity regime

Outputs
-------
snapshot["market_structure"]
snapshot["market_structure_summary"]
snapshot["market_structure_alerts"]
snapshot["market_structure_entities"]
snapshot["market_structure_regime"]
snapshot["market_structure_endpoints"]

Design
------
• future-proof
• resilient to missing sector labels
• works with current ToknClaw snapshot fields
• improves automatically as collectors and entity classification improve
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
# Constants
# -------------------------------------------------------

EXCHANGE_STYLE_ENTITIES = {
    "BINANCE",
    "BYBIT",
    "COINBASE",
    "COINBASE BRIDGE",
    "BITGET",
    "HTX",
    "MEXC",
    "GATE",
    "DERIBIT",
    "GEMINI",
    "ROBINHOOD",
}

STABLECOINS = {
    "USDT",
    "USDC",
    "DAI",
    "FDUSD",
    "TUSD",
    "USDE",
    "USDT0",
}

WHALE_CLUSTER_TYPES = {
    "whale_activity",
}

STRESS_CLUSTER_TYPES = {
    "defi_liquidation",
}

STRUCTURAL_CAPITAL_CLUSTER_TYPES = {
    "protocol_tvl",
    "protocol_revenue",
    "protocol_fees",
}


# -------------------------------------------------------
# Internal extraction
# -------------------------------------------------------

def _clusters(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(c) for c in _safe_list(snapshot.get("clusters"))]


def _signals(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(s) for s in _safe_list(snapshot.get("signals"))]


def _market_regime(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("market_regime"))


def _macro_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("macro_liquidity_summary"))


def _inst_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("institutional_flow_summary"))


def _stress_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("market_stress_summary"))


def _velocity_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("signal_velocity_summary"))


def _liquidity_rotation_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("liquidity_rotation_summary"))


def _entity_intel(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = _safe_dict(snapshot.get("entity_intelligence"))
    return {str(k).upper(): _safe_dict(v) for k, v in raw.items()}


# -------------------------------------------------------
# Structure factors
# -------------------------------------------------------

def _cluster_concentration_factor(snapshot: Dict[str, Any]) -> float:
    clusters = _clusters(snapshot)

    values = sorted(
        [_safe_float(c.get("total_value_usd"), 0.0) for c in clusters],
        reverse=True
    )

    if not values:
        return 0.0

    total = sum(values) or 1.0
    top3 = sum(values[:3])

    return _clamp(top3 / total)


def _exchange_concentration_factor(snapshot: Dict[str, Any]) -> float:
    total_exchange = 0.0
    total_all = 0.0

    for cluster in _clusters(snapshot):
        entity = str(cluster.get("entity") or "").upper()
        value = _safe_float(cluster.get("total_value_usd"), 0.0)
        total_all += value

        if entity in EXCHANGE_STYLE_ENTITIES:
            total_exchange += value

    if total_all <= 0:
        return 0.0

    return _clamp(total_exchange / total_all)


def _stablecoin_dominance_factor(snapshot: Dict[str, Any]) -> float:
    total_stables = 0.0
    total_all = 0.0

    for cluster in _clusters(snapshot):
        entity = str(cluster.get("entity") or "").upper()
        value = _safe_float(cluster.get("total_value_usd"), 0.0)
        total_all += value

        if entity in STABLECOINS:
            total_stables += value

    if total_all <= 0:
        return 0.0

    return _clamp(total_stables / total_all)


def _whale_dominance_factor(snapshot: Dict[str, Any]) -> float:
    total_whales = 0.0
    total_all = 0.0

    for cluster in _clusters(snapshot):
        ctype = str(cluster.get("cluster_type") or "")
        value = _safe_float(cluster.get("total_value_usd"), 0.0)
        total_all += value

        if ctype in WHALE_CLUSTER_TYPES:
            total_whales += value

    if total_all <= 0:
        return 0.0

    return _clamp(total_whales / total_all)


def _stress_fragility_factor(snapshot: Dict[str, Any]) -> float:
    score = 0.0

    for cluster in _clusters(snapshot):
        ctype = str(cluster.get("cluster_type") or "")
        value = _safe_float(cluster.get("total_value_usd"), 0.0)

        if ctype in STRESS_CLUSTER_TYPES:
            score += 0.40 + _clamp(value / 500_000_000) * 0.20

    stress = _stress_summary(snapshot)
    regime = str(stress.get("regime") or "")

    if regime == "severe_stress":
        score += 0.30
    elif regime == "elevated_stress":
        score += 0.18
    elif regime == "fragile_transition":
        score += 0.10

    return _clamp(score)


def _rotation_coherence_factor(snapshot: Dict[str, Any]) -> float:
    summary = _liquidity_rotation_summary(snapshot)
    dominant_weight = _safe_float(summary.get("dominant_weight"), 0.0)
    tracked_sectors = _safe_float(summary.get("tracked_sectors"), 0.0)

    # If only unknown sector exists, coherence is low-quality
    dominant_sector = str(summary.get("dominant_sector") or "")
    if dominant_sector == "unknown":
        return 0.20

    score = dominant_weight * 0.70

    if tracked_sectors >= 3:
        score += 0.15
    elif tracked_sectors == 1:
        score -= 0.10

    return _clamp(score)


def _macro_structure_factor(snapshot: Dict[str, Any]) -> float:
    summary = _macro_summary(snapshot)
    regime = str(summary.get("regime") or "")

    if regime == "global_liquidity_expansion":
        return 0.85
    if regime == "risk_on_liquidity":
        return 0.70
    if regime == "liquidity_contraction":
        return 0.20
    return 0.50


def _institutional_structure_factor(snapshot: Dict[str, Any]) -> float:
    summary = _inst_summary(snapshot)
    regime = str(summary.get("regime") or "")

    if regime == "heavy_institutional_accumulation":
        return 0.85
    if regime == "institutional_risk_on":
        return 0.72
    if regime == "institutional_risk_off":
        return 0.25
    return 0.50


def _velocity_fragility_factor(snapshot: Dict[str, Any]) -> float:
    summary = _velocity_summary(snapshot)
    urgency = str(summary.get("broadcast_urgency") or "").lower()

    if urgency == "high":
        return 0.75
    if urgency == "medium":
        return 0.50
    return 0.25


def _capital_quality_factor(snapshot: Dict[str, Any]) -> float:
    score = 0.0
    total = 0.0

    for cluster in _clusters(snapshot):
        ctype = str(cluster.get("cluster_type") or "")
        value = _safe_float(cluster.get("total_value_usd"), 0.0)

        if value <= 0:
            value = 1.0

        total += value

        if ctype in STRUCTURAL_CAPITAL_CLUSTER_TYPES:
            score += value

    if total <= 0:
        return 0.0

    return _clamp(score / total)


# -------------------------------------------------------
# Regime classification
# -------------------------------------------------------

def _classify_market_structure_regime(factors: Dict[str, float]) -> str:
    constructive_score = (
        factors["macro_structure"] * 0.18 +
        factors["institutional_structure"] * 0.18 +
        factors["capital_quality"] * 0.20 +
        factors["rotation_coherence"] * 0.14
    )

    fragile_score = (
        factors["stress_fragility"] * 0.22 +
        factors["velocity_fragility"] * 0.10 +
        factors["exchange_concentration"] * 0.10 +
        factors["stablecoin_dominance"] * 0.08 +
        factors["cluster_concentration"] * 0.10
    )

    if constructive_score >= 0.65 and fragile_score <= 0.38:
        return "constructive_expansion"

    if constructive_score >= 0.52 and fragile_score <= 0.52:
        return "institutional_rotation"

    if fragile_score >= 0.72:
        return "fragile_concentration"

    if fragile_score >= 0.55:
        return "defensive_structure"

    return "mixed_structure"


# -------------------------------------------------------
# Entity structure rows
# -------------------------------------------------------

def _build_entity_rows(snapshot: Dict[str, Any], regime: str) -> List[Dict[str, Any]]:
    entity_rows = []
    entity_map = defaultdict(lambda: {
        "cluster_types": [],
        "total_value_usd": 0.0,
        "signal_count": 0,
    })

    supporting_urls = []
    for signal in _signals(snapshot):
        url = signal.get("source_url") or signal.get("raw_url")
        if url:
            supporting_urls.append(str(url))
    supporting_urls = _unique_preserve(supporting_urls)

    entity_intel = _entity_intel(snapshot)

    for cluster in _clusters(snapshot):
        entity = str(cluster.get("entity") or "").upper()
        if not entity:
            continue

        ctype = str(cluster.get("cluster_type") or "")
        value = _safe_float(cluster.get("total_value_usd"), 0.0)
        count = int(_safe_float(cluster.get("signal_count"), 0))

        entity_map[entity]["cluster_types"].append(ctype)
        entity_map[entity]["total_value_usd"] += value
        entity_map[entity]["signal_count"] += count

    for entity, record in entity_map.items():
        score = 0.0
        ctype_list = _unique_preserve(record["cluster_types"])
        total_value = record["total_value_usd"]

        if entity in EXCHANGE_STYLE_ENTITIES:
            score += 0.25

        if entity in STABLECOINS:
            score += 0.20

        if "whale_activity" in ctype_list:
            score += 0.20

        if "defi_liquidation" in ctype_list:
            score += 0.35

        if "protocol_tvl" in ctype_list:
            score += 0.18

        score += _clamp(total_value / 10_000_000_000) * 0.20

        intel = _safe_dict(entity_intel.get(entity))
        score += _safe_float(intel.get("max_persistence_score"), 0.0) * 0.15
        score += _safe_float(intel.get("max_velocity_score"), 0.0) * 0.10

        if regime == "fragile_concentration":
            score += 0.08
        elif regime == "constructive_expansion":
            score -= 0.05

        entity_rows.append({
            "entity": entity,
            "market_structure_score": round(_clamp(score), 2),
            "cluster_types": ctype_list,
            "total_value_usd": round(total_value, 2),
            "signal_count": record["signal_count"],
            "supporting_urls": supporting_urls[:10],
        })

    entity_rows.sort(
        key=lambda x: (
            x.get("market_structure_score", 0.0),
            x.get("total_value_usd", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    return entity_rows


# -------------------------------------------------------
# Alerts
# -------------------------------------------------------

def _build_alerts(factors: Dict[str, float], regime: str, entity_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts = []

    if factors["cluster_concentration"] >= 0.75:
        alerts.append({
            "type": "cluster_concentration_risk",
            "severity": "high",
            "title": "Market structure is highly concentrated in a small number of clusters",
        })

    if factors["exchange_concentration"] >= 0.60:
        alerts.append({
            "type": "exchange_concentration",
            "severity": "medium",
            "title": "Exchange/custody entities are dominating market structure",
        })

    if factors["stablecoin_dominance"] >= 0.55:
        alerts.append({
            "type": "stablecoin_defensiveness",
            "severity": "medium",
            "title": "Stablecoin dominance suggests defensive positioning",
        })

    if factors["stress_fragility"] >= 0.65:
        alerts.append({
            "type": "stress_fragility",
            "severity": "high",
            "title": "Stress conditions are materially weakening market structure",
        })

    if regime == "fragile_concentration":
        alerts.append({
            "type": "fragile_market_structure",
            "severity": "high",
            "title": "Fragile concentration regime detected",
        })
    elif regime == "constructive_expansion":
        alerts.append({
            "type": "constructive_market_structure",
            "severity": "medium",
            "title": "Constructive market structure regime detected",
        })

    for row in entity_rows[:5]:
        if _safe_float(row.get("market_structure_score"), 0.0) >= 0.75:
            alerts.append({
                "type": "entity_structure_hotspot",
                "severity": "medium",
                "entity": row.get("entity"),
                "title": f'{row.get("entity")} is dominating current market structure',
            })

    return alerts[:25]


# -------------------------------------------------------
# Endpoints
# -------------------------------------------------------

def _endpoint_manifest() -> Dict[str, str]:
    return {
        "market_structure": "/api/toknclaw/market-structure",
        "market_structure_summary": "/api/toknclaw/market-structure/summary",
        "market_structure_alerts": "/api/toknclaw/market-structure/alerts",
        "market_structure_entities": "/api/toknclaw/market-structure/entities",
        "market_structure_regime": "/api/toknclaw/market-structure/regime",
    }


# -------------------------------------------------------
# Main engine
# -------------------------------------------------------

def build_market_structure(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    factors = {
        "cluster_concentration": round(_cluster_concentration_factor(snapshot), 2),
        "exchange_concentration": round(_exchange_concentration_factor(snapshot), 2),
        "stablecoin_dominance": round(_stablecoin_dominance_factor(snapshot), 2),
        "whale_dominance": round(_whale_dominance_factor(snapshot), 2),
        "stress_fragility": round(_stress_fragility_factor(snapshot), 2),
        "rotation_coherence": round(_rotation_coherence_factor(snapshot), 2),
        "macro_structure": round(_macro_structure_factor(snapshot), 2),
        "institutional_structure": round(_institutional_structure_factor(snapshot), 2),
        "velocity_fragility": round(_velocity_fragility_factor(snapshot), 2),
        "capital_quality": round(_capital_quality_factor(snapshot), 2),
    }

    regime = _classify_market_structure_regime(factors)
    entity_rows = _build_entity_rows(snapshot, regime)
    alerts = _build_alerts(factors, regime, entity_rows)

    summary = {
        "regime": regime,
        "top_entity": entity_rows[0]["entity"] if entity_rows else None,
        "top_entity_structure_score": entity_rows[0]["market_structure_score"] if entity_rows else 0.0,
        "tracked_entity_count": len(entity_rows),
        "alert_count": len(alerts),
        "factors": factors,
    }

    return {
        "market_structure": {
            "factors": factors,
            "entities": entity_rows,
        },
        "market_structure_summary": summary,
        "market_structure_alerts": alerts,
        "market_structure_entities": entity_rows,
        "market_structure_regime": regime,
        "market_structure_endpoints": _endpoint_manifest(),
    }
