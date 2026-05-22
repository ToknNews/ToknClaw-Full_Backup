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
# MODULE: liquidity_rotation_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Dict, List, Any
from collections import defaultdict


# -------------------------------------------------------
# helpers
# -------------------------------------------------------

def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def _clamp(v, low=0.0, high=1.0):
    return max(low, min(high, v))


# -------------------------------------------------------
# sector aggregation
# -------------------------------------------------------

def _aggregate_sector_flows(snapshot):

    clusters = _safe_list(snapshot.get("clusters"))

    sector_flow = defaultdict(float)
    entity_map = defaultdict(list)

    for c in clusters:

        c = _safe_dict(c)

        sector = str(c.get("sector") or "unknown")
        entity = c.get("entity")

        value = _safe_float(c.get("total_value_usd"))

        if value == 0:
            value = 1

        sector_flow[sector] += value

        if entity:
            entity_map[sector].append(entity)

    return sector_flow, entity_map


# -------------------------------------------------------
# velocity boost
# -------------------------------------------------------

def _apply_velocity_boost(snapshot, sector_scores):

    velocity = _safe_dict(snapshot.get("signal_velocity_summary"))

    top_entity = velocity.get("top_entity")

    if not top_entity:
        return sector_scores

    entity_intel = _safe_dict(snapshot.get("entity_intelligence"))

    record = _safe_dict(entity_intel.get(top_entity))

    sectors = record.get("sectors") or []

    for s in sectors:
        if s in sector_scores:
            sector_scores[s] *= 1.15

    return sector_scores


# -------------------------------------------------------
# institutional bias
# -------------------------------------------------------

def _institutional_bias(snapshot, sector_scores):

    inst = _safe_dict(snapshot.get("institutional_flow_summary"))

    regime = str(inst.get("regime") or "")

    if regime == "institutional_rotation":

        for s in sector_scores:
            sector_scores[s] *= 1.05

    if regime == "institutional_risk_off":

        for s in sector_scores:
            if s in {"defi", "retail"}:
                sector_scores[s] *= 0.9

    return sector_scores


# -------------------------------------------------------
# macro bias
# -------------------------------------------------------

def _macro_bias(snapshot, sector_scores):

    macro = _safe_dict(snapshot.get("macro_liquidity_summary"))

    regime = str(macro.get("regime") or "")

    if regime == "liquidity_expansion":

        for s in sector_scores:
            sector_scores[s] *= 1.1

    if regime == "liquidity_contraction":

        for s in sector_scores:
            sector_scores[s] *= 0.85

    return sector_scores


# -------------------------------------------------------
# normalize sector weights
# -------------------------------------------------------

def _normalize(sector_scores):

    total = sum(sector_scores.values()) or 1

    weights = {}

    for sector, value in sector_scores.items():

        weights[sector] = round(value / total, 4)

    return weights


# -------------------------------------------------------
# entity ranking
# -------------------------------------------------------

def _rank_entities(entity_map, sector_weights):

    rows = []

    for sector, entities in entity_map.items():

        weight = sector_weights.get(sector, 0)

        for e in entities:

            rows.append({
                "entity": e,
                "sector": sector,
                "rotation_weight": round(weight, 4)
            })

    rows.sort(key=lambda x: x["rotation_weight"], reverse=True)

    return rows[:50]


# -------------------------------------------------------
# alerts
# -------------------------------------------------------

def _build_alerts(sector_weights):

    alerts = []

    for sector, weight in sector_weights.items():

        if weight > 0.4:

            alerts.append({
                "type": "sector_rotation",
                "sector": sector,
                "severity": "high",
                "title": f"Liquidity rotating heavily into {sector}"
            })

        elif weight > 0.25:

            alerts.append({
                "type": "sector_accumulation",
                "sector": sector,
                "severity": "medium",
                "title": f"Liquidity building in {sector}"
            })

    return alerts


# -------------------------------------------------------
# endpoint manifest
# -------------------------------------------------------

def _endpoint_manifest():

    return {

        "liquidity_rotation": "/api/toknclaw/liquidity-rotation",
        "liquidity_rotation_summary": "/api/toknclaw/liquidity-rotation/summary",
        "liquidity_rotation_flows": "/api/toknclaw/liquidity-rotation/flows",
        "liquidity_rotation_entities": "/api/toknclaw/liquidity-rotation/entities",
        "liquidity_rotation_alerts": "/api/toknclaw/liquidity-rotation/alerts",
    }


# -------------------------------------------------------
# main engine
# -------------------------------------------------------

def build_liquidity_rotation(snapshot: Dict[str, Any]):

    snapshot = _safe_dict(snapshot)

    sector_scores, entity_map = _aggregate_sector_flows(snapshot)

    sector_scores = _apply_velocity_boost(snapshot, sector_scores)

    sector_scores = _institutional_bias(snapshot, sector_scores)

    sector_scores = _macro_bias(snapshot, sector_scores)

    sector_weights = _normalize(sector_scores)

    entity_rows = _rank_entities(entity_map, sector_weights)

    alerts = _build_alerts(sector_weights)

    summary = {

        "dominant_sector": max(sector_weights, key=sector_weights.get) if sector_weights else None,

        "dominant_weight": sector_weights.get(
            max(sector_weights, key=sector_weights.get),
            0
        ) if sector_weights else 0,

        "tracked_sectors": len(sector_weights),

        "alert_count": len(alerts)
    }

    return {

        "liquidity_rotation": {
            "sector_weights": sector_weights,
            "entities": entity_rows
        },

        "liquidity_rotation_summary": summary,

        "liquidity_rotation_flows": sector_weights,

        "liquidity_rotation_entities": entity_rows,

        "liquidity_rotation_alerts": alerts,

        "liquidity_rotation_endpoints": _endpoint_manifest()
    }
