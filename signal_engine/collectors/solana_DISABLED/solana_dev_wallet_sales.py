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
# MODULE: solana_dev_wallet_sales
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
Solana Dev Wallet Sales Collector

Purpose
-------
Detect selling behavior from tracked Solana dev/team wallets.

Feeds
-----
• bot risk controls
• rug-risk monitoring
• narrative intelligence
• broadcast warning segments
• alerts and newsletters

Notes
-----
Requires TOKN_SOL_DEV_WALLETS in .env.

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
    get_signatures_for_address,
    get_transaction,
    parse_csv_env,
    short_addr,
    token_balance_deltas,
)
from models.signal import Signal


DEV_WALLETS = parse_csv_env(os.getenv("TOKN_SOL_DEV_WALLETS"))
SIGNATURE_LIMIT = int(os.getenv("TOKN_SOL_DEV_SALES_SIGNATURE_LIMIT", "30"))
ABS_DELTA_ALERT = float(os.getenv("TOKN_SOL_DEV_SALES_DELTA_ALERT", "500"))
MIN_SELL_EVENTS_ALERT = int(os.getenv("TOKN_SOL_DEV_SALES_MIN_EVENTS", "2"))


@register_collector(
    name="solana_dev_wallet_sales",
    priority=2,
    tags=["solana", "dev-wallet", "sales", "risk", "broadcast"],
    category="onchain",
)
def fetch_solana_dev_wallet_sales_signals() -> List[Signal]:
    prefix = "SOLANA DEV SALES"
    started = time.time()
    signals: List[Signal] = []

    if not DEV_WALLETS:
        print(f"[{prefix}] no dev wallets configured")
        return signals

    sell_events = 0

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
                if change >= 0:
                    continue
                if abs(change) < ABS_DELTA_ALERT:
                    continue

                sell_events += 1

                debug_log(
                    prefix,
                    f"wallet={short_addr(wallet)} mint={mint[:8]} sold={abs(change):,.4f}",
                )

                signals.append(
                    Signal(
                        timestamp=datetime.utcnow(),
                        source="chainstack",
                        signal_type="solana_dev_wallet_sale",
                        entity=mint,
                        title="Tracked Solana dev wallet sale detected",
                        summary=(
                            f"Tracked wallet {short_addr(wallet)} sold "
                            f"{abs(change):,.4f} units of mint {mint}"
                        ),
                        confidence=0.86,
                        sentiment_score=-0.28,
                        raw_url=f"https://solscan.io/tx/{sig}",
                    )
                )

    if sell_events >= MIN_SELL_EVENTS_ALERT:
        signals.append(
            Signal(
                timestamp=datetime.utcnow(),
                source="chainstack",
                signal_type="solana_dev_wallet_sales_summary",
                entity="SOLANA_DEV_SALES",
                title="Solana dev wallet selling pressure detected",
                summary=f"{sell_events} recent dev-wallet sell events detected across tracked wallets",
                confidence=0.82,
                sentiment_score=-0.30,
                raw_url=None,
            )
        )

    runtime = round(time.time() - started, 2)
    print(
        f"[{prefix}] wallets={len(DEV_WALLETS)} "
        f"sell_events={sell_events} returned={len(signals)} runtime={runtime}s"
    )

    return signals
