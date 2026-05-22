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
# MODULE: evm_common
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
EVM On-Chain Common Utilities

Purpose
-------

Shared helper layer for EVM-compatible Chainstack collectors.

Supports:

• Ethereum
• Base
• Arbitrum
• Monad

Provides:

• RPC client setup
• ERC20 transfer decoding
• wallet registry loading
• token registry loading
• standardized block scanning

Author: TOKN Systems
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Set

from web3 import Web3


TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()

DEFAULT_TOKEN_PRICES = {
    "USDT": 1.0,
    "USDC": 1.0,
    "DAI": 1.0,
    "FRAX": 1.0,
    "WETH": 3000.0,
    "WBTC": 65000.0,
    "STETH": 3000.0,
}


def get_rpc_url(chain: str) -> Optional[str]:
    env_map = {
        "ethereum": "ETH_RPC",
        "base": "BASE_RPC",
        "arbitrum": "ARB_RPC",
        "monad": "MONAD_RPC",
    }
    key = env_map.get(chain.lower())
    if not key:
        return None
    return os.getenv(key)


def get_web3(chain: str) -> Optional[Web3]:
    rpc_url = get_rpc_url(chain)
    if not rpc_url:
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            return None
        return w3
    except Exception:
        return None


def load_wallet_registry(path: str) -> Dict[str, Set[str]]:
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception:
        return {}

    wallets: Dict[str, Set[str]] = {}

    for label, addresses in data.items():
        clean = set()

        if not isinstance(addresses, list):
            continue

        for addr in addresses:
            if not isinstance(addr, str) or not addr.startswith("0x"):
                continue
            try:
                clean.add(Web3.to_checksum_address(addr))
            except Exception:
                continue

        if clean:
            wallets[label] = clean

    return wallets


def topic_to_address(topic: Any) -> Optional[str]:
    try:
        if isinstance(topic, bytes):
            topic = topic.hex()

        topic = str(topic).replace("0x", "")
        return Web3.to_checksum_address("0x" + topic[-40:])
    except Exception:
        return None


def decode_transfer_value(data: Any) -> int:
    try:
        if isinstance(data, bytes):
            return int.from_bytes(data, "big")
        if isinstance(data, str):
            return int(data, 16)
    except Exception:
        return 0
    return 0


def build_default_token_registry() -> Dict[str, Dict[str, Any]]:
    return {
        "USDT": {
            "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "decimals": 6,
            "price": DEFAULT_TOKEN_PRICES["USDT"],
        },
        "USDC": {
            "address": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "decimals": 6,
            "price": DEFAULT_TOKEN_PRICES["USDC"],
        },
        "DAI": {
            "address": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
            "decimals": 18,
            "price": DEFAULT_TOKEN_PRICES["DAI"],
        },
        "WETH": {
            "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "decimals": 18,
            "price": DEFAULT_TOKEN_PRICES["WETH"],
        },
        "WBTC": {
            "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
            "decimals": 8,
            "price": DEFAULT_TOKEN_PRICES["WBTC"],
        },
        "STETH": {
            "address": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
            "decimals": 18,
            "price": DEFAULT_TOKEN_PRICES["STETH"],
        },
    }
