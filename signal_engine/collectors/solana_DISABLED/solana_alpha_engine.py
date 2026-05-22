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
# MODULE: solana_alpha_engine
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
Solana Alpha Engine

Purpose
-------
Aggregate Solana collector signals into a unified alpha score
for trading, alerts, and broadcast narratives.

Feeds
-----
• trading bot entry/exit signals
• narrative engine
• alerts
• newsletters
• social media commentary

Author: TOKN Systems
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List

from signal_engine.collectors.registry import register_collector
from models.signal import Signal


# Weight configuration
WEIGHTS = {
    "solana_token_mint": 1.5,
    "solana_pumpfun_activity": 1.4,
    "solana_raydium_pool_init": 2.0,
    "solana_liquidity_event": 1.6,
    "solana_jupiter_swap": 1.2,
    "solana_volume_velocity": 2.2,
    "solana_mev_activity": 1.0,
    "solana_liquidity_depth": 0.8,
    "solana_dev_wallet_sale": -2.5,
    "solana_holder_concentration_alert": -1.5,
}


ENTRY_THRESHOLD = float(os.getenv("TOKN_SOL_ALPHA_ENTRY", "4.0"))
EXIT_THRESHOLD = float(os.getenv("TOKN_SOL_ALPHA_EXIT", "-2.5"))


@register_collector(
    name="solana_alpha_engine",
    priority=0,
    tags=["solana", "alpha", "trading", "broadcast"],
    category="analysis",
)
def fetch_solana_alpha_signals(snapshot: Dict | None = None) -> List[Signal]:

    signals: List[Signal] = []

    if not snapshot:
        return signals

    raw_signals = snapshot.get("signals", [])

    token_scores: Dict[str, float] = {}

    for s in raw_signals:

        stype = getattr(s, "signal_type", None)
        entity = getattr(s, "entity", None)

        if not stype or not entity:
            continue

        weight = WEIGHTS.get(stype)

        if weight is None:
            continue

        token_scores.setdefault(entity, 0.0)
        token_scores[entity] += weight

    now = datetime.utcnow()

    for token, score in token_scores.items():

        if score >= ENTRY_THRESHOLD:

            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_alpha_entry_signal",
                    entity=token,
                    title="Solana Alpha Entry Signal",
                    summary=f"Alpha score {score:.2f} for {token} — entry conditions detected",
                    confidence=0.85,
                    sentiment_score=0.6,
                    raw_url=None,
                )
            )

        if score <= EXIT_THRESHOLD:

            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_alpha_exit_warning",
                    entity=token,
                    title="Solana Alpha Exit Warning",
                    summary=f"Alpha score {score:.2f} for {token} — exit risk detected",
                    confidence=0.82,
                    sentiment_score=-0.6,
                    raw_url=None,
                )
            )

    if token_scores:

        top = sorted(token_scores.items(), key=lambda x: x[1], reverse=True)[:5]

        signals.append(
            Signal(
                timestamp=now,
                source="toknclaw",
                signal_type="solana_alpha_summary",
                entity="SOLANA_ALPHA",
                title="Solana Alpha Summary",
                summary=f"Top alpha tokens: {', '.join([t[0] for t in top])}",
                confidence=0.75,
                sentiment_score=0.25,
                raw_url=None,
            )
        )

    print(f"[SOLANA ALPHA] tokens_scored={len(token_scores)} signals={len(signals)}")

    return signals
