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
# MODULE: entity_relationship_graph
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
entity_relationship_graph.py

ToknClaw Entity Relationship Graph Engine

Purpose
-------
Construct a relationship graph between entities discovered in the snapshot.

Relationships Detected
----------------------
protocol_token
token_chain
protocol_chain
exchange_token
entity_cluster
entity_narrative
entity_correlation
entity_signal_source

Outputs
-------
snapshot["entity_relationship_graph"]
snapshot["entity_relationship_summary"]
snapshot["entity_relationship_alerts"]
snapshot["entity_relationship_endpoints"]

Design Goals
------------
• deterministic
• graph-ready
• scalable
• snapshot-safe
• future graph database compatible
"""

from __future__ import annotations

from typing import Dict, List, Any
from collections import defaultdict


# ---------------------------------------------------
# Helpers
# ---------------------------------------------------

def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _safe_str(v):
    if v is None:
        return ""
    return str(v).strip()


def _unique_preserve(items):

    seen = set()
    out = []

    for i in items:

        key = repr(i)

        if key in seen:
            continue

        seen.add(key)
        out.append(i)

    return out


# ---------------------------------------------------
# Edge Builder
# ---------------------------------------------------

def _add_edge(graph, source, target, relation):

    if not source or not target:
        return

    graph.append({
        "source": source,
        "target": target,
        "relation": relation
    })


# ---------------------------------------------------
# Graph Builder
# ---------------------------------------------------

def build_entity_relationship_graph(snapshot: Dict[str, Any]):

    snapshot = _safe_dict(snapshot)

    graph = []

    entity_class = _safe_list(snapshot.get("entity_classification"))
    clusters = _safe_list(snapshot.get("clusters"))
    signals = _safe_list(snapshot.get("signals"))
    narratives = _safe_list(snapshot.get("narratives"))
    correlations = _safe_list(snapshot.get("narrative_correlations"))

    entity_lookup = {}

    for e in entity_class:

        e = _safe_dict(e)

        entity_lookup[e.get("entity")] = e


    # ---------------------------------------------------
    # Token ↔ Chain
    # ---------------------------------------------------

    for entity, meta in entity_lookup.items():

        chain = meta.get("chain")

        if chain:

            _add_edge(
                graph,
                entity,
                chain.upper(),
                "token_chain"
            )


    # ---------------------------------------------------
    # Protocol ↔ Chain
    # ---------------------------------------------------

    for entity, meta in entity_lookup.items():

        if meta.get("entity_type") != "protocol":
            continue

        chain = meta.get("chain")

        if chain:

            _add_edge(
                graph,
                entity,
                chain.upper(),
                "protocol_chain"
            )


    # ---------------------------------------------------
    # Signals → Entities
    # ---------------------------------------------------

    for s in signals:

        s = _safe_dict(s)

        entity = _safe_str(s.get("entity")).upper()
        source = _safe_str(s.get("source")).upper()

        if entity and source:

            _add_edge(
                graph,
                entity,
                source,
                "entity_signal_source"
            )


    # ---------------------------------------------------
    # Clusters
    # ---------------------------------------------------

    for c in clusters:

        c = _safe_dict(c)

        entity = _safe_str(c.get("entity")).upper()
        cluster_id = _safe_str(c.get("cluster_id"))

        if entity and cluster_id:

            _add_edge(
                graph,
                entity,
                cluster_id,
                "entity_cluster"
            )


    # ---------------------------------------------------
    # Narratives
    # ---------------------------------------------------

    for n in narratives:

        n = _safe_dict(n)

        narrative_type = _safe_str(n.get("narrative_type"))

        for entity in _safe_list(n.get("entities")):

            entity = _safe_str(entity).upper()

            if entity and narrative_type:

                _add_edge(
                    graph,
                    entity,
                    narrative_type,
                    "entity_narrative"
                )


    # ---------------------------------------------------
    # Correlations
    # ---------------------------------------------------

    for c in correlations:

        c = _safe_dict(c)

        corr_type = _safe_str(c.get("correlation_type"))

        for entity in _safe_list(c.get("entities")):

            entity = _safe_str(entity).upper()

            if entity and corr_type:

                _add_edge(
                    graph,
                    entity,
                    corr_type,
                    "entity_correlation"
                )


    graph = _unique_preserve(graph)

    # ---------------------------------------------------
    # Summary
    # ---------------------------------------------------

    relation_counts = defaultdict(int)

    entities = set()

    for e in graph:

        relation_counts[e["relation"]] += 1

        entities.add(e["source"])
        entities.add(e["target"])


    summary = {

        "node_count": len(entities),

        "edge_count": len(graph),

        "relation_counts": dict(relation_counts),

        "top_relations": sorted(
            relation_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
    }


    # ---------------------------------------------------
    # Alerts
    # ---------------------------------------------------

    alerts = []

    if relation_counts.get("entity_narrative", 0) > 20:

        alerts.append({
            "type": "narrative_density",
            "severity": "medium",
            "title": "Large narrative network detected"
        })


    if relation_counts.get("entity_cluster", 0) > 50:

        alerts.append({
            "type": "cluster_density",
            "severity": "medium",
            "title": "Entity cluster network expanding"
        })


    # ---------------------------------------------------
    # Endpoints
    # ---------------------------------------------------

    endpoints = {

        "entity_graph": "/api/toknclaw/entities/graph",

        "entity_graph_summary": "/api/toknclaw/entities/graph/summary",

        "entity_graph_alerts": "/api/toknclaw/entities/graph/alerts"
    }


    return {

        "entity_relationship_graph": graph,

        "entity_relationship_summary": summary,

        "entity_relationship_alerts": alerts,

        "entity_relationship_endpoints": endpoints
    }
