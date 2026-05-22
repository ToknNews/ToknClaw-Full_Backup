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
# MODULE: strategy_candidate_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Dict, List, Any


def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def build_strategy_candidates(snapshot: Dict[str, Any], registry: List[Dict]) -> List[Dict]:

    regime = _safe_dict(snapshot.get("market_regime")).get("name")
    correlations = _safe_list(snapshot.get("narrative_correlations"))
    entities = _safe_dict(snapshot.get("entity_intelligence"))

    candidates = []

    for strat in registry:

        if regime not in strat.get("regimes", []):
            continue

        score = 0.5

        for corr in correlations:
            if corr.get("correlation_type") in strat.get("drivers", []):
                score += 0.2

        candidates.append({
            "strategy_id": strat["strategy_id"],
            "name": strat["name"],
            "direction": strat["direction"],
            "sector": strat["sector"],
            "score": min(score, 1.0),
            "risk_level": strat["risk_level"],
        })

    return candidates
