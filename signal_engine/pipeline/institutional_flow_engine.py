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
# MODULE: institutional_flow_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
institutional_flow_engine.py

ToknClaw Institutional Flow Engine

Purpose
-------
Detect and summarize institutional-style crypto flow behavior.

Outputs
-------
snapshot["institutional_flows"]
snapshot["institutional_flow_summary"]
snapshot["institutional_flow_alerts"]
snapshot["institutional_flow_entities"]
snapshot["institutional_flow_regime"]
snapshot["institutional_flow_endpoints"]

Design
------
• works with currently available ToknClaw data
• gets stronger automatically as ETF / macro / issuer collectors are added
• does not require paid APIs by itself
• future-proof for exchange reserve, ETF, treasury, custody, and stablecoin collectors
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
# Keyword / entity heuristics
# -------------------------------------------------------

INSTITUTIONAL_KEYWORDS = {
    "etf",
    "blackrock",
    "fidelity",
    "ark",
    "grayscale",
    "issuer",
    "custody",
    "custodian",
    "treasury",
    "corporate treasury",
    "institutional",
    "prime",
    "reserve",
    "strategy",
    "microstrategy",
    "coinbase prime",
}

INSTITUTIONAL_ENTITIES = {
    "BLACKROCK",
    "FIDELITY",
    "ARK",
    "GRAYSCALE",
    "COINBASE",
    "COINBASE PRIME",
    "STRATEGY",
    "MICROSTRATEGY",
    "BITWISE",
    "VANECK",
    "FRANKLIN",
    "ARK INVEST",
}

EXCHANGE_STYLE_ENTITIES = {
    "BYBIT",
    "BINANCE",
    "GEMINI",
    "COINBASE BRIDGE",
    "BITGET",
    "HTX",
    "MEXC",
    "GATE",
    "DERIBIT",
    "ROBINHOOD",
}

STABLECOINS = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "USDT0"}


# -------------------------------------------------------
# Extraction helpers
# -------------------------------------------------------

def _signals(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(s) for s in _safe_list(snapshot.get("signals"))]


def _clusters(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(c) for c in _safe_list(snapshot.get("clusters"))]


def _correlations(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(c) for c in _safe_list(snapshot.get("narrative_correlations"))]


def _market_regime(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("market_regime"))


def _macro_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(snapshot.get("macro_liquidity_summary"))


def _extract_keyword_hits(snapshot: Dict[str, Any]) -> List[str]:
    hits = []

    for signal in _signals(snapshot):
        title = str(signal.get("title") or "").lower()
        summary = str(signal.get("summary") or "").lower()
        blob = f"{title} {summary}"

        for kw in sorted(INSTITUTIONAL_KEYWORDS):
            if kw in blob:
                hits.append(kw)

    return _unique_preserve(hits)


def _extract_institutional_entities(snapshot: Dict[str, Any]) -> List[str]:
    entities = []

    for cluster in _clusters(snapshot):
        entity = str(cluster.get("entity") or "").upper()
        if not entity:
            continue

        if entity in INSTITUTIONAL_ENTITIES:
            entities.append(entity)

        if entity in EXCHANGE_STYLE_ENTITIES:
            entities.append(entity)

        if entity in STABLECOINS:
            entities.append(entity)

        if "ETF" in entity or "TREASURY" in entity or "PRIME" in entity:
            entities.append(entity)

    for corr in _correlations(snapshot):
        for entity in _safe_list(corr.get("entities")):
            entity = str(entity).upper()
            if not entity:
                continue

            if entity in INSTITUTIONAL_ENTITIES or entity in EXCHANGE_STYLE_ENTITIES or entity in STABLECOINS:
                entities.append(entity)

    return _unique_preserve(entities)


def _extract_supporting_urls(snapshot: Dict[str, Any], limit: int = 20) -> List[str]:
    urls = []

    for signal in _signals(snapshot):
        url = signal.get("source_url") or signal.get("raw_url")
        if url:
            urls.append(str(url))

    return _unique_preserve(urls)[:limit]


# -------------------------------------------------------
# Factor calculations
# -------------------------------------------------------

