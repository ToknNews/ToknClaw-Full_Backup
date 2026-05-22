#!/usr/bin/env python3
"""
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
# MODULE: collector_tiers
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


Collector tier orchestration for ToknClaw.

Purpose
-------
Organize collectors into execution tiers so
real-time signals always run before slower
analytics and research collectors.

Tier Structure
--------------

tier_1 : realtime signals
tier_2 : structural capital data
tier_3 : narrative sources
tier_4 : deep research / heavy scrapers
"""

from __future__ import annotations

from typing import Dict, List, Any


# -------------------------------------------------------
# Tier definitions
# -------------------------------------------------------

TIER_MAP = {

    "tier_1": {
        "description": "realtime market signals",
        "tags": {
            "whales",
            "liquidations",
            "exchange_flows",
            "onchain",
            "trading",
        }
    },

    "tier_2": {
        "description": "structural capital signals",
        "tags": {
            "defi",
            "protocol_metrics",
            "tvl",
            "protocol_revenue",
            "token_metrics",
        }
    },

    "tier_3": {
        "description": "narrative signals",
        "tags": {
            "news",
            "social",
            "sentiment",
            "culture",
        }
    },

    "tier_4": {
        "description": "deep research collectors",
        "tags": {
            "research",
            "analytics",
            "agents",
        }
    }
}


# -------------------------------------------------------
# Tier resolver
# -------------------------------------------------------

def resolve_collector_tier(collector: Dict[str, Any]) -> str:

    tags = set(collector.get("tags") or [])

    for tier, meta in TIER_MAP.items():

        tier_tags = meta.get("tags") or set()

        if tags & tier_tags:
            return tier

    return "tier_3"


# -------------------------------------------------------
# Tier grouping
# -------------------------------------------------------

def group_collectors_by_tier(collectors):

    tiers = {
        "tier_1": [],
        "tier_2": [],
        "tier_3": [],
        "tier_4": [],
    }

    for c in collectors:

        category = (c.get("category") or "").lower()
        name = c.get("collector_name", "").lower()

        # -----------------------------------------
        # TIER 1 — CRITICAL (RPC / onchain)
        # -----------------------------------------
        if (
            category == "onchain"
            or "solana" in name
            or "evm" in name
        ):
            tiers["tier_1"].append(c)
            continue

        # -----------------------------------------
        # TIER 2 — SIGNAL / STRATEGY
        # -----------------------------------------
        if (
            "strategy" in name
            or "allocator" in name
            or "performance" in name
            or category in ["analysis", "derived"]
        ):
            tiers["tier_2"].append(c)
            continue

        # -----------------------------------------
        # TIER 3 — DATA / NEWS / API
        # -----------------------------------------
        if (
            "rss" in name
            or "news" in name
            or "scraper" in name
            or "reddit" in name
            or "coingecko" in name
            or "cryptopanic" in name
        ):
            tiers["tier_3"].append(c)
            continue

        # -----------------------------------------
        # DEFAULT → TIER 3
        # -----------------------------------------
        tiers["tier_3"].append(c)

    return tiers

# -------------------------------------------------------
# Ordered execution plan
# -------------------------------------------------------

def build_execution_plan(collectors: List[Dict[str, Any]]):

    tiers = group_collectors_by_tier(collectors)

    execution_order = []

    for tier in ["tier_1", "tier_2", "tier_3", "tier_4"]:

        batch = tiers.get(tier) or []

        if not batch:
            continue

        batch.sort(
            key=lambda c: (
                -int(c.get("priority", 100)),
                c.get("collector_name", "")
            )
        )

        execution_order.append({
            "tier": tier,
            "collectors": batch
        })

    return execution_order
