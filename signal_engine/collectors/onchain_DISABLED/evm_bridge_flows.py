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
# MODULE: evm_bridge_flows
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
EVM Bridge Flow Collector

Purpose
-------

Tracks large transfers involving known bridge wallets and contracts.

Feeds:

• cross_asset_intelligence_engine
• liquidity_rotation_engine
• institutional_flow_engine

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
    "collector_id": "evm_bridge_flows",
    "priority": 2,
    "timeout_sec": 15,
    "enabled": True,
    "tags": ["bridge", "onchain", "multichain", "chainstack"],
}

BRIDGE_REGISTRY = "/opt/toknclaw/data/approved/bridge_wallets.json"
BLOCK_SCAN_DEPTH = int(os.getenv("TOKN_EVM_BRIDGE_BLOCK_SCAN_DEPTH", "80"))
FLOW_USD_THRESHOLD = float(os.getenv("TOKN_EVM_BRIDGE_FLOW_USD_THRESHOLD", "5000000"))
CHAINS = ["ethereum", "base", "arbitrum"]


def fetch_evm_bridge_flow_signals() -> List[Signal]:

    signals: List[Signal] = []
    bridges = load_wallet_registry(BRIDGE_REGISTRY)
    if not bridges:
        return signals

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

                    bridge_in = None
                    bridge_out = None

                    for bridge, addresses in bridges.items():
                        if to_addr in addresses:
                            bridge_in = bridge
                        if from_addr in addresses:
                            bridge_out = bridge

                    if not bridge_in and not bridge_out:
                        continue

                    raw_value = decode_transfer_value(log["data"])
                    amount = raw_value / (10 ** decimals)
                    value_usd = amount * price

                    if value_usd < FLOW_USD_THRESHOLD:
                        continue

                    if bridge_in:
                        signals.append(
                            Signal(
                                timestamp=datetime.utcnow(),
                                source="chainstack",
                                signal_type="bridge_inflow",
                                entity=symbol,
                                title=f"${value_usd:,.0f} {symbol} bridged into {bridge_in}",
                                summary=f"{amount:,.2f} {symbol} transferred into bridge endpoint {bridge_in} on {chain}.",
                                confidence=0.92,
                                sentiment_score=None,
                                raw_url=None,
                            )
                        )

                    if bridge_out:
                        signals.append(
                            Signal(
                                timestamp=datetime.utcnow(),
                                source="chainstack",
                                signal_type="bridge_outflow",
                                entity=symbol,
                                title=f"${value_usd:,.0f} {symbol} bridged out of {bridge_out}",
                                summary=f"{amount:,.2f} {symbol} transferred out of bridge endpoint {bridge_out} on {chain}.",
                                confidence=0.90,
                                sentiment_score=None,
                                raw_url=None,
                            )
                        )

                except Exception:
                    continue

    return signals
