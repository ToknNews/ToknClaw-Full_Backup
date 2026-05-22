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
# MODULE: regime_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Dict, List, Any
from collections import defaultdict


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _sum_cluster_values(clusters):

    total = 0

    for c in clusters:
        try:
            total += float(c.get("total_value_usd") or 0)
        except Exception:
            pass

    return total


# -------------------------------------------------------
# Sector Scoring
# -------------------------------------------------------

def _compute_sector_weights(snapshot):

    clusters = _safe_list(snapshot.get("clusters"))

    sector_scores = defaultdict(float)

    for c in clusters:

        ctype = str(c.get("cluster_type") or "")
        value = float(c.get("total_value_usd") or 0)

        if ctype in {"protocol_tvl", "protocol_revenue", "protocol_fees"}:
            sector_scores["defi"] += value + 1

        elif ctype == "whale_activity":
            sector_scores["onchain"] += value + 1

        elif ctype == "retail_narrative":
            sector_scores["retail"] += 1

        elif ctype == "news_theme":
            sector_scores["news"] += 1

    total = sum(sector_scores.values()) or 1

    weights = {}

    for sector, score in sector_scores.items():
        weights[sector] = round(score / total, 3)

    return weights


# -------------------------------------------------------
# Narrative Alignment
# -------------------------------------------------------

def _narrative_alignment(snapshot):

    correlations = _safe_list(snapshot.get("narrative_correlations"))

    if len(correlations) == 0:
        return "none"

    if len(correlations) == 1:
        return "aligned"

    if len(correlations) <= 3:
        return "mixed"

    return "fragmented"


# -------------------------------------------------------
# Regime Classification
# -------------------------------------------------------

def _classify_market_regime(snapshot):

    correlations = _safe_list(snapshot.get("narrative_correlations"))
    retail = _safe_dict(snapshot.get("retail_pulse"))
    metrics = _safe_dict(snapshot.get("metrics"))

    retail_sentiment = str(retail.get("retail_sentiment") or "neutral").lower()

    whale_flow = float(metrics.get("whale_activity_usd") or 0)

    defi_corr = any(
        c.get("correlation_type") == "defi_capital_rotation"
        for c in correlations
    )

    retail_corr = any(
        c.get("correlation_type") == "risk_on_speculation_cycle"
        for c in correlations
    )

    inst_corr = any(
        c.get("correlation_type") == "institutional_accumulation"
        for c in correlations
    )

    if defi_corr and inst_corr:
        return "defi_expansion_cycle"

    if retail_corr and retail_sentiment == "risk_on":
        return "retail_speculation_cycle"

    if whale_flow > 500_000_000:
        return "institutional_accumulation_phase"

    return "mixed_transition"


# -------------------------------------------------------
# Liquidity Regime
# -------------------------------------------------------

def _liquidity_regime(snapshot):

    metrics = _safe_dict(snapshot.get("metrics"))

    whale = float(metrics.get("whale_activity_usd") or 0)
    inflow = float(metrics.get("exchange_inflows_usd") or 0)
    liqs = float(metrics.get("defi_liquidations_usd") or 0)

    if whale > 500_000_000 and inflow == 0:
        return "capital_rotation"

    if liqs > 100_000_000:
        return "liquidation_pressure"

    if whale > 300_000_000:
        return "institutional_flow"

    return "balanced"


# -------------------------------------------------------
# Broadcast Bias
# -------------------------------------------------------

def _broadcast_bias(regime):

    mapping = {
        "defi_expansion_cycle": "bullish",
        "retail_speculation_cycle": "bullish",
        "institutional_accumulation_phase": "bullish",
        "mixed_transition": "neutral",
        "liquidation_pressure": "bearish"
    }

    return mapping.get(regime, "neutral")


# -------------------------------------------------------
# Dominant Narrative
# -------------------------------------------------------

def _dominant_narrative(snapshot):

    correlations = _safe_list(snapshot.get("narrative_correlations"))

    if not correlations:
        return None

    return correlations[0].get("correlation_type")


# -------------------------------------------------------
# Dominant Entities
# -------------------------------------------------------

def _dominant_entities(snapshot):

    correlations = _safe_list(snapshot.get("narrative_correlations"))

    entities = []

    for c in correlations[:3]:
        entities.extend(c.get("entities") or [])

    seen = set()
    out = []

    for e in entities:
        if e not in seen:
            seen.add(e)
            out.append(e)

    return out[:6]


# -------------------------------------------------------
# Regime Alerts
# -------------------------------------------------------

def _detect_regime_alerts(snapshot, regime):

    alerts = []

    arcs = _safe_list(snapshot.get("narrative_arcs"))

    for arc in arcs:

        persistence = float(arc.get("peak_persistence_score") or 0)

        if persistence > 0.8:

            alerts.append({
                "type": "persistent_narrative",
                "title": arc.get("title"),
                "severity": "high"
            })

    if regime == "mixed_transition":

        alerts.append({
            "type": "regime_uncertainty",
            "title": "Market signals are mixed",
            "severity": "medium"
        })

    if regime == "defi_expansion_cycle":

        alerts.append({
            "type": "defi_expansion",
            "title": "DeFi capital formation regime detected",
            "severity": "high"
        })

    return alerts


# -------------------------------------------------------
# Public Engine
# -------------------------------------------------------

def build_market_regime(snapshot: Dict[str, Any]):

    snapshot = _safe_dict(snapshot)

    sector_weights = _compute_sector_weights(snapshot)

    regime = _classify_market_regime(snapshot)

    liquidity = _liquidity_regime(snapshot)

    broadcast_bias = _broadcast_bias(regime)

    alignment = _narrative_alignment(snapshot)

    dominant_narrative = _dominant_narrative(snapshot)

    dominant_entities = _dominant_entities(snapshot)

    alerts = _detect_regime_alerts(snapshot, regime)

    confidence = round(max(sector_weights.values() or [0]), 2)

    return {

        "name": regime,

        "liquidity_regime": liquidity,

        "sector_weights": sector_weights,

        "narrative_alignment": alignment,

        "dominant_narrative": dominant_narrative,

        "dominant_entities": dominant_entities,

        "broadcast_bias": broadcast_bias,

        "confidence": confidence,

        "alerts": alerts
    }
