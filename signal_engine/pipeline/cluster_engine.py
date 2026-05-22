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
# MODULE: cluster_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Any, Dict, List
from collections import defaultdict
import re
import time


USD_RE = re.compile(r"\$([0-9,]+)")


# ---------------------------------------------------
# Utilities
# ---------------------------------------------------

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _extract_usd_from_title(title: str) -> float:
    if not isinstance(title, str):
        return 0.0

    match = USD_RE.search(title)
    if not match:
        return 0.0

    raw = match.group(1).replace(",", "")
    return _safe_float(raw, 0.0)


# ---------------------------------------------------
# Cluster key logic
# ---------------------------------------------------

def _cluster_key(signal: Dict[str, Any]) -> str:

    signal_type = str(signal.get("signal_type") or "unknown").lower()
    entity = str(signal.get("entity") or "NONE").upper()
    source = str(signal.get("source") or "unknown").lower()

    if signal_type == "whale_transfer":
        return f"whale_activity::{entity}"

    if signal_type in {
        "x_narrative",
        "reddit_narrative",
        "memecoin_rotation",
        "retail_pulse"
    }:
        return f"retail_narrative::{entity}"

    if signal_type == "news":
        return f"news::{entity}"

    if signal_type.startswith("protocol_"):
        return f"{signal_type}::{entity}"

    return f"{signal_type}::{entity}::{source}"


# ---------------------------------------------------
# Cluster type classification
# ---------------------------------------------------

def _cluster_type(signal: Dict[str, Any]) -> str:

    signal_type = str(signal.get("signal_type") or "unknown").lower()

    if signal_type == "whale_transfer":
        return "whale_activity"

    if signal_type in {
        "x_narrative",
        "reddit_narrative",
        "memecoin_rotation",
        "retail_pulse"
    }:
        return "retail_narrative"

    if signal_type == "news":
        return "news_theme"

    if signal_type.startswith("protocol_"):
        return signal_type

    return signal_type


# ---------------------------------------------------
# Broadcast priority heuristic
# ---------------------------------------------------

def _broadcast_priority(cluster_type: str, value_usd: float, signal_count: int):

    if cluster_type == "whale_activity" and value_usd > 100_000_000:
        return "high"

    if cluster_type in {"protocol_tvl", "protocol_revenue"}:
        return "high"

    if cluster_type == "retail_narrative" and signal_count >= 2:
        return "medium"

    if signal_count >= 3:
        return "medium"

    return "low"


# ---------------------------------------------------
# Main cluster builder
# ---------------------------------------------------

def build_clusters(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    now = time.time()

    for signal in signals or []:
        if isinstance(signal, dict):
            grouped[_cluster_key(signal)].append(signal)

    clusters: List[Dict[str, Any]] = []

    for key, items in grouped.items():

        first = items[0]

        cluster_type = _cluster_type(first)
        entity = first.get("entity")

        sources = sorted(
            set(str(item.get("source") or "") for item in items)
        )

        entities = sorted(
            set(str(item.get("entity") or "") for item in items if item.get("entity"))
        )

        urls = [
            item.get("raw_url")
            for item in items
            if item.get("raw_url")
        ]

        titles: List[str] = []
        total_confidence = 0.0
        total_value_usd = 0.0

        first_ts = None
        last_ts = None

        for item in items:

            total_confidence += _safe_float(item.get("confidence"), 0.0)

            total_value_usd += _extract_usd_from_title(
                str(item.get("title") or "")
            )

            title = str(item.get("title") or "").strip()

            if title:
                titles.append(title)

            ts = item.get("timestamp")

            if ts:
                try:
                    t = float(ts)
                    if first_ts is None or t < first_ts:
                        first_ts = t
                    if last_ts is None or t > last_ts:
                        last_ts = t
                except Exception:
                    pass

        avg_confidence = round(
            total_confidence / max(len(items), 1), 3
        )

        summary = ""

        if cluster_type == "whale_activity":

            summary = (
                f"{len(items)} whale transfer signal(s)"
                + (
                    f" totaling about ${total_value_usd:,.0f}"
                    if total_value_usd > 0 else ""
                )
                + (f" for {entity}" if entity else "")
            )

        elif cluster_type == "retail_narrative":

            summary = (
                f"{len(items)} retail narrative signal(s)"
                + (f" centered on {entity}" if entity and entity != "NONE" else "")
            )

        elif cluster_type == "news_theme":

            summary = (
                f"{len(items)} news signal(s)"
                + (f" linked to {entity}" if entity and entity != "NONE" else "")
            )

        else:

            summary = f"{len(items)} signal(s) in cluster {cluster_type}"

        broadcast_priority = _broadcast_priority(
            cluster_type,
            total_value_usd,
            len(items)
        )

        cluster_age = None

        if last_ts:
            cluster_age = int(now - last_ts)

        clusters.append({

            "cluster_id": key,

            "cluster_type": cluster_type,

            "entity": entity,

            "entities": entities,

            "signal_count": len(items),

            "sources": sources,

            "urls": urls,

            "avg_confidence": avg_confidence,

            "total_value_usd": round(total_value_usd, 2),

            "broadcast_priority": broadcast_priority,

            "summary": summary,

            "sample_titles": titles[:3],

            "first_seen": first_ts,

            "last_seen": last_ts,

            "cluster_age_sec": cluster_age

        })

    clusters.sort(

        key=lambda c: (

            c.get("broadcast_priority") == "high",

            c.get("total_value_usd", 0.0),

            c.get("signal_count", 0),

            c.get("avg_confidence", 0.0)

        ),

        reverse=True

    )

    return clusters
