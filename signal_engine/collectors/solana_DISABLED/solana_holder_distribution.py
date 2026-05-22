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
# MODULE: solana_holder_distribution
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
Solana Holder Distribution Collector

Purpose
-------
Measure holder distribution and concentration across tracked
Solana mints for risk control and narrative enrichment.

Feeds
-----
• bot risk controls
• rug-risk monitoring
• broadcast risk segments
• newsletter analysis
• entity intelligence

Notes
-----
Requires TOKN_SOL_TRACKED_MINTS in .env.

Author: TOKN Systems
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import List

from signal_engine.collectors.registry import register_collector
from signal_engine.collectors.solana.solana_shared import (
    debug_log,
    get_token_largest_accounts,
    get_token_supply,
    parse_csv_env,
)
from models.signal import Signal


TRACKED_MINTS = parse_csv_env(os.getenv("TOKN_SOL_TRACKED_MINTS"))
TOP1_ALERT = float(os.getenv("TOKN_SOL_TOP1_CONCENTRATION_ALERT", "0.20"))
TOP5_ALERT = float(os.getenv("TOKN_SOL_TOP5_CONCENTRATION_ALERT", "0.50"))


def _safe_float(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


@register_collector(
    name="solana_holder_distribution",
    priority=2,
    tags=["solana", "holders", "distribution", "risk", "broadcast"],
    category="onchain",
    execution="slow",
)
def fetch_solana_holder_distribution_signals() -> List[Signal]:
    prefix = "SOLANA HOLDERS"
    started = time.time()
    signals: List[Signal] = []

    if not TRACKED_MINTS:
        print(f"[{prefix}] no tracked mints configured")
        return signals

    for mint in TRACKED_MINTS:
        supply = get_token_supply(mint, prefix=prefix)
        holders = get_token_largest_accounts(mint, prefix=prefix)

        if not supply or not holders:
            continue

        ui_supply = _safe_float(supply.get("uiAmount"))
        if ui_supply <= 0:
            continue

        top_amounts = []
        for holder in holders[:10]:
            amount = _safe_float(holder.get("uiAmount"))
            top_amounts.append(amount)

        if not top_amounts:
            continue

        top1_ratio = top_amounts[0] / ui_supply if ui_supply else 0.0
        top5_ratio = sum(top_amounts[:5]) / ui_supply if ui_supply else 0.0
        top10_ratio = sum(top_amounts[:10]) / ui_supply if ui_supply else 0.0

        debug_log(
            prefix,
            f"mint={mint[:8]} top1={top1_ratio:.4f} top5={top5_ratio:.4f} top10={top10_ratio:.4f}",
        )

        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_holder_distribution",
                entity=mint,
                title="Solana holder distribution update",
                summary=(
                    f"Holder distribution for {mint}: "
                    f"top1={top1_ratio:.2%}, top5={top5_ratio:.2%}, top10={top10_ratio:.2%}"
                ),
                confidence=0.80,
                sentiment_score=-0.10 if top5_ratio >= TOP5_ALERT else 0.05,
                raw_url=f"https://solscan.io/token/{mint}",
            )
        )

        if top1_ratio >= TOP1_ALERT or top5_ratio >= TOP5_ALERT:
            signals.append(
                Signal(
                    timestamp=datetime.utcnow(),
                    source="chainstack",
                    signal_type="solana_holder_concentration_alert",
                    entity=mint,
                    title="Elevated holder concentration detected",
                    summary=(
                        f"Mint {mint} concentration risk elevated: "
                        f"top1={top1_ratio:.2%}, top5={top5_ratio:.2%}"
                    ),
                    confidence=0.84,
                    sentiment_score=-0.24,
                    raw_url=f"https://solscan.io/token/{mint}",
                )
            )

    runtime = round(time.time() - started, 2)
    print(
        f"[{prefix}] tracked={len(TRACKED_MINTS)} "
        f"returned={len(signals)} runtime={runtime}s"
    )

    return signals
