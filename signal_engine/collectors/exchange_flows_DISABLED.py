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
# MODULE: exchange_flows
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
Exchange Flow Collector

Purpose
-------

Detects high-value token flows into and out of known exchange wallets
using Chainstack-backed EVM RPC infrastructure.

This collector is intended to surface:

• exchange inflows
• exchange outflows
• institutional-sized transfers
• potential distribution / accumulation behavior

Feeds:

• institutional_flow_engine
• market_structure_engine
• liquidity_rotation_engine

Author: TOKN Systems
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import List

from web3 import Web3

from models.signal import Signal
from signal_engine.collectors.onchain.evm_common import (
    TRANSFER_TOPIC,
    build_default_token_registry,
    decode_transfer_value,
    get_web3,
    load_wallet_registry,
    topic_to_address,
)


COLLECTOR_META = {
    "collector_id": "exchange_flows",
    "priority": 1,
    "timeout_sec": 15,
    "enabled": True,
    "tags": ["onchain", "exchange", "flows", "chainstack"],
}

EXCHANGE_REGISTRY = "/opt/toknclaw/data/approved/exchange_wallets.json"
BLOCK_SCAN_DEPTH = int(os.getenv("TOKN_EXCHANGE_BLOCK_SCAN_DEPTH", "80"))
FLOW_USD_THRESHOLD = float(os.getenv("TOKN_EXCHANGE_FLOW_USD_THRESHOLD", "5000000"))


def fetch_exchange_flow_signals() -> List[Signal]:

    signals: List[Signal] = []

    w3 = get_web3("ethereum")
    if not w3:
        return signals

    wallets = load_wallet_registry(EXCHANGE_REGISTRY)
    if not wallets:
        return signals

    tokens = build_default_token_registry()

    try:
        latest_block = w3.eth.block_number
    except Exception:
        return signals

    for symbol, token in tokens.items():

        try:
            token_address = Web3.to_checksum_address(token["address"])
            decimals = int(token["decimals"])
            price = float(token["price"])
        except Exception:
            continue

        try:
            logs = w3.eth.get_logs(
                {
                    "fromBlock": max(0, latest_block - BLOCK_SCAN_DEPTH),
                    "toBlock": latest_block,
                    "address": token_address,
                    "topics": [TRANSFER_TOPIC],
                }
            )
        except Exception:
            continue

        for log in logs:

            try:
                if len(log["topics"]) < 3:
                    continue

                from_addr = topic_to_address(log["topics"][1])
                to_addr = topic_to_address(log["topics"][2])

                if not from_addr or not to_addr:
                    continue

                exchange_in = None
                exchange_out = None

                for exchange, addresses in wallets.items():
                    if to_addr in addresses:
                        exchange_in = exchange
                    if from_addr in addresses:
                        exchange_out = exchange

                if not exchange_in and not exchange_out:
                    continue

                raw_value = decode_transfer_value(log["data"])
                amount = raw_value / (10 ** decimals)
                value_usd = amount * price

                if value_usd < FLOW_USD_THRESHOLD:
                    continue

                timestamp = datetime.utcnow()

                if exchange_in:
                    signals.append(
                        Signal(
                            timestamp=timestamp,
                            source="chainstack",
                            signal_type="exchange_inflow",
                            entity=symbol,
                            title=f"${value_usd:,.0f} {symbol} moved to {exchange_in}",
                            summary=f"{amount:,.2f} {symbol} transferred into {exchange_in} from an external wallet.",
                            confidence=0.95,
                            sentiment_score=None,
                            raw_url=None,
                        )
                    )

                if exchange_out:
                    signals.append(
                        Signal(
                            timestamp=timestamp,
                            source="chainstack",
                            signal_type="exchange_outflow",
                            entity=symbol,
                            title=f"${value_usd:,.0f} {symbol} moved out of {exchange_out}",
                            summary=f"{amount:,.2f} {symbol} transferred out of {exchange_out} to an external wallet.",
                            confidence=0.93,
                            sentiment_score=None,
                            raw_url=None,
                        )
                    )

            except Exception:
                continue

    return signals
