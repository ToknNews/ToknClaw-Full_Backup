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
# MODULE: narrative_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Set


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


def _cluster_map(clusters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(c.get("cluster_id")): c
        for c in clusters
        if isinstance(c, dict) and c.get("cluster_id")
    }


def _cluster_type_counts(cluster_analysis: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in cluster_analysis:
        ctype = str(item.get("cluster_type") or "unknown")
        counts[ctype] = counts.get(ctype, 0) + 1
    return counts


def _find_clusters_by_type(
    cluster_analysis: List[Dict[str, Any]],
    cluster_types: Set[str],
) -> List[Dict[str, Any]]:
    return [
        item for item in cluster_analysis
        if str(item.get("cluster_type") or "") in cluster_types
    ]


def _extract_entities(items: List[Dict[str, Any]]) -> List[str]:
    entities: List[str] = []
    for item in items:
        entity = item.get("entity")
        if entity:
            entities.append(str(entity))
    return _unique_preserve(entities)


def _extract_cluster_ids(items: List[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for item in items:
        cid = item.get("cluster_id")
        if cid:
            ids.append(str(cid))
    return _unique_preserve(ids)


def _extract_sources_and_urls(
    cluster_ids: List[str],
    clusters_by_id: Dict[str, Dict[str, Any]],
) -> tuple[list[str], list[str]]:
    sources: List[str] = []
    urls: List[str] = []

    for cid in cluster_ids:
        cluster = clusters_by_id.get(cid) or {}
        sources.extend(cluster.get("sources") or [])
        urls.extend(cluster.get("urls") or [])

    return _unique_preserve([str(s) for s in sources if s]), _unique_preserve([str(u) for u in urls if u])


def _strength_from_confidence(confidence: float) -> str:
    if confidence >= 0.9:
        return "dominant"
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.68:
        return "medium"
    return "low"


def _broadcast_relevance(confidence: float, narrative_type: str) -> str:
    if narrative_type in {"broad_risk_on_rotation", "market_stress", "institutional_repositioning"} and confidence >= 0.8:
        return "high"
    if confidence >= 0.72:
        return "medium"
    return "low"


def _alert_relevance(confidence: float, narrative_type: str) -> str:
    if narrative_type in {"market_stress", "institutional_repositioning", "retail_meme_rotation"} and confidence >= 0.8:
        return "high"
    if confidence >= 0.72:
        return "medium"
    return "low"


def _time_horizon(narrative_type: str) -> str:
    if narrative_type in {"retail_meme_rotation", "market_stress", "news_driven_repricing"}:
        return "intraday"
    if narrative_type in {"institutional_repositioning", "broad_risk_on_rotation"}:
        return "swing"
    return "multi_session"


def _sector_for_narrative(narrative_type: str) -> str:
    mapping = {
        "institutional_repositioning": "onchain",
        "defi_capital_formation": "defi",
        "protocol_business_strength": "protocol_economics",
        "retail_meme_rotation": "retail",
        "broad_risk_on_rotation": "market_structure",
        "market_stress": "market_structure",
        "news_driven_repricing": "news",
        "mixed_transition": "macro_structure",
    }
    return mapping.get(narrative_type, "general")


def _regime_alignment(narrative_type: str, market_regime: Dict[str, Any]) -> str:
    regime_name = str(market_regime.get("name") or "")

    if regime_name == "low_signal_mixed":
        return "partial"

    positive_map = {
        "speculative_risk_on": {"retail_meme_rotation", "broad_risk_on_rotation"},
        "defi_capital_formation": {"defi_capital_formation", "protocol_business_strength"},
        "institutional_repositioning": {"institutional_repositioning"},
        "broad_risk_on_rotation": {"broad_risk_on_rotation", "retail_meme_rotation", "defi_capital_formation"},
        "mixed_transition": {"mixed_transition", "news_driven_repricing"},
    }

    supported = positive_map.get(regime_name, set())

    if narrative_type in supported:
        return "aligned"

    if narrative_type == "market_stress" and regime_name in {"speculative_risk_on", "broad_risk_on_rotation"}:
        return "contradictory"

    return "partial"


def _hash_id(narrative_type: str, entities: List[str], cluster_ids: List[str]) -> str:
    raw = f"{narrative_type}|{'|'.join(sorted(entities))}|{'|'.join(sorted(cluster_ids))}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _build_narrative(
    *,
    narrative_type: str,
    title: str,
    summary: str,
    confidence: float,
    entities: List[str],
    cluster_ids: List[str],
    clusters_by_id: Dict[str, Dict[str, Any]],
    drivers: List[str],
    contradictions: List[str],
    market_regime: Dict[str, Any],
    actionability: str,
) -> Dict[str, Any]:
    sources, urls = _extract_sources_and_urls(cluster_ids, clusters_by_id)
    confidence = round(float(confidence), 2)

    return {
        "narrative_id": _hash_id(narrative_type, entities, cluster_ids),
        "narrative_type": narrative_type,
        "title": title,
        "summary": summary,
        "confidence": confidence,
        "strength": _strength_from_confidence(confidence),
        "time_horizon": _time_horizon(narrative_type),
        "sector": _sector_for_narrative(narrative_type),
        "entities": _unique_preserve(entities),
        "supporting_cluster_ids": _unique_preserve(cluster_ids),
        "supporting_sources": sources,
        "supporting_urls": urls,
        "drivers": _unique_preserve(drivers),
        "contradictions": _unique_preserve(contradictions),
        "regime_alignment": _regime_alignment(narrative_type, market_regime),
        "broadcast_relevance": _broadcast_relevance(confidence, narrative_type),
        "alert_relevance": _alert_relevance(confidence, narrative_type),
        "actionability": actionability,
        "persistence_key": f"{narrative_type}::{'|'.join(sorted(_unique_preserve(entities)))}",
        "first_seen": None,
        "last_seen": None,
        "state": "active",
    }


def build_narratives(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    clusters = _safe_list(snapshot.get("clusters"))
    cluster_analysis = _safe_list(snapshot.get("cluster_analysis"))
    retail_pulse = _safe_dict(snapshot.get("retail_pulse"))
    deltas = _safe_dict(snapshot.get("deltas"))
    market_regime = _safe_dict(snapshot.get("market_regime"))
    risks = _safe_dict(snapshot.get("risks"))

    clusters_by_id = _cluster_map(clusters)
    narratives: List[Dict[str, Any]] = []

    whale_items = _find_clusters_by_type(cluster_analysis, {"whale_activity"})
    defi_items = _find_clusters_by_type(cluster_analysis, {"protocol_tvl", "protocol_tvl_growth", "protocol_tvl_spike"})
    revenue_items = _find_clusters_by_type(cluster_analysis, {"protocol_revenue", "protocol_fees"})
    retail_items = _find_clusters_by_type(cluster_analysis, {"retail_narrative"})
    news_items = _find_clusters_by_type(cluster_analysis, {"news_theme"})

    whale_delta = ((_safe_dict(deltas.get("whale_activity_usd"))).get("percent_change"))
    retail_sentiment = str(retail_pulse.get("retail_sentiment") or "unknown").lower()
    memecoin_rotation = bool(retail_pulse.get("memecoin_rotation"))
    primary_risks = _safe_list(risks.get("primary"))

    contradictions_global: List[str] = []
    if retail_sentiment == "risk_on" and isinstance(whale_delta, (int, float)) and whale_delta < -10:
        contradictions_global.append("Retail risk appetite is rising while whale activity is falling.")
    if "Retail speculation is increasing." in primary_risks and retail_sentiment == "risk_off":
        contradictions_global.append("Risk warnings are elevated while retail sentiment reads risk-off.")

    # 1. institutional_repositioning
    if len(whale_items) >= 2:
        entities = _extract_entities(whale_items)
        cluster_ids = _extract_cluster_ids(whale_items)
        confidence = 0.82
        drivers = ["whale_activity"]

        if isinstance(whale_delta, (int, float)):
            if whale_delta > 10:
                confidence = 0.87
                drivers.append("rising_whale_activity")
            elif whale_delta < -10:
                confidence = 0.8
                drivers.append("falling_whale_activity")

        narratives.append(_build_narrative(
            narrative_type="institutional_repositioning",
            title="Large holders are actively repositioning",
            summary="Whale activity suggests institutional or large-holder positioning is an active market driver.",
            confidence=confidence,
            entities=entities,
            cluster_ids=cluster_ids,
            clusters_by_id=clusters_by_id,
            drivers=drivers,
            contradictions=contradictions_global,
            market_regime=market_regime,
            actionability="watch",
        ))

    # 2. defi_capital_formation
    if len(defi_items) >= 2:
        entities = _extract_entities(defi_items)
        cluster_ids = _extract_cluster_ids(defi_items)

        confidence = 0.86
        if len(defi_items) >= 3:
            confidence = 0.89

        narratives.append(_build_narrative(
            narrative_type="defi_capital_formation",
            title="Capital is concentrating in DeFi protocols",
            summary="TVL expansion across multiple protocols suggests active capital formation within DeFi.",
            confidence=confidence,
            entities=entities,
            cluster_ids=cluster_ids,
            clusters_by_id=clusters_by_id,
            drivers=["protocol_tvl", "capital_concentration"],
            contradictions=[],
            market_regime=market_regime,
            actionability="monitor",
        ))

    # 3. protocol_business_strength
    if len(revenue_items) >= 1:
        entities = _extract_entities(revenue_items)
        cluster_ids = _extract_cluster_ids(revenue_items)

        confidence = 0.78
        if len(revenue_items) >= 2:
            confidence = 0.84

        narratives.append(_build_narrative(
            narrative_type="protocol_business_strength",
            title="Protocol business activity is surfacing",
            summary="Revenue and fee signals suggest protocol-level business performance is becoming more visible.",
            confidence=confidence,
            entities=entities,
            cluster_ids=cluster_ids,
            clusters_by_id=clusters_by_id,
            drivers=["protocol_revenue", "protocol_fees"],
            contradictions=[],
            market_regime=market_regime,
            actionability="monitor",
        ))

    # 4. retail_meme_rotation
    if len(retail_items) >= 2 or memecoin_rotation:
        entities = _extract_entities(retail_items)
        cluster_ids = _extract_cluster_ids(retail_items)
        confidence = 0.8

        if retail_sentiment == "risk_on":
            confidence = 0.86
        elif retail_sentiment == "unknown":
            confidence = 0.74

        narratives.append(_build_narrative(
            narrative_type="retail_meme_rotation",
            title="Retail attention is rotating into meme narratives",
            summary="Social and memecoin signals indicate retail attention is clustering around speculative assets.",
            confidence=confidence,
            entities=entities,
            cluster_ids=cluster_ids,
            clusters_by_id=clusters_by_id,
            drivers=["retail_narrative", "memecoin_rotation"],
            contradictions=contradictions_global if contradictions_global else [],
            market_regime=market_regime,
            actionability="watch",
        ))

    # 5. broad_risk_on_rotation
    if (retail_sentiment == "risk_on") and (len(defi_items) >= 1) and (len(whale_items) >= 1):
        joint_items = whale_items[:2] + defi_items[:2] + retail_items[:2]
        entities = _extract_entities(joint_items)
        cluster_ids = _extract_cluster_ids(joint_items)

        narratives.append(_build_narrative(
            narrative_type="broad_risk_on_rotation",
            title="Risk-on rotation is broadening across the market",
            summary="Whale activity, DeFi capital formation, and retail appetite are aligning into a broader risk-on rotation.",
            confidence=0.88,
            entities=entities,
            cluster_ids=cluster_ids,
            clusters_by_id=clusters_by_id,
            drivers=["whale_activity", "protocol_tvl", "retail_sentiment"],
            contradictions=[],
            market_regime=market_regime,
            actionability="elevate",
        ))

    # 6. market_stress
    stress_contradictions: List[str] = []
    if "Retail speculation is increasing." in primary_risks:
        stress_contradictions.append("Speculation risk is rising.")
    if isinstance(whale_delta, (int, float)) and whale_delta < -15:
        stress_contradictions.append("Whale activity momentum has weakened materially.")

    if stress_contradictions:
        stress_items = whale_items[:2] + news_items[:1]
        entities = _extract_entities(stress_items)
        cluster_ids = _extract_cluster_ids(stress_items)

        narratives.append(_build_narrative(
            narrative_type="market_stress",
            title="Underlying market stress is building",
            summary="Cross-signal contradictions suggest fragility may be building beneath the surface.",
            confidence=0.79,
            entities=entities,
            cluster_ids=cluster_ids,
            clusters_by_id=clusters_by_id,
            drivers=["risk_signals", "cross_signal_contradiction"],
            contradictions=stress_contradictions,
            market_regime=market_regime,
            actionability="alert",
        ))

    # 7. news_driven_repricing
    if len(news_items) >= 2:
        entities = _extract_entities(news_items)
        cluster_ids = _extract_cluster_ids(news_items)

        narratives.append(_build_narrative(
            narrative_type="news_driven_repricing",
            title="News flow is influencing repricing behavior",
            summary="Clustered news catalysts suggest headline flow is contributing to market repricing.",
            confidence=0.72,
            entities=entities,
            cluster_ids=cluster_ids,
            clusters_by_id=clusters_by_id,
            drivers=["news_theme"],
            contradictions=[],
            market_regime=market_regime,
            actionability="watch",
        ))

    # 8. mixed_transition fallback
    if not narratives:
        all_cluster_ids = _extract_cluster_ids(cluster_analysis[:3])
        all_entities = _extract_entities(cluster_analysis[:3])

        narratives.append(_build_narrative(
            narrative_type="mixed_transition",
            title="The market is in a mixed transitional state",
            summary="Signals are present but not yet aligned strongly enough into a dominant narrative.",
            confidence=0.6,
            entities=all_entities,
            cluster_ids=all_cluster_ids,
            clusters_by_id=clusters_by_id,
            drivers=["mixed_signal_state"],
            contradictions=contradictions_global,
            market_regime=market_regime,
            actionability="observe",
        ))

    narratives = _dedupe_narratives(narratives)
    narratives.sort(
        key=lambda n: (
            n.get("broadcast_relevance") == "high",
            n.get("alert_relevance") == "high",
            n.get("confidence", 0.0),
            len(n.get("supporting_cluster_ids") or []),
            n.get("title", ""),
        ),
        reverse=True,
    )

    return narratives


def _dedupe_narratives(narratives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []

    for narrative in narratives:
        key = (
            narrative.get("narrative_type"),
            tuple(sorted(narrative.get("entities") or [])),
            tuple(sorted(narrative.get("supporting_cluster_ids") or [])),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(narrative)

    return out


def build_narrative_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    narratives = _safe_list(snapshot.get("narratives"))
    market_regime = _safe_dict(snapshot.get("market_regime"))

    primary = narratives[0] if narratives else {}
    secondary = narratives[1:3] if len(narratives) > 1 else []

    dominant_entities: List[str] = []
    for n in narratives[:3]:
        dominant_entities.extend(n.get("entities") or [])

    dominant_entities = _unique_preserve(dominant_entities)[:6]

    return {
        "primary_narrative": primary.get("narrative_type"),
        "primary_title": primary.get("title"),
        "secondary_narratives": [n.get("narrative_type") for n in secondary],
        "dominant_entities": dominant_entities,
        "regime_alignment": primary.get("regime_alignment") if primary else "partial",
        "market_regime": market_regime.get("name"),
        "narrative_count": len(narratives),
    }


def build_narrative_alerts(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    narratives = _safe_list(snapshot.get("narratives"))

    alerts = [
        {
            "narrative_id": n.get("narrative_id"),
            "narrative_type": n.get("narrative_type"),
            "title": n.get("title"),
            "confidence": n.get("confidence"),
            "strength": n.get("strength"),
            "alert_relevance": n.get("alert_relevance"),
            "entities": n.get("entities"),
            "supporting_urls": n.get("supporting_urls"),
            "actionability": n.get("actionability"),
        }
        for n in narratives
        if n.get("alert_relevance") in {"high", "medium"}
    ]

    alerts.sort(
        key=lambda a: (
            a.get("alert_relevance") == "high",
            a.get("confidence", 0.0),
            a.get("title", ""),
        ),
        reverse=True,
    )

    return alerts


def build_narrative_meta(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    narratives = _safe_list(snapshot.get("narratives"))

    sector_counts: Dict[str, int] = {}
    contradiction_count = 0

    for n in narratives:
        sector = str(n.get("sector") or "general")
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        contradiction_count += len(n.get("contradictions") or [])

    return {
        "narrative_count": len(narratives),
        "sector_counts": sector_counts,
        "contradiction_count": contradiction_count,
        "high_broadcast_relevance_count": sum(1 for n in narratives if n.get("broadcast_relevance") == "high"),
        "high_alert_relevance_count": sum(1 for n in narratives if n.get("alert_relevance") == "high"),
    }
