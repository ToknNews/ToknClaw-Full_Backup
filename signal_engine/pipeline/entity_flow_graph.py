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
# MODULE: entity_flow_graph
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
entity_flow_graph.py

ToknClaw Entity Flow Graph Engine

Purpose
-------
Construct a directional flow graph across entities, sectors, narratives,
macro state, institutional structure, and stress propagation.

Outputs
-------
snapshot["entity_flow_graph"]
snapshot["entity_flow_nodes"]
snapshot["entity_flow_edges"]
snapshot["entity_flow_hotspots"]
snapshot["entity_flow_routes"]
snapshot["entity_flow_summary"]
snapshot["entity_flow_alerts"]
snapshot["entity_flow_endpoints"]

Design Goals
------------
• deterministic
• directional
• capital-flow aware
• snapshot-safe
• future graph database compatible
• future API compatible
• resilient to incomplete classification
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict


EXPORT_DIR = Path("/opt/toknclaw/data/graphs")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _now_ts() -> int:
    return int(time.time())


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

STABLECOINS = {
    "USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "USDT0"
}

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

INSTITUTIONAL_STYLE_ENTITIES = {
    "BLACKROCK",
    "FIDELITY",
    "ARK",
    "GRAYSCALE",
    "COINBASE PRIME",
    "STRATEGY",
    "MICROSTRATEGY",
    "BITWISE",
    "VANECK",
    "FRANKLIN",
}

WHALE_NODE = "WHALE_CAPITAL"
MACRO_NODE = "MACRO_LIQUIDITY"
STRESS_NODE = "MARKET_STRESS"
INSTITUTIONAL_NODE = "INSTITUTIONAL_CAPITAL"
RETAIL_NODE = "RETAIL_FLOW"

SYSTEM_NODE_META = {
    WHALE_NODE: {"node_type": "system_flow", "sector": "onchain", "category": "whale_capital"},
    MACRO_NODE: {"node_type": "system_flow", "sector": "macro", "category": "macro_liquidity"},
    STRESS_NODE: {"node_type": "system_flow", "sector": "risk", "category": "market_stress"},
    INSTITUTIONAL_NODE: {"node_type": "system_flow", "sector": "institutional", "category": "institutional_capital"},
    RETAIL_NODE: {"node_type": "system_flow", "sector": "retail", "category": "retail_flow"},
}


# -------------------------------------------------------
# Snapshot helpers
# -------------------------------------------------------

def _clusters(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(c) for c in _safe_list(snapshot.get("clusters"))]


def _signals(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(s) for s in _safe_list(snapshot.get("signals"))]


def _narratives(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(n) for n in _safe_list(snapshot.get("narratives"))]


def _correlations(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_safe_dict(c) for c in _safe_list(snapshot.get("narrative_correlations"))]


def _entity_class_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}

    for row in _safe_list(snapshot.get("entity_classification")):
        row = _safe_dict(row)
        entity = _safe_str(row.get("entity")).upper()
        if entity:
            out[entity] = row

    return out


def _entity_intel_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = _safe_dict(snapshot.get("entity_intelligence"))
    return {str(k).upper(): _safe_dict(v) for k, v in raw.items()}


def _quant_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}

    for row in _safe_list(snapshot.get("quant_factors")):
        row = _safe_dict(row)
        entity = _safe_str(row.get("entity")).upper()
        if entity:
            out[entity] = row

    return out


def _trade_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}

    for row in _safe_list(snapshot.get("trade_signals")):
        row = _safe_dict(row)
        entity = _safe_str(row.get("entity")).upper()
        if entity:
            out[entity] = row

    return out


# -------------------------------------------------------
# Node inference
# -------------------------------------------------------

