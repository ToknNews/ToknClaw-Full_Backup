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
# MODULE: narrative_correlation_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Set


# ----------------------------------------------------------
# SAFE UTILITIES
# ----------------------------------------------------------

def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


# ----------------------------------------------------------
# CLUSTER HELPERS
# ----------------------------------------------------------

def _cluster_map(clusters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(c.get("cluster_id")): c
        for c in clusters
        if isinstance(c, dict) and c.get("cluster_id")
    }


def _cluster_value_sum(cluster_ids, clusters_by_id):
    total = 0.0

    for cid in cluster_ids:
        c = clusters_by_id.get(cid) or {}
        total += float(c.get("total_value_usd") or 0)

    return total


def _find_cluster_analysis_by_type(
    cluster_analysis: List[Dict[str, Any]],
    cluster_types: Set[str],
) -> List[Dict[str, Any]]:
    return [
        item for item in cluster_analysis
        if str(item.get("cluster_type") or "") in cluster_types
    ]


def _extract_entities(items: List[Dict[str, Any]]) -> List[str]:
    entities = []

    for item in items:
        entity = item.get("entity")
        if entity:
            entities.append(str(entity))

    return _unique_preserve(entities)


def _extract_cluster_ids(items: List[Dict[str, Any]]) -> List[str]:
    ids = []

    for item in items:
        cid = item.get("cluster_id")
        if cid:
            ids.append(str(cid))

    return _unique_preserve(ids)


def _extract_sources_urls_from_clusters(
    cluster_ids: List[str],
    clusters_by_id: Dict[str, Dict[str, Any]],
) -> tuple[list[str], list[str]]:

    sources = []
    urls = []

    for cid in cluster_ids:

        cluster = clusters_by_id.get(cid) or {}

        sources.extend(cluster.get("sources") or [])
        urls.extend(cluster.get("urls") or [])

    return (
        _unique_preserve([str(s) for s in sources if s]),
        _unique_preserve([str(u) for u in urls if u]),
    )


# ----------------------------------------------------------
# ID GENERATION
# ----------------------------------------------------------

def _hash_id(correlation_type: str, cluster_ids: List[str], entities: List[str]) -> str:

    raw = f"{correlation_type}|{'|'.join(sorted(cluster_ids))}|{'|'.join(sorted(entities))}"

    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# ----------------------------------------------------------
# SCORING HELPERS
# ----------------------------------------------------------

def _strength_from_confidence(confidence: float) -> str:

    if confidence >= 0.9:
        return "dominant"

    if confidence >= 0.8:
        return "high"

    if confidence >= 0.68:
        return "medium"

    return "low"


def _broadcast_relevance(confidence: float, correlation_type: str) -> str:

    if correlation_type in {
        "institutional_accumulation",
        "defi_capital_rotation",
        "risk_on_speculation_cycle",
        "market_stress_repricing",
    } and confidence >= 0.8:
        return "high"

    if confidence >= 0.72:
        return "medium"

    return "low"


def _sector_for_correlation(correlation_type: str) -> str:

    mapping = {
        "institutional_accumulation": "onchain",
        "defi_capital_rotation": "defi",
        "risk_on_speculation_cycle": "retail",
        "protocol_fundamental_expansion": "protocol_economics",
        "market_stress_repricing": "market_structure",
        "news_liquidity_repricing": "news",
    }

    return mapping.get(correlation_type, "general")


# ----------------------------------------------------------
# CORRELATION BUILDER
# ----------------------------------------------------------

