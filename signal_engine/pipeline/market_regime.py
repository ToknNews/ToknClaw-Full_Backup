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
# MODULE: market_regime
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Any, Dict, List


HIGH_PRIORITY = {"high"}
MEDIUM_OR_HIGH = {"medium", "high"}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _cluster_type_counts(cluster_analysis: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for item in cluster_analysis:
        ctype = str(item.get("cluster_type") or "unknown")
        counts[ctype] = counts.get(ctype, 0) + 1

    return counts


def _high_priority_clusters(cluster_analysis: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        item for item in cluster_analysis
        if str(item.get("broadcast_priority") or "").lower() in HIGH_PRIORITY
    ]


def _medium_or_high_clusters(cluster_analysis: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        item for item in cluster_analysis
        if str(item.get("broadcast_priority") or "").lower() in MEDIUM_OR_HIGH
    ]


def build_narrative_events(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    cluster_analysis = _safe_list(snapshot.get("cluster_analysis"))
    retail_pulse = snapshot.get("retail_pulse") or {}
    deltas = snapshot.get("deltas") or {}

    counts = _cluster_type_counts(cluster_analysis)
    events: List[Dict[str, Any]] = []

    whale_clusters = counts.get("whale_activity", 0)
    protocol_tvl_clusters = counts.get("protocol_tvl", 0) + counts.get("protocol_tvl_growth", 0) + counts.get("protocol_tvl_spike", 0)
    protocol_rev_clusters = counts.get("protocol_revenue", 0) + counts.get("protocol_fees", 0)
    retail_clusters = counts.get("retail_narrative", 0)

    whale_delta = ((deltas.get("whale_activity_usd") or {}).get("percent_change"))
    retail_sentiment = str(retail_pulse.get("retail_sentiment") or "unknown").lower()
    memecoin_rotation = bool(retail_pulse.get("memecoin_rotation"))

    if whale_clusters >= 2:
        direction = "neutral"
        if isinstance(whale_delta, (int, float)):
            if whale_delta > 10:
                direction = "rising"
            elif whale_delta < -10:
                direction = "falling"

        events.append({
            "event_type": "whale_repositioning",
            "confidence": 0.82 if direction == "neutral" else 0.87,
            "direction": direction,
            "summary": "Large-holder positioning is active across the market.",
            "evidence": whale_clusters,
        })

    if protocol_tvl_clusters >= 2:
        events.append({
            "event_type": "defi_capital_formation",
            "confidence": 0.86,
            "direction": "rising",
            "summary": "Capital appears to be concentrating in DeFi protocols.",
            "evidence": protocol_tvl_clusters,
        })

    if protocol_rev_clusters >= 1:
        events.append({
            "event_type": "protocol_business_strength",
            "confidence": 0.80,
            "direction": "rising",
            "summary": "Protocol revenue and fee signals suggest business activity is surfacing.",
            "evidence": protocol_rev_clusters,
        })

    if retail_clusters >= 2 or memecoin_rotation:
        events.append({
            "event_type": "retail_speculation",
            "confidence": 0.84 if retail_sentiment == "risk_on" else 0.76,
            "direction": retail_sentiment if retail_sentiment in {"risk_on", "risk_off"} else "neutral",
            "summary": "Retail narrative activity is building across social and memecoin flows.",
            "evidence": retail_clusters,
        })

    if retail_sentiment == "risk_on" and protocol_tvl_clusters >= 1:
        events.append({
            "event_type": "risk_on_rotation",
            "confidence": 0.83,
            "direction": "rising",
            "summary": "Speculative appetite and protocol growth are aligning in the same cycle.",
            "evidence": retail_clusters + protocol_tvl_clusters,
        })

    return events


def detect_market_regime(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    cluster_analysis = _safe_list(snapshot.get("cluster_analysis"))
    retail_pulse = snapshot.get("retail_pulse") or {}
    narrative_events = _safe_list(snapshot.get("narrative_events"))

    counts = _cluster_type_counts(cluster_analysis)
    high_priority = _high_priority_clusters(cluster_analysis)
    medium_or_high = _medium_or_high_clusters(cluster_analysis)

    retail_sentiment = str(retail_pulse.get("retail_sentiment") or "unknown").lower()
    memecoin_rotation = bool(retail_pulse.get("memecoin_rotation"))

    whale_clusters = counts.get("whale_activity", 0)
    protocol_tvl_clusters = counts.get("protocol_tvl", 0) + counts.get("protocol_tvl_growth", 0) + counts.get("protocol_tvl_spike", 0)
    protocol_rev_clusters = counts.get("protocol_revenue", 0) + counts.get("protocol_fees", 0)
    retail_clusters = counts.get("retail_narrative", 0)
    news_clusters = counts.get("news_theme", 0)

    regime = "mixed_transition"
    confidence = 0.62
    drivers: List[str] = []
    posture = "balanced"

    if whale_clusters >= 2:
        drivers.append("whale activity")
    if protocol_tvl_clusters >= 1:
        drivers.append("DeFi TVL concentration")
    if protocol_rev_clusters >= 1:
        drivers.append("protocol business signals")
    if retail_clusters >= 1:
        drivers.append("retail narrative")
    if news_clusters >= 1:
        drivers.append("news catalysts")

    if retail_sentiment == "risk_on" and memecoin_rotation and retail_clusters >= 2:
        regime = "speculative_risk_on"
        confidence = 0.84
        posture = "offensive"

    if protocol_tvl_clusters >= 2 and protocol_rev_clusters >= 1:
        regime = "defi_capital_formation"
        confidence = max(confidence, 0.86)
        posture = "constructive"

    if whale_clusters >= 2 and len(high_priority) >= 2 and retail_sentiment != "risk_on":
        regime = "institutional_repositioning"
        confidence = max(confidence, 0.85)
        posture = "selective"

    if retail_sentiment == "risk_on" and protocol_tvl_clusters >= 1 and whale_clusters >= 1:
        regime = "broad_risk_on_rotation"
        confidence = max(confidence, 0.88)
        posture = "offensive"

    if len(narrative_events) == 0 and len(medium_or_high) <= 1:
        regime = "low_signal_mixed"
        confidence = 0.55
        posture = "neutral"

    return {
        "name": regime,
        "confidence": round(confidence, 2),
        "posture": posture,
        "drivers": drivers,
        "high_priority_cluster_count": len(high_priority),
        "medium_or_high_cluster_count": len(medium_or_high),
        "retail_sentiment": retail_sentiment,
        "memecoin_rotation": memecoin_rotation,
    }
