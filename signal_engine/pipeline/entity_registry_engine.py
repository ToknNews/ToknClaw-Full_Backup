#!/usr/bin/env python3

"""
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
# MODULE: entity_registry_engine
# PURPOSE: Builds canonical entity registry from all intelligence layers
#
# AUTHOR: TOKN SYSTEM
# ============================================================

Responsibilities
----------------
• unify entities from clusters, narratives, classification, signals
• normalize names and IDs
• deduplicate entities across sources
• attach signals, clusters, and narrative relationships
• output canonical entity registry for system-wide use

Author: TOKN Systems
"""

from typing import Dict, Any, List
from collections import defaultdict


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_name(name: str) -> str:
    return str(name).strip().upper()


def normalize_type(entity_type: str) -> str:
    if not entity_type:
        return "unknown"
    return str(entity_type).strip().lower()


def build_entity_id(name: str, entity_type: str) -> str:
    return f"{normalize_type(entity_type)}::{normalize_name(name)}"


# ============================================================
# CORE BUILDER
# ============================================================

def build_entity_registry(snapshot: Dict[str, Any]) -> Dict[str, Any]:

    registry: Dict[str, Dict[str, Any]] = {}

    def ensure_entity(name: str, entity_type: str, source: str):

        if not name:
            return None

        name_norm = normalize_name(name)
        type_norm = normalize_type(entity_type)
        entity_id = build_entity_id(name_norm, type_norm)

        if entity_id not in registry:
            registry[entity_id] = {
                "entity_id": entity_id,
                "name": name_norm,
                "type": type_norm,
                "sources": set(),
                "clusters": set(),
                "narratives": set(),
                "signal_count": 0,
                "confidence_sum": 0.0,
                "observations": 0,
            }

        entity = registry[entity_id]
        entity["sources"].add(source)

        return entity_id


    # ========================================================
    # 1. CLUSTERS (PRIMARY SOURCE)
    # ========================================================

    for cluster in snapshot.get("clusters", []):
        name = cluster.get("entity")
        ctype = cluster.get("cluster_type", "unknown")

        entity_id = ensure_entity(name, ctype, "cluster")
        if not entity_id:
            continue

        entity = registry[entity_id]

        entity["clusters"].add(cluster.get("cluster_id"))
        entity["signal_count"] += cluster.get("signal_count", 0)
        entity["confidence_sum"] += cluster.get("avg_confidence", 0)
        entity["observations"] += 1


    # ========================================================
    # 2. NARRATIVES
    # ========================================================

    for narrative in snapshot.get("narratives", []):
        for name in narrative.get("entities", []):
            entity_id = ensure_entity(name, "narrative", "narrative")
            if not entity_id:
                continue

            registry[entity_id]["narratives"].add(narrative.get("narrative_id"))


    # ========================================================
    # 3. SIGNALS (FALLBACK / ENRICHMENT)
    # ========================================================

    for signal in snapshot.get("signals", []):
        name = signal.get("entity") or signal.get("symbol")

        if not name:
            continue

        entity_id = ensure_entity(name, signal.get("type", "signal"), "signal")
        if not entity_id:
            continue

        entity = registry[entity_id]

        entity["signal_count"] += 1
        entity["confidence_sum"] += signal.get("confidence", 0)
        entity["observations"] += 1


    # ========================================================
    # 4. CLASSIFICATION (ENRICH TYPE)
    # ========================================================

    classification = snapshot.get("entity_classification", {})

    for name, data in classification.items():
        entity_type = data.get("type", "unknown")

        entity_id = ensure_entity(name, entity_type, "classification")
        if not entity_id:
            continue


    # ========================================================
    # FINALIZE
    # ========================================================

    for entity in registry.values():

        # sets → lists
        entity["sources"] = list(entity["sources"])
        entity["clusters"] = list(entity["clusters"])
        entity["narratives"] = list(entity["narratives"])

        # derived metrics
        if entity["observations"] > 0:
            entity["avg_confidence"] = entity["confidence_sum"] / entity["observations"]
        else:
            entity["avg_confidence"] = 0

        # cleanup
        del entity["confidence_sum"]
        del entity["observations"]

    return registry
