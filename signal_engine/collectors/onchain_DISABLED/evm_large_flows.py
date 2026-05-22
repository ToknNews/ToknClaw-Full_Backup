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
# MODULE: evm_large_flows
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
EVM Large Flow Collector

Purpose
-------

Scans multiple EVM chains for large token transfer activity.

Chains:

• Ethereum
• Base
• Arbitrum
• Monad

Feeds:

• entity_flow_graph
• institutional_flow_engine
• narrative_engine

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
    topic_to_address,
)


COLLECTOR_META = {
    "collector_id": "evm_large_flows",
    "priority": 2,
    "timeout_sec": 15,
    "enabled": True,
    "tags": ["onchain", "flows", "multichain", "chainstack"],
}

CHAINS = ["ethereum", "base", "arbitrum", "monad"]
BLOCK_SCAN_DEPTH = int(os.getenv("TOKN_EVM_FLOW_BLOCK_SCAN_DEPTH", "60"))
FLOW_USD_THRESHOLD = float(os.getenv("TOKN_EVM_FLOW_USD_THRESHOLD", "10000000"))


def fetch_evm_large_flow_signals() -> List[Signal]:

    signals: List[Signal] = []
    tokens = build_default_token_registry()

    for chain in CHAINS:

        w3 = get_web3(chain)
        if not w3:
            continue

        try:
            latest_block = w3.eth.block_number
        except Exception:
            continue

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

                    raw_value = decode_transfer_value(log["data"])
                    amount = raw_value / (10 ** decimals)
                    value_usd = amount * price

                    if value_usd < FLOW_USD_THRESHOLD:
                        continue

                    signals.append(
                        Signal(
                            timestamp=datetime.utcnow(),
                            source="chainstack",
                            signal_type="large_token_transfer",
                            entity=symbol,
                            title=f"${value_usd:,.0f} {symbol} moved on {chain}",
                            summary=f"{amount:,.2f} {symbol} transferred on {chain} from {from_addr[:10]}... to {to_addr[:10]}....",
                            confidence=0.91,
                            sentiment_score=None,
                            raw_url=None,
                        )
                    )

                except Exception:
                    continue

    return signals
