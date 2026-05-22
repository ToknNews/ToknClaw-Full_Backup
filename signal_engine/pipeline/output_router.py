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
# MODULE: output_router
# PURPOSE: Routes snapshot into product-specific intelligence views
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""
from typing import Dict, List, Any


# ============================================================
# HELPERS
# ============================================================

def top_n(items: List[Dict], n: int, key: str = "confidence") -> List[Dict]:
    return sorted(items, key=lambda x: x.get(key, 0), reverse=True)[:n]


def filter_signals(signals: List[Dict], min_conf: float = 0.0) -> List[Dict]:
    return [s for s in signals if s.get("confidence", 0) >= min_conf]


# ============================================================
# BROADCAST VIEW (ToknNews)
# ============================================================

def build_broadcast_view(snapshot: Dict) -> Dict:

    narratives = snapshot.get("narratives", [])
    clusters = snapshot.get("clusters", [])
    signals = snapshot.get("signals", [])
    regime = snapshot.get("market_regime", {})

    top_narratives = top_n(narratives, 5, key="confidence")

    high_priority_clusters = [
        c for c in clusters if c.get("broadcast_priority") == "high"
    ]

    top_clusters = sorted(
        high_priority_clusters,
        key=lambda x: x.get("signal_count", 0),
        reverse=True
    )[:5]

    top_signals = top_n(signals, 10, key="confidence")

    return {
        "headline_narratives": top_narratives,
        "top_clusters": top_clusters,
        "top_signals": top_signals,
        "market_regime": regime,
    }


# ============================================================
# DASHBOARD VIEW (UI)
# ============================================================

def build_dashboard_view(snapshot: Dict) -> Dict:

    return {
        "clusters": snapshot.get("clusters", []),
        "signals": snapshot.get("signals", []),
        "narratives": snapshot.get("narratives", []),
        "cross_asset": snapshot.get("cross_asset_intelligence", {}),
        "liquidity": snapshot.get("macro_liquidity", {}),
        "stress": snapshot.get("market_stress", {}),
        "structure": snapshot.get("market_structure", {}),
    }


# ============================================================
# TRADING VIEW (PRIVATE SYSTEM)
# ============================================================

def build_trading_view(snapshot: Dict) -> Dict:

    return {
        "trade_signals": snapshot.get("trade_signals", []),
        "strategy_allocations": snapshot.get("strategy_allocations", []),
        "position_risk": snapshot.get("position_risk", {}),
        "market_regime": snapshot.get("market_regime", {}),
        "conviction_scores": snapshot.get("conviction_scores", {}),
    }


# ============================================================
# PROMO VIEW (CONTENT ENGINE)
# ============================================================

def build_promo_view(snapshot: Dict) -> Dict:

    signals = snapshot.get("signals", [])

    # heuristic filters for high-drama content
    high_conf = filter_signals(signals, min_conf=0.8)

    memecoin = [
        s for s in high_conf
        if "memecoin" in str(s.get("tags", [])).lower()
    ]

    whales = [
        s for s in high_conf
        if "whale" in str(s.get("title", "")).lower()
    ]

    news = [
        s for s in high_conf
        if "news" in str(s.get("source", "")).lower()
    ]

    return {
        "high_conviction": high_conf[:20],
        "memecoin_activity": memecoin[:15],
        "whale_activity": whales[:15],
        "news_drivers": news[:15],
    }


# ============================================================
# MAIN ROUTER
# ============================================================

def build_output_views(snapshot: Dict) -> Dict:

    return {
        "broadcast": build_broadcast_view(snapshot),
        "dashboard": build_dashboard_view(snapshot),
        "trading": build_trading_view(snapshot),
        "promo": build_promo_view(snapshot),
    }
