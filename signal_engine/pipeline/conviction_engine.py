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
# MODULE: conviction_engine
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


def _relevance_weight(value: str) -> float:
    value = str(value or "").lower()
    if value == "high":
        return 1.0
    if value == "medium":
        return 0.6
    return 0.25


def build_conviction_scores(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    entity_intel = _safe_dict(snapshot.get("entity_intelligence"))
    signal_velocity = _safe_dict(snapshot.get("signal_velocity"))
    market_regime = _safe_dict(snapshot.get("market_regime"))
    sector_weights = _safe_dict(market_regime.get("sector_weights"))

    velocity_by_entity = {
        str(item.get("entity")): _safe_float(item.get("velocity_score"), 0.0)
        for item in _safe_list(signal_velocity.get("entities"))
        if isinstance(item, dict) and item.get("entity")
    }

    convictions = []

    for entity, record in entity_intel.items():
        record = _safe_dict(record)
        sectors = record.get("sectors") or []
        lead_sector_weight = max([_safe_float(sector_weights.get(s), 0.0) for s in sectors] or [0.0])

        confidence_component = _safe_float(record.get("latest_confidence"), 0.0) * 0.30
        persistence_component = _safe_float(record.get("max_persistence_score"), 0.0) * 0.20
        velocity_component = _safe_float(velocity_by_entity.get(entity), 0.0) * 0.20
        relevance_component = _relevance_weight(record.get("broadcast_relevance")) * 0.15
        sector_component = lead_sector_weight * 0.15

        conviction_score = round(
            confidence_component +
            persistence_component +
            velocity_component +
            relevance_component +
            sector_component,
            2
        )

        convictions.append({
            "entity": entity,
            "conviction_score": conviction_score,
            "latest_confidence": _safe_float(record.get("latest_confidence"), 0.0),
            "max_persistence_score": _safe_float(record.get("max_persistence_score"), 0.0),
            "velocity_score": _safe_float(velocity_by_entity.get(entity), 0.0),
            "broadcast_relevance": record.get("broadcast_relevance"),
            "alert_relevance": record.get("alert_relevance"),
            "state": record.get("state"),
            "sectors": sectors,
            "supporting_sources": record.get("supporting_sources") or [],
            "supporting_urls": record.get("supporting_urls") or [],
            "dominant_narrative_titles": record.get("dominant_narrative_titles") or [],
        })

    convictions.sort(
        key=lambda x: (
            x.get("conviction_score", 0.0),
            x.get("latest_confidence", 0.0),
            x.get("velocity_score", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    summary = {
        "top_entity": convictions[0]["entity"] if convictions else None,
        "top_conviction_score": convictions[0]["conviction_score"] if convictions else 0.0,
        "count": len(convictions),
    }

    return {
        "items": convictions,
        "summary": summary,
    }
