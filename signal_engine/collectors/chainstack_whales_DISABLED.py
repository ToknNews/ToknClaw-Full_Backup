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
# MODULE: chainstack_whales
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

import os
from datetime import datetime

from dotenv import load_dotenv
from web3 import Web3

from models.signal import Signal

# Load environment
load_dotenv("/opt/toknclaw/signal_engine/.env")

ETH_RPC = os.getenv("ETH_RPC")

TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()

TOKENS = {
    "USDT": {
        "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "decimals": 6,
        "price": 1
    },
    "USDC": {
        "address": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "decimals": 6,
        "price": 1
    },
    "WETH": {
        "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "decimals": 18,
        "price": 3000
    },
    "WBTC": {
        "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "decimals": 8,
        "price": 65000
    },
}

BLOCK_SCAN_DEPTH = 50

# USD whale threshold
WHALE_USD_THRESHOLD = 5_000_000


def decode_value(data):

    if isinstance(data, bytes):
        return int.from_bytes(data, "big")

    if isinstance(data, str):
        return int(data, 16)

    return 0


def fetch_eth_whales():

    signals = []

    if not ETH_RPC:
        return signals

    try:

        w3 = Web3(Web3.HTTPProvider(ETH_RPC))

        if not w3.is_connected():
            return signals

        latest_block = w3.eth.block_number

        for symbol, token in TOKENS.items():

            address = Web3.to_checksum_address(token["address"])
            decimals = token["decimals"]
            price = token["price"]

            logs = w3.eth.get_logs({
                "fromBlock": latest_block - BLOCK_SCAN_DEPTH,
                "toBlock": latest_block,
                "address": address,
                "topics": [TRANSFER_TOPIC]
            })

            for log in logs:

                raw_value = decode_value(log["data"])

                amount = raw_value / (10 ** decimals)

                value_usd = amount * price

                if value_usd >= WHALE_USD_THRESHOLD:

                    signals.append(
                        Signal(
                            timestamp=datetime.utcnow(),
                            source="chainstack",
                            signal_type="whale_transfer",
                            entity=symbol,
                            title=f"${value_usd:,.0f} {symbol} whale transfer detected",
                            summary=f"{amount:,.0f} {symbol} transferred (~${value_usd:,.0f})",
                            confidence=0.92,
                            sentiment_score=None,
                            raw_url=None
                        )
                    )

    except Exception as e:

        print("Chainstack collector error:", e)

    return signals