def _whale_flow_factor(snapshot: Dict[str, Any]) -> float:
    total = 0.0

    for cluster in _clusters(snapshot):
        if str(cluster.get("cluster_type") or "") == "whale_activity":
            total += _safe_float(cluster.get("total_value_usd"), 0.0)

    return _clamp(total / 2_000_000_000)


def _stablecoin_flow_factor(snapshot: Dict[str, Any]) -> float:
    total = 0.0

    for cluster in _clusters(snapshot):
        entity = str(cluster.get("entity") or "").upper()
        if entity in STABLECOINS:
            total += _safe_float(cluster.get("total_value_usd"), 0.0)

    return _clamp(total / 2_000_000_000)


def _institutional_keyword_factor(snapshot: Dict[str, Any]) -> float:
    hits = _extract_keyword_hits(snapshot)
    return _clamp(len(hits) * 0.12)


def _institutional_correlation_factor(snapshot: Dict[str, Any]) -> float:
    score = 0.0

    for corr in _correlations(snapshot):
        ctype = str(corr.get("correlation_type") or "")
        conf = _safe_float(corr.get("confidence"), 0.0)

        if ctype == "institutional_accumulation":
            score += conf * 0.60

        if ctype == "news_liquidity_repricing":
            score += conf * 0.20

        if ctype == "crypto_macro_liquidity":
            score += conf * 0.20

    return _clamp(score)


def _entity_concentration_factor(snapshot: Dict[str, Any]) -> float:
    entities = _extract_institutional_entities(snapshot)
    return _clamp(len(entities) * 0.08)


def _macro_alignment_factor(snapshot: Dict[str, Any]) -> float:
    macro_summary = _macro_summary(snapshot)
    regime = str(macro_summary.get("regime") or "")

    if regime == "global_liquidity_expansion":
        return 0.80

    if regime == "risk_on_liquidity":
        return 0.65

    if regime == "liquidity_contraction":
        return 0.20

    return 0.50


def _exchange_concentration_factor(snapshot: Dict[str, Any]) -> float:
    total = 0.0

    for cluster in _clusters(snapshot):
        entity = str(cluster.get("entity") or "").upper()
        if entity in EXCHANGE_STYLE_ENTITIES:
            total += _safe_float(cluster.get("total_value_usd"), 0.0)

    return _clamp(total / 5_000_000_000)


# -------------------------------------------------------
# Regime classification
# -------------------------------------------------------

def _classify_institutional_flow_regime(factors: Dict[str, float]) -> str:
    score = (
        factors["whale_flow"] * 0.25 +
        factors["stablecoin_flow"] * 0.18 +
        factors["institutional_keywords"] * 0.12 +
        factors["institutional_correlation"] * 0.20 +
        factors["entity_concentration"] * 0.10 +
        factors["macro_alignment"] * 0.10 +
        factors["exchange_concentration"] * 0.05
    )

    if score >= 0.78:
        return "heavy_institutional_accumulation"

    if score >= 0.62:
        return "institutional_risk_on"

    if score <= 0.30:
        return "institutional_risk_off"

    return "institutional_rotation"


# -------------------------------------------------------
# Entity-level flow intelligence
# -------------------------------------------------------