def _build_correlation(
    *,
    correlation_type: str,
    title: str,
    summary: str,
    confidence: float,
    entities: List[str],
    supporting_cluster_ids: List[str],
    supporting_drivers: List[str],
    contradictions: List[str],
    clusters_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:

    sources, urls = _extract_sources_urls_from_clusters(
        supporting_cluster_ids,
        clusters_by_id
    )

    confidence = round(float(confidence), 2)

    correlation_id = _hash_id(
        correlation_type,
        supporting_cluster_ids,
        entities
    )

    return {

        "correlation_id": correlation_id,

        # persistence metadata
        "persistence_key": f"{correlation_type}::{'|'.join(sorted(entities))}",
        "first_detected": None,
        "last_detected": None,

        "correlation_type": correlation_type,
        "title": title,
        "summary": summary,

        "confidence": confidence,
        "strength": _strength_from_confidence(confidence),

        "sector": _sector_for_correlation(correlation_type),

        "entities": _unique_preserve(entities),

        "supporting_cluster_ids": _unique_preserve(supporting_cluster_ids),

        "supporting_sources": sources,
        "supporting_urls": urls,

        "supporting_drivers": _unique_preserve(supporting_drivers),

        "contradictions": _unique_preserve(contradictions),

        "broadcast_relevance": _broadcast_relevance(
            confidence,
            correlation_type
        ),
    }


# ----------------------------------------------------------
# MAIN CORRELATION ENGINE
# ----------------------------------------------------------

def build_narrative_correlations(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:

    snapshot = _safe_dict(snapshot)

    clusters = _safe_list(snapshot.get("clusters"))
    cluster_analysis = _safe_list(snapshot.get("cluster_analysis"))

    retail_pulse = _safe_dict(snapshot.get("retail_pulse"))
    deltas = _safe_dict(snapshot.get("deltas"))
    market_regime = _safe_dict(snapshot.get("market_regime"))
    risks = _safe_dict(snapshot.get("risks"))

    clusters_by_id = _cluster_map(clusters)

    whale_items = _find_cluster_analysis_by_type(cluster_analysis, {"whale_activity"})
    defi_items = _find_cluster_analysis_by_type(cluster_analysis, {"protocol_tvl"})
    revenue_items = _find_cluster_analysis_by_type(cluster_analysis, {"protocol_revenue", "protocol_fees"})
    retail_items = _find_cluster_analysis_by_type(cluster_analysis, {"retail_narrative"})
    news_items = _find_cluster_analysis_by_type(cluster_analysis, {"news_theme"})

    retail_sentiment = str(retail_pulse.get("retail_sentiment") or "unknown").lower()

    memecoin_rotation = bool(retail_pulse.get("memecoin_rotation"))

    whale_delta = (_safe_dict(deltas.get("whale_activity_usd"))).get("percent_change")

    primary_risks = _safe_list(risks.get("primary"))

    correlations: List[Dict[str, Any]] = []

    # --------------------------------------------------
    # 1 Institutional Accumulation
    # --------------------------------------------------

    if len(whale_items) >= 2:

        entities = _extract_entities(whale_items)
        cluster_ids = _extract_cluster_ids(whale_items)

        confidence = 0.78

        value_sum = _cluster_value_sum(cluster_ids, clusters_by_id)

        if value_sum > 500_000_000:
            confidence += 0.05
        elif value_sum > 100_000_000:
            confidence += 0.03

        drivers = ["whale_activity"]
        contradictions = []

        correlations.append(_build_correlation(
            correlation_type="institutional_accumulation",
            title="Large-holder activity is converging into an institutional signal",
            summary="Whale clusters are aligning into a broader large-holder positioning narrative.",
            confidence=confidence,
            entities=entities,
            supporting_cluster_ids=cluster_ids,
            supporting_drivers=drivers,
            contradictions=contradictions,
            clusters_by_id=clusters_by_id,
        ))

    # --------------------------------------------------
    # 2 DeFi Capital Rotation
    # --------------------------------------------------

    if len(defi_items) >= 2:

        entities = _extract_entities(defi_items)
        cluster_ids = _extract_cluster_ids(defi_items)

        confidence = 0.80

        value_sum = _cluster_value_sum(cluster_ids, clusters_by_id)

        if value_sum > 5_000_000_000:
            confidence += 0.05
        elif value_sum > 1_000_000_000:
            confidence += 0.03

        correlations.append(_build_correlation(
            correlation_type="defi_capital_rotation",
            title="Capital concentration is forming inside DeFi",
            summary="TVL concentration across multiple protocols suggests a developing DeFi capital rotation.",
            confidence=confidence,
            entities=entities,
            supporting_cluster_ids=cluster_ids,
            supporting_drivers=["protocol_tvl"],
            contradictions=[],
            clusters_by_id=clusters_by_id,
        ))

    # --------------------------------------------------
    # 3 Retail Risk Cycle
    # --------------------------------------------------

    if len(retail_items) >= 2 or memecoin_rotation:

        entities = _extract_entities(retail_items)
        cluster_ids = _extract_cluster_ids(retail_items)

        confidence = 0.76

        if retail_sentiment == "risk_on":
            confidence = 0.86

        if memecoin_rotation:
            confidence = max(confidence, 0.84)

        correlations.append(_build_correlation(
            correlation_type="risk_on_speculation_cycle",
            title="Retail and memecoin signals are converging",
            summary="Retail narrative flow and speculative rotation are aligning into a broader risk-on speculation cycle.",
            confidence=confidence,
            entities=entities,
            supporting_cluster_ids=cluster_ids,
            supporting_drivers=["retail_narrative"],
            contradictions=[],
            clusters_by_id=clusters_by_id,
        ))

    # --------------------------------------------------
    # SORT
    # --------------------------------------------------

    correlations = _dedupe_correlations(correlations)

    correlations.sort(
        key=lambda c: (
            c.get("broadcast_relevance") == "high",
            c.get("confidence", 0),
            len(c.get("supporting_cluster_ids") or [])
        ),
        reverse=True
    )

    return correlations


# ----------------------------------------------------------
# DEDUPE
# ----------------------------------------------------------

def _dedupe_correlations(correlations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

    seen = set()
    out = []

    for item in correlations:

        key = (
            item.get("correlation_type"),
            tuple(sorted(item.get("entities") or [])),
            tuple(sorted(item.get("supporting_cluster_ids") or [])),
        )

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


# ----------------------------------------------------------
# SUMMARY
# ----------------------------------------------------------

def build_narrative_correlation_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:

    correlations = _safe_list(snapshot.get("narrative_correlations"))

    primary = correlations[0] if correlations else {}
    secondary = correlations[1:3]

    dominant_entities = []

    for c in correlations[:3]:
        dominant_entities.extend(c.get("entities") or [])

    dominant_entities = _unique_preserve(dominant_entities)[:8]

    return {
        "correlation_count": len(correlations),
        "primary_correlation": primary.get("correlation_type"),
        "primary_title": primary.get("title"),
        "secondary_correlations": [c.get("correlation_type") for c in secondary],
        "dominant_entities": dominant_entities,
        "high_broadcast_count": sum(
            1 for c in correlations if c.get("broadcast_relevance") == "high"
        ),
    }
