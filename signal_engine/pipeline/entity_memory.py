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
# MODULE: entity_memory
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Any, Dict, List


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_entity_intelligence(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    narratives = _safe_list(snapshot.get("narratives"))
    history = _safe_list(snapshot.get("narrative_history"))
    clusters = _safe_list(snapshot.get("clusters"))

    entities: Dict[str, Dict[str, Any]] = {}

    for narrative in narratives:
        if not isinstance(narrative, dict):
            continue

        for entity in narrative.get("entities") or []:
            if not entity:
                continue

            key = str(entity).upper()
            entities.setdefault(key, {
                "entity": key,
                "narrative_types": [],
                "sectors": [],
                "supporting_sources": [],
                "supporting_urls": [],
                "broadcast_relevance": "low",
                "alert_relevance": "low",
                "latest_confidence": 0.0,
                "peak_confidence": 0.0,
                "narrative_count": 0,
                "dominant_narrative_titles": [],
            })

            record = entities[key]
            record["narrative_types"].extend(narrative.get("narrative_type") and [narrative.get("narrative_type")] or [])
            record["sectors"].extend(narrative.get("sector") and [narrative.get("sector")] or [])
            record["supporting_sources"].extend(narrative.get("supporting_sources") or [])
            record["supporting_urls"].extend(narrative.get("supporting_urls") or [])
            record["narrative_count"] += 1
            record["latest_confidence"] = max(record["latest_confidence"], _safe_float(narrative.get("confidence"), 0.0))
            record["peak_confidence"] = max(record["peak_confidence"], _safe_float(narrative.get("confidence"), 0.0))

            if narrative.get("broadcast_relevance") == "high":
                record["broadcast_relevance"] = "high"
            elif narrative.get("broadcast_relevance") == "medium" and record["broadcast_relevance"] != "high":
                record["broadcast_relevance"] = "medium"

            if narrative.get("alert_relevance") == "high":
                record["alert_relevance"] = "high"
            elif narrative.get("alert_relevance") == "medium" and record["alert_relevance"] != "high":
                record["alert_relevance"] = "medium"

            if narrative.get("strength") in {"dominant", "high"} and narrative.get("title"):
                record["dominant_narrative_titles"].append(narrative.get("title"))

    history_by_entity: Dict[str, Dict[str, Any]] = {}

    for item in history:
        if not isinstance(item, dict):
            continue

        for entity in item.get("dominant_entities") or []:
            if not entity:
                continue

            key = str(entity).upper()
            history_by_entity.setdefault(key, {
                "observation_count": 0,
                "max_persistence_score": 0.0,
                "max_velocity_score": 0.0,
                "states": [],
            })

            h = history_by_entity[key]
            h["observation_count"] += int(item.get("observation_count") or 0)
            h["max_persistence_score"] = max(h["max_persistence_score"], _safe_float(item.get("persistence_score"), 0.0))
            h["max_velocity_score"] = max(h["max_velocity_score"], _safe_float(item.get("velocity_score"), 0.0))
            h["states"].append(str(item.get("state") or "active"))

    cluster_mentions: Dict[str, int] = {}
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue

        entity = cluster.get("entity")
        if entity:
            key = str(entity).upper()
            cluster_mentions[key] = cluster_mentions.get(key, 0) + 1

        for entity in cluster.get("entities") or []:
            key = str(entity).upper()
            cluster_mentions[key] = cluster_mentions.get(key, 0) + 1

    for entity, record in entities.items():
        hist = history_by_entity.get(entity, {})
        record["history_observation_count"] = hist.get("observation_count", 0)
        record["max_persistence_score"] = round(hist.get("max_persistence_score", 0.0), 2)
        record["max_velocity_score"] = round(hist.get("max_velocity_score", 0.0), 2)
        record["cluster_mentions"] = int(cluster_mentions.get(entity, 0))

        states = hist.get("states", [])
        record["state"] = "active"
        if "dominant" in states:
            record["state"] = "dominant"
        elif "fading" in states and "active" not in states and "dominant" not in states:
            record["state"] = "fading"

        record["narrative_types"] = list(dict.fromkeys(record["narrative_types"]))[:12]
        record["sectors"] = list(dict.fromkeys(record["sectors"]))[:12]
        record["supporting_sources"] = list(dict.fromkeys(record["supporting_sources"]))[:20]
        record["supporting_urls"] = list(dict.fromkeys(record["supporting_urls"]))[:20]
        record["dominant_narrative_titles"] = list(dict.fromkeys(record["dominant_narrative_titles"]))[:10]
        record["latest_confidence"] = round(record["latest_confidence"], 2)
        record["peak_confidence"] = round(record["peak_confidence"], 2)

    return dict(
        sorted(
            entities.items(),
            key=lambda kv: (
                kv[1].get("state") == "dominant",
                kv[1].get("broadcast_relevance") == "high",
                kv[1].get("max_persistence_score", 0.0),
                kv[1].get("max_velocity_score", 0.0),
                kv[1].get("latest_confidence", 0.0),
                kv[1].get("cluster_mentions", 0),
            ),
            reverse=True,
        )
    )


def build_entity_intelligence_meta(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    entity_intelligence = snapshot.get("entity_intelligence") or {}

    dominant = [e for e in entity_intelligence.values() if e.get("state") == "dominant"]
    high_broadcast = [e for e in entity_intelligence.values() if e.get("broadcast_relevance") == "high"]

    return {
        "entity_count": len(entity_intelligence),
        "dominant_entity_count": len(dominant),
        "high_broadcast_entity_count": len(high_broadcast),
    }
