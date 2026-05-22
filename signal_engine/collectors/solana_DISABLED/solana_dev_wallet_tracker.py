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
# MODULE: solana_dev_wallet_tracker
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
Solana Dev Wallet Tracker

Purpose
-------
Track known dev/team wallets on Solana for risk alerts and narrative enrichment.

Feeds
-----
• bot risk controls
• whale/dev alerts
• broadcast narratives
• article/social content
• newsletters

Notes
-----
Requires TOKN_SOL_DEV_WALLETS in .env.

Author: TOKN Systems
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Dict, List

from signal_engine.collectors.registry import register_collector
from signal_engine.collectors.solana.solana_shared import (
    debug_log,
    get_signatures_for_address,
    get_transaction,
    parse_csv_env,
    short_addr,
    token_balance_deltas,
)
from models.signal import Signal


DEV_WALLETS = parse_csv_env(os.getenv("TOKN_SOL_DEV_WALLETS"))
SIGNATURE_LIMIT = int(os.getenv("TOKN_SOL_DEV_WALLET_SIGNATURE_LIMIT", "25"))
ABS_DELTA_ALERT = float(os.getenv("TOKN_SOL_DEV_WALLET_DELTA_ALERT", "1000"))


@register_collector(
    name="solana_dev_wallet_tracker",
    priority=2,
    tags=["solana", "dev-wallet", "risk", "alerts", "broadcast"],
    category="onchain",
)
def fetch_solana_dev_wallet_signals() -> List[Signal]:
    prefix = "SOLANA DEV"
    started = time.time()
    signals: List[Signal] = []

    if not DEV_WALLETS:
        print(f"[{prefix}] no dev wallets configured")
        return signals

    for wallet in DEV_WALLETS:
        rows = get_signatures_for_address(wallet, SIGNATURE_LIMIT, prefix=prefix)
        debug_log(prefix, f"wallet={short_addr(wallet)} signatures={len(rows)}")

        for row in rows:
            sig = row.get("signature")
            if not sig:
                continue

            tx = get_transaction(sig, prefix=prefix)
            if not tx:
                continue

            deltas = token_balance_deltas(tx)

            for delta in deltas:
                owner = delta.get("owner")
                mint = delta.get("mint")
                change = float(delta.get("delta", 0.0))

                if owner != wallet:
                    continue
                if not mint:
                    continue
                if abs(change) < ABS_DELTA_ALERT:
                    continue

                direction = "received" if change > 0 else "sent"

                debug_log(
                    prefix,
                    f"wallet={short_addr(wallet)} mint={mint[:8]} delta={round(change,4)} direction={direction}",
                )

                signals.append(
                    Signal(
                        timestamp=datetime.utcnow(),
                        source="chainstack",
                        signal_type="solana_dev_wallet_flow",
                        entity=mint,
                        title="Tracked Solana dev wallet flow detected",
                        summary=(
                            f"Tracked wallet {short_addr(wallet)} {direction} "
                            f"{abs(change):,.4f} units of mint {mint}"
                        ),
                        confidence=0.84,
                        sentiment_score=-0.12 if change < 0 else 0.08,
                        raw_url=f"https://solscan.io/tx/{sig}",
                    )
                )

    runtime = round(time.time() - started, 2)
    print(f"[{prefix}] wallets={len(DEV_WALLETS)} returned={len(signals)} runtime={runtime}s")

    return signals
