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
# MODULE: cluster_explorer_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Any, Dict, List
from collections import defaultdict


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


def _cluster_cards(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards = []

    for cluster in _safe_list(snapshot.get("clusters")):
        cluster = _safe_dict(cluster)

        cid = _safe_str(cluster.get("cluster_id"))
        if not cid:
            continue

        cards.append({
            "cluster_id": cid,
            "cluster_type": cluster.get("cluster_type"),
            "entity": cluster.get("entity"),
            "signal_count": cluster.get("signal_count"),
            "total_value_usd": round(_safe_float(cluster.get("total_value_usd"), 0.0), 2),
            "avg_confidence": round(_safe_float(cluster.get("avg_confidence"), 0.0), 3),
            "sources": cluster.get("sources") or [],
            "urls": cluster.get("urls") or [],
            "summary": cluster.get("summary"),
            "sample_titles": cluster.get("sample_titles") or [],
        })

    cards.sort(
        key=lambda x: (
            _safe_float(x.get("total_value_usd"), 0.0),
            _safe_float(x.get("avg_confidence"), 0.0),
            _safe_float(x.get("signal_count"), 0.0),
        ),
        reverse=True,
    )

    return cards


def _cluster_filters(cards: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    cluster_types = sorted(set(_safe_str(c.get("cluster_type")) for c in cards if _safe_str(c.get("cluster_type"))))
    entities = sorted(set(_safe_str(c.get("entity")) for c in cards if _safe_str(c.get("entity"))))
    sources = sorted(set(src for c in cards for src in (c.get("sources") or [])))

    return {
        "cluster_types": cluster_types[:200],
        "entities": entities[:500],
        "sources": sources[:100],
    }


def _cluster_groups(cards: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups = defaultdict(list)

    for card in cards:
        key = _safe_str(card.get("cluster_type")) or "unknown"
        groups[key].append(card)

    return {
        key: sorted(
            value,
            key=lambda x: _safe_float(x.get("total_value_usd"), 0.0),
            reverse=True,
        )[:50]
        for key, value in groups.items()
    }


def build_cluster_explorer(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    cards = _cluster_cards(snapshot)
    filters = _cluster_filters(cards)
    groups = _cluster_groups(cards)

    summary = {
        "cluster_count": len(cards),
        "top_cluster": cards[0]["cluster_id"] if cards else None,
        "top_cluster_value": cards[0]["total_value_usd"] if cards else 0.0,
        "group_count": len(groups),
    }

    return {
        "cluster_explorer": {
            "cards": cards,
            "filters": filters,
            "groups": groups,
        },
        "cluster_explorer_summary": summary,
        "cluster_explorer_endpoints": {
            "cluster_explorer": "/api/toknclaw/clusters",
            "cluster_explorer_summary": "/api/toknclaw/clusters/summary",
            "cluster_explorer_filters": "/api/toknclaw/clusters/filters",
            "cluster_explorer_groups": "/api/toknclaw/clusters/groups",
        },
    }