def _build_entity_rows(snapshot: Dict[str, Any], regime: str) -> List[Dict[str, Any]]:
    rows = []

    urls = _extract_supporting_urls(snapshot)

    for entity in _extract_institutional_entities(snapshot):
        entity_clusters = []
        total_value = 0.0
        cluster_types = []

        for cluster in _clusters(snapshot):
            c_entity = str(cluster.get("entity") or "").upper()
            if c_entity != entity:
                continue

            entity_clusters.append(cluster)
            total_value += _safe_float(cluster.get("total_value_usd"), 0.0)
            cluster_types.append(str(cluster.get("cluster_type") or ""))

        score = _clamp(total_value / 5_000_000_000)

        if entity in STABLECOINS:
            entity_type = "stablecoin"
            score += 0.12
        elif entity in EXCHANGE_STYLE_ENTITIES:
            entity_type = "exchange_or_custody"
            score += 0.08
        elif entity in INSTITUTIONAL_ENTITIES or "ETF" in entity or "TREASURY" in entity:
            entity_type = "institutional"
            score += 0.15
        else:
            entity_type = "unknown"

        if regime in {"heavy_institutional_accumulation", "institutional_risk_on"}:
            score += 0.05

        rows.append({
            "entity": entity,
            "entity_type": entity_type,
            "institutional_flow_score": round(_clamp(score), 2),
            "cluster_count": len(entity_clusters),
            "cluster_types": _unique_preserve(cluster_types),
            "total_value_usd": round(total_value, 2),
            "supporting_urls": urls[:10],
        })

    rows.sort(
        key=lambda x: (
            x.get("institutional_flow_score", 0.0),
            x.get("total_value_usd", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    return rows


# -------------------------------------------------------
# Alerts
# -------------------------------------------------------

def _build_alerts(factors: Dict[str, float], regime: str, entity_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts = []

    if factors["whale_flow"] >= 0.75:
        alerts.append({
            "type": "whale_flow_surge",
            "severity": "high",
            "title": "Whale flow is elevated at an institutional scale",
        })

    if factors["stablecoin_flow"] >= 0.70:
        alerts.append({
            "type": "stablecoin_rotation",
            "severity": "high",
            "title": "Stablecoin movement suggests large capital repositioning",
        })

    if regime == "heavy_institutional_accumulation":
        alerts.append({
            "type": "institutional_accumulation_regime",
            "severity": "high",
            "title": "Heavy institutional accumulation regime detected",
        })

    if regime == "institutional_risk_off":
        alerts.append({
            "type": "institutional_risk_off",
            "severity": "high",
            "title": "Institutional positioning appears risk-off",
        })

    for row in entity_rows[:5]:
        if _safe_float(row.get("institutional_flow_score"), 0.0) >= 0.75:
            alerts.append({
                "type": "entity_institutional_flow",
                "severity": "medium",
                "entity": row.get("entity"),
                "title": f'{row.get("entity")} is showing elevated institutional flow characteristics',
            })

    return alerts[:25]


# -------------------------------------------------------
# Endpoint manifest
# -------------------------------------------------------

def _endpoint_manifest() -> Dict[str, str]:
    return {
        "institutional_flows": "/api/toknclaw/institutional/flows",
        "institutional_flow_summary": "/api/toknclaw/institutional/flows/summary",
        "institutional_flow_alerts": "/api/toknclaw/institutional/flows/alerts",
        "institutional_flow_entities": "/api/toknclaw/institutional/flows/entities",
        "institutional_flow_regime": "/api/toknclaw/institutional/flows/regime",
    }


# -------------------------------------------------------
# Main engine
# -------------------------------------------------------

def build_institutional_flows(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    factors = {
        "whale_flow": round(_whale_flow_factor(snapshot), 2),
        "stablecoin_flow": round(_stablecoin_flow_factor(snapshot), 2),
        "institutional_keywords": round(_institutional_keyword_factor(snapshot), 2),
        "institutional_correlation": round(_institutional_correlation_factor(snapshot), 2),
        "entity_concentration": round(_entity_concentration_factor(snapshot), 2),
        "macro_alignment": round(_macro_alignment_factor(snapshot), 2),
        "exchange_concentration": round(_exchange_concentration_factor(snapshot), 2),
    }

    regime = _classify_institutional_flow_regime(factors)
    entity_rows = _build_entity_rows(snapshot, regime)
    alerts = _build_alerts(factors, regime, entity_rows)

    summary = {
        "regime": regime,
        "top_entity": entity_rows[0]["entity"] if entity_rows else None,
        "top_entity_score": entity_rows[0]["institutional_flow_score"] if entity_rows else 0.0,
        "tracked_entity_count": len(entity_rows),
        "alert_count": len(alerts),
        "factors": factors,
    }

    return {
        "institutional_flows": {
            "factors": factors,
            "entities": entity_rows,
        },
        "institutional_flow_summary": summary,
        "institutional_flow_alerts": alerts,
        "institutional_flow_entities": entity_rows,
        "institutional_flow_regime": regime,
        "institutional_flow_endpoints": _endpoint_manifest(),
    }
