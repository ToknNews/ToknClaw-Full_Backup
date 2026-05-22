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
# MODULE: metrics
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
████████╗ ██████╗ ██╗  ██╗███╗   ██╗
╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║
   ██║   ██║   ██║█████╔╝ ██╔██╗ ██║
   ██║   ██║   ██║██╔═██╗ ██║╚██╗██║
   ██║   ╚██████╔╝██║  ██╗██║ ╚████║
   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝

TOKNCLAW SIGNAL ENGINE
Metrics & Analytics Engine

Purpose
-------
Aggregate system metrics and intelligence summaries
from collector signals.

Author: TOKN Systems
"""

from __future__ import annotations

import collections
from typing import Any, Dict, List


def safe_get(obj, field, default=None):
    try:
        if isinstance(obj, dict):
            return obj.get(field, default)
        return getattr(obj, field, default)
    except Exception:
        return default


def compute_metrics(signals: List[Any]) -> Dict[str, Any]:

    metrics: Dict[str, Any] = {}

    total_signals = len(signals)

    by_source = collections.Counter()
    by_type = collections.Counter()
    by_entity = collections.Counter()

    solana_activity = collections.Counter()
    titles = []

    for s in signals:

        source = safe_get(s, "source")
        signal_type = safe_get(s, "signal_type")
        entity = safe_get(s, "entity")
        title = safe_get(s, "title")

        if title:
            titles.append(title)

        if source:
            by_source[source] += 1

        if signal_type:
            by_type[signal_type] += 1

        if entity:
            by_entity[entity] += 1

        if isinstance(signal_type, str) and "solana" in signal_type:
            solana_activity[signal_type] += 1

    metrics["total_signals"] = total_signals
    metrics["unique_entities"] = len(by_entity)
    metrics["sources"] = dict(by_source)
    metrics["signal_types"] = dict(by_type)
    metrics["top_entities"] = by_entity.most_common(10)
    metrics["headline_samples"] = titles[:10]
    metrics["solana_activity"] = dict(solana_activity)

    solana_volume = (
        solana_activity.get("solana_jupiter_swap", 0)
        + solana_activity.get("solana_jupiter_swap_activity", 0)
        + solana_activity.get("solana_jupiter_stream_event", 0)
        + solana_activity.get("solana_volume_velocity", 0)
        + solana_activity.get("solana_velocity_summary", 0)
    )

    solana_launches = (
        solana_activity.get("solana_pumpfun_activity", 0)
        + solana_activity.get("solana_pumpfun_summary", 0)
        + solana_activity.get("solana_pumpfun_stream_event", 0)
        + solana_activity.get("solana_token_mint", 0)
        + solana_activity.get("solana_mint_activity", 0)
    )

    solana_liquidity = (
        solana_activity.get("solana_raydium_pool_init", 0)
        + solana_activity.get("solana_raydium_pool_activity", 0)
        + solana_activity.get("solana_raydium_stream_event", 0)
        + solana_activity.get("solana_liquidity_event", 0)
        + solana_activity.get("solana_liquidity_depth", 0)
    )

    solana_mev = solana_activity.get("solana_mev_activity", 0)

    metrics["solana_summary"] = {
        "launch_activity": solana_launches,
        "liquidity_events": solana_liquidity,
        "swap_activity": solana_volume,
        "mev_activity": solana_mev,
    }

    alpha_signals = []

    for s in signals:
        stype = safe_get(s, "signal_type")
        if isinstance(stype, str) and "alpha" in stype:
            alpha_signals.append(stype)

    metrics["alpha_signal_count"] = len(alpha_signals)

    metrics["system_health"] = {
        "signals_processed": total_signals,
        "unique_signal_types": len(by_type),
        "unique_sources": len(by_source),
        "unique_entities": len(by_entity),
    }

    print(
        "[METRICS] signals=", total_signals,
        "sources=", len(by_source),
        "types=", len(by_type),
        "entities=", len(by_entity),
    )

    return metrics