def _infer_node_meta(
    node: str,
    entity_class_map: Dict[str, Dict[str, Any]],
    entity_intel_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    node = _safe_str(node).upper()

    if node in SYSTEM_NODE_META:
        base = dict(SYSTEM_NODE_META[node])
        base["node"] = node
        base["classification_confidence"] = 1.0
        return base

    row = _safe_dict(entity_class_map.get(node))
    intel = _safe_dict(entity_intel_map.get(node))

    if row:
        return {
            "node": node,
            "node_type": row.get("entity_type") or "unknown",
            "sector": row.get("sector"),
            "category": row.get("category"),
            "chain": row.get("chain"),
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "classification_confidence": round(_safe_float(row.get("classification_confidence"), 0.0), 2),
            "classification_source": row.get("classification_source"),
            "aliases": row.get("aliases") or [],
            "supporting_sources": intel.get("supporting_sources") or [],
        }

    if node in STABLECOINS:
        return {
            "node": node,
            "node_type": "stablecoin",
            "sector": "stablecoin",
            "category": "stablecoin",
            "classification_confidence": 0.90,
            "classification_source": "flow_graph_fallback",
        }

    if node in EXCHANGE_STYLE_ENTITIES:
        return {
            "node": node,
            "node_type": "exchange",
            "sector": "exchange",
            "category": "cex",
            "classification_confidence": 0.88,
            "classification_source": "flow_graph_fallback",
        }

    if node in INSTITUTIONAL_STYLE_ENTITIES:
        return {
            "node": node,
            "node_type": "institutional",
            "sector": "institutional",
            "category": "issuer_or_custody",
            "classification_confidence": 0.85,
            "classification_source": "flow_graph_fallback",
        }

    return {
        "node": node,
        "node_type": "unknown",
        "sector": "unknown",
        "category": None,
        "classification_confidence": 0.30,
        "classification_source": "flow_graph_fallback",
    }


# -------------------------------------------------------
# Edge aggregation
# -------------------------------------------------------

def _edge_key(source: str, target: str, relation: str) -> tuple[str, str, str]:
    return (_safe_str(source).upper(), _safe_str(target).upper(), _safe_str(relation))


def _merge_metadata(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    existing = _safe_dict(existing)
    incoming = _safe_dict(incoming)

    merged = dict(existing)

    for key, value in incoming.items():
        if value in [None, "", [], {}]:
            continue

        if key not in merged or merged[key] in [None, "", [], {}]:
            merged[key] = value
            continue

        if isinstance(merged[key], list) or isinstance(value, list):
            merged[key] = _unique_preserve(_safe_list(merged[key]) + _safe_list(value))
            continue

        if merged[key] == value:
            continue

    return merged


def _add_edge(
    edge_map: Dict[tuple[str, str, str], Dict[str, Any]],
    source: str,
    target: str,
    relation: str,
    weight: float = 0.0,
    confidence: float = 0.5,
    metadata: Dict[str, Any] | None = None,
):
    source = _safe_str(source).upper()
    target = _safe_str(target).upper()
    relation = _safe_str(relation)

    if not source or not target or not relation or source == target:
        return

    key = _edge_key(source, target, relation)
    incoming_weight = _clamp(weight)
    incoming_confidence = _clamp(confidence)

    if key not in edge_map:
        edge_map[key] = {
            "source": source,
            "target": target,
            "relation": relation,
            "weight": incoming_weight,
            "confidence": incoming_confidence,
            "observation_count": 1,
            "metadata": metadata or {},
        }
        return

    edge_map[key]["weight"] = round(_clamp(edge_map[key]["weight"] + incoming_weight), 4)
    edge_map[key]["confidence"] = round(_clamp(max(edge_map[key]["confidence"], incoming_confidence)), 4)
    edge_map[key]["observation_count"] += 1
    edge_map[key]["metadata"] = _merge_metadata(edge_map[key]["metadata"], metadata or {})


# -------------------------------------------------------
# Edge constructors
# -------------------------------------------------------

def _build_stablecoin_exchange_edges(snapshot: Dict[str, Any], edge_map: Dict[tuple[str, str, str], Dict[str, Any]]):
    for cluster in _clusters(snapshot):
        entity = _safe_str(cluster.get("entity")).upper()
        value = _safe_float(cluster.get("total_value_usd"), 0.0)
        ctype = _safe_str(cluster.get("cluster_type"))

        if entity not in STABLECOINS:
            continue

        weight = _clamp(value / 2_000_000_000)
        confidence = 0.72 if value > 0 else 0.45

        for exchange in EXCHANGE_STYLE_ENTITIES:
            _add_edge(
                edge_map,
                entity,
                exchange,
                "stablecoin_exchange_flow",
                weight,
                confidence,
                {
                    "cluster_type": ctype,
                    "inferred": True,
                    "value_usd": round(value, 2),
                },
            )


def _build_exchange_asset_edges(
    snapshot: Dict[str, Any],
    edge_map: Dict[tuple[str, str, str], Dict[str, Any]],
    entity_class_map: Dict[str, Dict[str, Any]],
):
    for cluster in _clusters(snapshot):
        entity = _safe_str(cluster.get("entity")).upper()
        value = _safe_float(cluster.get("total_value_usd"), 0.0)
        ctype = _safe_str(cluster.get("cluster_type"))

        if not entity or entity in EXCHANGE_STYLE_ENTITIES:
            continue

        meta = _safe_dict(entity_class_map.get(entity))
        entity_type = _safe_str(meta.get("entity_type"))

        if entity_type not in {"token", "stablecoin", "wrapped_asset", "protocol", "exchange", "institutional", "unknown"}:
            continue

        weight = _clamp(value / 10_000_000_000)
        confidence = 0.58 if value > 0 else 0.35

        for exchange in EXCHANGE_STYLE_ENTITIES:
            _add_edge(
                edge_map,
                exchange,
                entity,
                "exchange_asset_flow",
                weight,
                confidence,
                {
                    "cluster_type": ctype,
                    "inferred": True,
                    "value_usd": round(value, 2),
                },
            )


def _build_whale_edges(snapshot: Dict[str, Any], edge_map: Dict[tuple[str, str, str], Dict[str, Any]]):
    for cluster in _clusters(snapshot):
        entity = _safe_str(cluster.get("entity")).upper()
        ctype = _safe_str(cluster.get("cluster_type"))
        value = _safe_float(cluster.get("total_value_usd"), 0.0)

        if ctype != "whale_activity" or not entity:
            continue

        _add_edge(
            edge_map,
            WHALE_NODE,
            entity,
            "whale_entity_flow",
            _clamp(value / 2_000_000_000),
            0.88,
            {
                "cluster_type": ctype,
                "value_usd": round(value, 2),
            },
        )


def _build_institutional_edges(snapshot: Dict[str, Any], edge_map: Dict[tuple[str, str, str], Dict[str, Any]]):
    summary = _safe_dict(snapshot.get("institutional_flow_summary"))
    regime = _safe_str(summary.get("regime"))

    if regime:
        _add_edge(
            edge_map,
            INSTITUTIONAL_NODE,
            regime,
            "institutional_regime_flow",
            0.65,
            0.75,
            {"summary": True},
        )

    for row in _safe_list(snapshot.get("institutional_flow_entities")):
        row = _safe_dict(row)
        entity = _safe_str(row.get("entity")).upper()
        score = _safe_float(row.get("institutional_flow_score"), 0.0)

        if not entity:
            continue

        _add_edge(
            edge_map,
            INSTITUTIONAL_NODE,
            entity,
            "institutional_entity_flow",
            score,
            max(0.50, score),
            {
                "entity_type": row.get("entity_type"),
                "total_value_usd": row.get("total_value_usd"),
            },
        )


def _build_macro_edges(snapshot: Dict[str, Any], edge_map: Dict[tuple[str, str, str], Dict[str, Any]]):
    summary = _safe_dict(snapshot.get("macro_liquidity_summary"))
    regime = _safe_str(summary.get("regime"))

    if regime:
        _add_edge(
            edge_map,
            MACRO_NODE,
            regime,
            "macro_regime_flow",
            0.60,
            0.72,
            {"summary": True},
        )

    for row in _safe_list(snapshot.get("cross_asset_intelligence")):
        row = _safe_dict(row)
        relation_type = _safe_str(row.get("relation_type"))
        confidence = _safe_float(row.get("confidence"), 0.0)

        if not relation_type:
            continue

        _add_edge(
            edge_map,
            MACRO_NODE,
            relation_type,
            "macro_cross_asset_flow",
            confidence,
            confidence,
            {"relation": relation_type},
        )

        for entity in _safe_list(row.get("entities")):
            entity = _safe_str(entity).upper()
            if entity:
                _add_edge(
                    edge_map,
                    MACRO_NODE,
                    entity,
                    "macro_entity_flow",
                    confidence * 0.75,
                    confidence,
                    {"relation": relation_type},
                )


def _build_stress_edges(snapshot: Dict[str, Any], edge_map: Dict[tuple[str, str, str], Dict[str, Any]]):
    summary = _safe_dict(snapshot.get("market_stress_summary"))
    regime = _safe_str(summary.get("regime"))

    if regime:
        _add_edge(
            edge_map,
            STRESS_NODE,
            regime,
            "stress_regime_flow",
            0.70,
            0.85,
            {"summary": True},
        )

    for row in _safe_list(snapshot.get("market_stress_entities")):
        row = _safe_dict(row)
        entity = _safe_str(row.get("entity")).upper()
        score = _safe_float(row.get("entity_stress_score"), 0.0)

        if not entity:
            continue

        _add_edge(
            edge_map,
            STRESS_NODE,
            entity,
            "stress_entity_flow",
            score,
            max(0.55, score),
            {"cluster_types": row.get("cluster_types") or []},
        )


def _build_retail_edges(snapshot: Dict[str, Any], edge_map: Dict[tuple[str, str, str], Dict[str, Any]]):
    retail_pulse = _safe_dict(snapshot.get("retail_pulse"))

    if bool(retail_pulse.get("memecoin_rotation")):
        _add_edge(
            edge_map,
            RETAIL_NODE,
            "MEMECOIN_ROTATION",
            "retail_regime_flow",
            0.65,
            0.72,
            {"signal": "memecoin_rotation"},
        )

    sentiment = _safe_str(retail_pulse.get("retail_sentiment")).upper()
    if sentiment:
        _add_edge(
            edge_map,
            RETAIL_NODE,
            sentiment,
            "retail_sentiment_flow",
            0.45,
            0.60,
            {"summary": True},
        )

    for cluster in _clusters(snapshot):
        entity = _safe_str(cluster.get("entity")).upper()
        ctype = _safe_str(cluster.get("cluster_type"))
        value = _safe_float(cluster.get("total_value_usd"), 0.0)

        if ctype != "retail_narrative" or not entity:
            continue

        _add_edge(
            edge_map,
            RETAIL_NODE,
            entity,
            "retail_entity_flow",
            _clamp(0.35 + value / 500_000_000),
            0.68,
            {"cluster_type": ctype},
        )


def _build_narrative_edges(snapshot: Dict[str, Any], edge_map: Dict[tuple[str, str, str], Dict[str, Any]]):
    for narrative in _narratives(snapshot):
        narrative = _safe_dict(narrative)
        ntype = _safe_str(narrative.get("narrative_type"))
        confidence = _safe_float(narrative.get("confidence"), 0.0)

        if not ntype:
            continue

        for entity in _safe_list(narrative.get("entities")):
            entity = _safe_str(entity).upper()
            if entity:
                _add_edge(
                    edge_map,
                    entity,
                    ntype,
                    "entity_narrative_flow",
                    confidence,
                    confidence,
                    {"title": narrative.get("title")},
                )

    for corr in _correlations(snapshot):
        corr = _safe_dict(corr)
        ctype = _safe_str(corr.get("correlation_type"))
        confidence = _safe_float(corr.get("confidence"), 0.0)

        if not ctype:
            continue

        for entity in _safe_list(corr.get("entities")):
            entity = _safe_str(entity).upper()
            if entity:
                _add_edge(
                    edge_map,
                    entity,
                    ctype,
                    "entity_correlation_flow",
                    confidence,
                    confidence,
                    {"broadcast_relevance": corr.get("broadcast_relevance")},
                )


def _build_quant_trade_edges(snapshot: Dict[str, Any], edge_map: Dict[tuple[str, str, str], Dict[str, Any]]):
    quant_map = _quant_map(snapshot)
    trade_map = _trade_map(snapshot)

    for entity, row in quant_map.items():
        row = _safe_dict(row)
        composite = _safe_float(row.get("composite_factor"), 0.0)
        bucket = _safe_str(row.get("regime_bucket")).upper()

        if bucket:
            _add_edge(
                edge_map,
                entity,
                bucket,
                "entity_quant_bucket_flow",
                composite,
                max(0.45, composite),
                {"composite_factor": composite},
            )

    for entity, row in trade_map.items():
        row = _safe_dict(row)
        direction = _safe_str(row.get("direction")).upper()
        confidence = _safe_float(row.get("confidence"), 0.0)

        if direction:
            _add_edge(
                edge_map,
                entity,
                direction,
                "entity_trade_signal_flow",
                confidence,
                confidence,
                {"signal_reasons": row.get("signal_reasons") or []},
            )


# -------------------------------------------------------
# Nodes / routes / hotspots
# -------------------------------------------------------

def _build_nodes(
    edges: List[Dict[str, Any]],
    entity_class_map: Dict[str, Dict[str, Any]],
    entity_intel_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    node_names = set()

    for edge in edges:
        node_names.add(_safe_str(edge.get("source")).upper())
        node_names.add(_safe_str(edge.get("target")).upper())

    nodes = []
    for node in sorted(node_names):
        nodes.append(_infer_node_meta(node, entity_class_map, entity_intel_map))

    return nodes


def _build_hotspots(edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    inbound = defaultdict(float)
    outbound = defaultdict(float)
    relation_counts = defaultdict(int)

    for edge in edges:
        source = _safe_str(edge.get("source")).upper()
        target = _safe_str(edge.get("target")).upper()
        weight = _safe_float(edge.get("weight"), 0.0)

        outbound[source] += weight
        inbound[target] += weight
        relation_counts[source] += 1
        relation_counts[target] += 1

    nodes = set(list(inbound.keys()) + list(outbound.keys()))
    rows = []

    for node in nodes:
        inbound_weight = round(inbound[node], 4)
        outbound_weight = round(outbound[node], 4)
        total_activity = round(inbound[node] + outbound[node], 4)

        if outbound_weight > inbound_weight * 1.35:
            hotspot_type = "source_dominant"
        elif inbound_weight > outbound_weight * 1.35:
            hotspot_type = "sink_dominant"
        else:
            hotspot_type = "balanced_router"

        rows.append({
            "node": node,
            "inbound_weight": inbound_weight,
            "outbound_weight": outbound_weight,
            "relationship_count": relation_counts[node],
            "total_activity": total_activity,
            "hotspot_type": hotspot_type,
        })

    rows.sort(
        key=lambda x: (
            x.get("total_activity", 0.0),
            x.get("relationship_count", 0),
            x.get("node", ""),
        ),
        reverse=True,
    )

    return rows[:100]


def _build_routes(edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    route_map = defaultdict(lambda: {"count": 0, "weight": 0.0})

    for edge in edges:
        relation = _safe_str(edge.get("relation"))
        route_map[relation]["count"] += 1
        route_map[relation]["weight"] += _safe_float(edge.get("weight"), 0.0)

    rows = []
    for relation, stats in route_map.items():
        rows.append({
            "relation": relation,
            "edge_count": stats["count"],
            "total_weight": round(stats["weight"], 4),
        })

    rows.sort(
        key=lambda x: (
            x.get("total_weight", 0.0),
            x.get("edge_count", 0),
            x.get("relation", ""),
        ),
        reverse=True,
    )

    return rows


def _build_summary(edges: List[Dict[str, Any]], nodes: List[Dict[str, Any]], hotspots: List[Dict[str, Any]], routes: List[Dict[str, Any]]) -> Dict[str, Any]:
    relation_counts = defaultdict(int)

    for edge in edges:
        relation_counts[_safe_str(edge.get("relation"))] += 1

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "relation_counts": dict(relation_counts),
        "top_relations": sorted(
            relation_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10],
        "top_hotspot": hotspots[0]["node"] if hotspots else None,
        "top_hotspot_activity": hotspots[0]["total_activity"] if hotspots else 0.0,
        "top_route": routes[0]["relation"] if routes else None,
        "top_route_weight": routes[0]["total_weight"] if routes else 0.0,
    }


def _build_alerts(edges: List[Dict[str, Any]], hotspots: List[Dict[str, Any]], routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts = []

    if len(edges) > 150:
        alerts.append({
            "type": "flow_network_density",
            "severity": "medium",
            "title": "Entity flow network density is elevated",
        })

    if hotspots:
        top = hotspots[0]
        if _safe_float(top.get("total_activity"), 0.0) >= 3.0:
            alerts.append({
                "type": "flow_hotspot",
                "severity": "high",
                "node": top.get("node"),
                "title": f'{top.get("node")} is a dominant flow hotspot',
            })

    top_routes = {r["relation"]: r for r in routes[:10]}

    if "whale_entity_flow" in top_routes and _safe_float(top_routes["whale_entity_flow"].get("total_weight"), 0.0) >= 1.0:
        alerts.append({
            "type": "whale_flow_dispersion",
            "severity": "medium",
            "title": "Whale capital is dispersing across multiple entities",
        })

    if "stress_entity_flow" in top_routes and _safe_float(top_routes["stress_entity_flow"].get("total_weight"), 0.0) >= 1.0:
        alerts.append({
            "type": "stress_propagation",
            "severity": "high",
            "title": "Stress is propagating across multiple entities",
        })

    if "institutional_entity_flow" in top_routes and _safe_float(top_routes["institutional_entity_flow"].get("total_weight"), 0.0) >= 1.0:
        alerts.append({
            "type": "institutional_capital_concentration",
            "severity": "medium",
            "title": "Institutional capital concentration is rising",
        })

    return alerts[:25]


def _endpoint_manifest() -> Dict[str, str]:
    return {
        "entity_flow_graph": "/api/toknclaw/entities/flow-graph",
        "entity_flow_nodes": "/api/toknclaw/entities/flow-graph/nodes",
        "entity_flow_edges": "/api/toknclaw/entities/flow-graph/edges",
        "entity_flow_summary": "/api/toknclaw/entities/flow-graph/summary",
        "entity_flow_alerts": "/api/toknclaw/entities/flow-graph/alerts",
        "entity_flow_hotspots": "/api/toknclaw/entities/flow-graph/hotspots",
        "entity_flow_routes": "/api/toknclaw/entities/flow-graph/routes",
    }


# -------------------------------------------------------
# Export
# -------------------------------------------------------

def _write_export(payload: Dict[str, Any]) -> None:
    latest = EXPORT_DIR / "latest_entity_flow_graph.json"
    dated = EXPORT_DIR / f'entity_flow_graph_{int(time.time())}.json'

    text = json.dumps(payload, indent=2)
    latest.write_text(text)
    dated.write_text(text)


# -------------------------------------------------------
# Main engine
# -------------------------------------------------------

def build_entity_flow_graph(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    edge_map: Dict[tuple[str, str, str], Dict[str, Any]] = {}

    entity_class_map = _entity_class_map(snapshot)
    entity_intel_map = _entity_intel_map(snapshot)

    _build_stablecoin_exchange_edges(snapshot, edge_map)
    _build_exchange_asset_edges(snapshot, edge_map, entity_class_map)
    _build_whale_edges(snapshot, edge_map)
    _build_institutional_edges(snapshot, edge_map)
    _build_macro_edges(snapshot, edge_map)
    _build_stress_edges(snapshot, edge_map)
    _build_retail_edges(snapshot, edge_map)
    _build_narrative_edges(snapshot, edge_map)
    _build_quant_trade_edges(snapshot, edge_map)

    edges = list(edge_map.values())
    edges.sort(
        key=lambda x: (
            _safe_float(x.get("weight"), 0.0),
            _safe_float(x.get("confidence"), 0.0),
            _safe_str(x.get("relation")),
            _safe_str(x.get("source")),
            _safe_str(x.get("target")),
        ),
        reverse=True,
    )

    nodes = _build_nodes(edges, entity_class_map, entity_intel_map)
    hotspots = _build_hotspots(edges)
    routes = _build_routes(edges)
    summary = _build_summary(edges, nodes, hotspots, routes)
    alerts = _build_alerts(edges, hotspots, routes)

    payload = {
        "generated_at": _now_ts(),
        "entity_flow_graph": edges,
        "entity_flow_nodes": nodes,
        "entity_flow_edges": edges,
        "entity_flow_hotspots": hotspots,
        "entity_flow_routes": routes,
        "entity_flow_summary": summary,
        "entity_flow_alerts": alerts,
        "entity_flow_endpoints": _endpoint_manifest(),
    }

    _write_export(payload)

    return payload
