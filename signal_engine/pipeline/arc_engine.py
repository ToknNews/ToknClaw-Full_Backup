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
# MODULE: arc_engine
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _arc_key(record: Dict[str, Any]) -> str:
    return f"{record.get('narrative_type')}::{record.get('sector')}"


def build_narrative_arcs(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    history = _safe_list(snapshot.get("narrative_history"))

    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for item in history:
        if not isinstance(item, dict):
            continue

        key = _arc_key(item)
        grouped.setdefault(key, []).append(item)

    arcs: List[Dict[str, Any]] = []

    for key, items in grouped.items():
        items.sort(
            key=lambda x: (
                x.get("state") == "dominant",
                _safe_float(x.get("persistence_score"), 0.0),
                _safe_float(x.get("velocity_score"), 0.0),
                _safe_float(x.get("latest_confidence"), 0.0),
            ),
            reverse=True,
        )

        first_seen = min(_safe_int(i.get("first_seen"), 0) for i in items if i.get("first_seen"))
        last_seen = max(_safe_int(i.get("last_seen"), 0) for i in items if i.get("last_seen"))
        total_observations = sum(_safe_int(i.get("observation_count"), 0) for i in items)

        dominant_entities: List[str] = []
        supporting_sources: List[str] = []
        supporting_urls: List[str] = []
        states: List[str] = []

        for item in items:
            dominant_entities.extend(item.get("dominant_entities") or [])
            supporting_sources.extend(item.get("supporting_sources") or [])
            supporting_urls.extend(item.get("supporting_urls") or [])
            states.append(str(item.get("state") or "active"))

        dominant_entities = list(dict.fromkeys(dominant_entities))[:12]
        supporting_sources = list(dict.fromkeys(supporting_sources))[:12]
        supporting_urls = list(dict.fromkeys(supporting_urls))[:20]

        lead = items[0]
        narrative_type = str(lead.get("narrative_type") or "unknown")
        sector = str(lead.get("sector") or "general")

        arc_strength = "low"
        peak_persistence = max(_safe_float(i.get("persistence_score"), 0.0) for i in items)
        peak_velocity = max(_safe_float(i.get("velocity_score"), 0.0) for i in items)
        peak_confidence = max(_safe_float(i.get("latest_confidence"), 0.0) for i in items)

        if peak_persistence >= 0.75 or peak_confidence >= 0.9:
            arc_strength = "dominant"
        elif peak_persistence >= 0.55 or peak_confidence >= 0.82:
            arc_strength = "high"
        elif peak_persistence >= 0.35 or peak_confidence >= 0.7:
            arc_strength = "medium"

        state = "active"
        if all(s == "fading" for s in states):
            state = "fading"
        elif any(s == "dominant" for s in states):
            state = "dominant"

        arcs.append({
            "arc_id": key,
            "arc_type": narrative_type,
            "sector": sector,
            "title": f"{narrative_type} arc",
            "summary": f"{narrative_type} has persisted across the monitored narrative history.",
            "state": state,
            "strength": arc_strength,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "duration_sec": max(last_seen - first_seen, 0),
            "narrative_count": len(items),
            "total_observations": total_observations,
            "dominant_entities": dominant_entities,
            "supporting_sources": supporting_sources,
            "supporting_urls": supporting_urls,
            "peak_persistence_score": round(peak_persistence, 2),
            "peak_velocity_score": round(peak_velocity, 2),
            "peak_confidence": round(peak_confidence, 2),
            "memory_keys": [i.get("memory_key") for i in items if i.get("memory_key")],
        })

    arcs.sort(
        key=lambda a: (
            a.get("state") == "dominant",
            a.get("strength") == "dominant",
            a.get("peak_persistence_score", 0.0),
            a.get("peak_velocity_score", 0.0),
            a.get("peak_confidence", 0.0),
            a.get("duration_sec", 0),
        ),
        reverse=True,
    )

    return arcs


def build_arc_summary(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    arcs = _safe_list(snapshot.get("narrative_arcs"))

    dominant = [a for a in arcs if a.get("state") == "dominant"]
    active = [a for a in arcs if a.get("state") in {"active", "dominant"}]

    lead = arcs[0] if arcs else {}

    return {
        "arc_count": len(arcs),
        "dominant_arc_count": len(dominant),
        "active_arc_count": len(active),
        "primary_arc": lead.get("arc_type"),
        "primary_arc_title": lead.get("title"),
        "primary_arc_strength": lead.get("strength"),
    }
