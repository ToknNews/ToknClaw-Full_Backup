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
# MODULE: solana_wallet_concentration
# PURPOSE: Measure top-holder concentration for Solana tokens via RPC
#
# AUTHOR: TOKN SYSTEM
# ============================================================

Responsibilities
----------------
• fetch token supply via RPC
• fetch largest holder accounts via RPC
• compute concentration ratios
• emit risk signals for allocator + broadcast

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

print("[DEBUG] solana_wallet_concentration MODULE LOADED")
# ---------------------------------------------------
# CONFIG (READ AT RUNTIME)
# ---------------------------------------------------

def get_tracked_mints():
    return parse_csv_env(os.getenv("TOKN_SOL_TRACKED_MINTS"))


TOP1_ALERT = float(os.getenv("TOKN_SOL_TOP1_CONCENTRATION_ALERT", "0.20"))
TOP5_ALERT = float(os.getenv("TOKN_SOL_TOP5_CONCENTRATION_ALERT", "0.50"))


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def _safe_float(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


# ---------------------------------------------------
# COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="solana_wallet_concentration",
    priority=2,
    tags=["solana", "wallets", "concentration", "risk"],
    category="onchain",
    execution="slow",
)

def fetch_solana_wallet_concentration_signals() -> List[Signal]:
    print("[DEBUG] solana_wallet_concentration FUNCTION CALLED")
    prefix = "SOLANA CONCENTRATION"
    started = time.time()
    signals: List[Signal] = []

    tracked_mints = get_tracked_mints()

    if not tracked_mints:
        print(f"[{prefix}] no tracked mints configured")
        return signals

    print(f"[{prefix}] starting RPC checks for {len(tracked_mints)} mints")

    for mint in tracked_mints:

        # ---------------------------------------------------
        # RPC CALLS (THIS IS WHAT DRIVES CHAINSTACK USAGE)
        # ---------------------------------------------------

        supply = get_token_supply(mint, prefix=prefix)
        holders = get_token_largest_accounts(mint, prefix=prefix)

        print(f"[CHAINSTACK] mint={mint[:8]} supply={'OK' if supply else 'FAIL'} holders={len(holders)}")

        if not supply or not holders:
            continue

        ui_amount = _safe_float(supply.get("uiAmount"))
        if ui_amount <= 0:
            continue

        top_balances = [
            _safe_float(holder.get("uiAmount"))
            for holder in holders[:5]
        ]

        if not top_balances:
            continue

        top1_ratio = top_balances[0] / ui_amount if ui_amount else 0.0
        top5_ratio = sum(top_balances) / ui_amount if ui_amount else 0.0

        debug_log(
            prefix,
            f"mint={mint[:8]} supply={round(ui_amount,2)} "
            f"top1={round(top1_ratio,4)} top5={round(top5_ratio,4)}",
        )

        # ---------------------------------------------------
        # SIGNAL EMISSION
        # ---------------------------------------------------

        if top1_ratio >= TOP1_ALERT or top5_ratio >= TOP5_ALERT:
            signals.append(
                Signal(
                    timestamp=datetime.utcnow(),
                    source="chainstack",
                    signal_type="solana_wallet_concentration",
                    entity=mint,
                    title="Elevated Solana wallet concentration detected",
                    summary=(
                        f"Mint {mint} concentration risk: "
                        f"top1={top1_ratio:.2%}, top5={top5_ratio:.2%}"
                    ),
                    confidence=0.81,
                    sentiment_score=-0.22,
                    raw_url=f"https://solscan.io/token/{mint}",
                )
            )

    runtime = round(time.time() - started, 2)

    print(
        f"[{prefix}] tracked={len(tracked_mints)} "
        f"returned={len(signals)} runtime={runtime}s"
    )

    return signals
