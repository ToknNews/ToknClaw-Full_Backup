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
# MODULE: defi_liquidations
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

import os
from datetime import datetime

from dotenv import load_dotenv
from web3 import Web3

from models.signal import Signal

load_dotenv("/opt/toknclaw/signal_engine/.env")

ETH_RPC = os.getenv("ETH_RPC")

# Aave V3 liquidation event topic
AAVE_LIQUIDATION_TOPIC = Web3.keccak(
    text="LiquidationCall(address,address,address,uint256,uint256,address,bool)"
).hex()

BLOCK_SCAN_DEPTH = 100

LIQUIDATION_USD_THRESHOLD = 1_000_000


def fetch_defi_liquidations():

    signals = []

    if not ETH_RPC:
        return signals

    try:

        w3 = Web3(Web3.HTTPProvider(ETH_RPC))

        if not w3.is_connected():
            return signals

        latest_block = w3.eth.block_number

        logs = w3.eth.get_logs({
            "fromBlock": latest_block - BLOCK_SCAN_DEPTH,
            "toBlock": latest_block,
            "topics": [AAVE_LIQUIDATION_TOPIC]
        })

        for log in logs:

            signals.append(
                Signal(
                    timestamp=datetime.utcnow(),
                    source="chainstack",
                    signal_type="defi_liquidation",
                    entity="ETH",
                    title="DeFi liquidation detected (Aave)",
                    summary=f"Aave liquidation event detected in block {log['blockNumber']}",
                    confidence=0.9,
                    sentiment_score=None,
                    raw_url=None
                )
            )

    except Exception as e:

        print("DeFi liquidation collector error:", e)

    return signals
