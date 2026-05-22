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
# MODULE: signal_schema_v2
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import time
from typing import Any, Dict, List

from pipeline.entity_mapper import enrich_entity_metadata


def normalize_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    entity_meta = enrich_entity_metadata(
        signal.get("entity"),
        source=signal.get("source"),
        sector=signal.get("sector"),
        chain=signal.get("chain"),
    )

    return {
        "timestamp": signal.get("timestamp") or time.time(),
        "source": signal.get("source"),
        "signal_type": signal.get("signal_type"),
        "signal_class": signal.get("signal_class"),
        "signal_family": signal.get("signal_family"),
        "entity": entity_meta.get("entity"),
        "entity_type": signal.get("entity_type") or entity_meta.get("entity_type"),
        "sector": signal.get("sector") or entity_meta.get("sector"),
        "chain": signal.get("chain") or entity_meta.get("chain"),
        "direction": signal.get("direction"),
        "value_usd": signal.get("value_usd"),
        "confidence": signal.get("confidence"),
        "sentiment_score": signal.get("sentiment_score"),
        "time_horizon": signal.get("time_horizon"),
        "title": signal.get("title"),
        "summary": signal.get("summary"),
        "tags": signal.get("tags") or [],
        "source_url": signal.get("source_url") or signal.get("raw_url"),
        "raw_source_id": signal.get("raw_source_id"),
        "metadata": signal.get("metadata") or {},
    }


def normalize_signals(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []

    for signal in signals:
        if isinstance(signal, dict):
            normalized.append(normalize_signal(signal))
            continue

        try:
            normalized.append(normalize_signal(signal.__dict__))
        except Exception:
            continue

    return normalized
