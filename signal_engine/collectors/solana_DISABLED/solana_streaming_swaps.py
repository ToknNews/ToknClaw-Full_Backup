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
# MODULE: solana_streaming_swaps
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
Solana Streaming Swaps Daemon

Purpose
-------
Runs a production websocket streaming daemon for high-value Solana
program activity and appends enriched normalized signals directly into
the ToknClaw signal lake.

Responsibilities
----------------
• connect to Solana websocket endpoint
• subscribe to configured high-value programs
• receive live log notifications
• dedupe transaction signatures
• enrich each event with getTransaction()
• infer token / pair entities where possible
• append streaming signals into the signal lake
• support automatic reconnect and graceful shutdown
• support OpenClaw agent-controlled runtime config

Design Notes
------------
• standalone daemon (NOT a fetch_* collector)
• runs independently from snapshot engine
• OpenClaw agents should modify:
  /opt/toknclaw/config/solana_streaming.json

Primary Config
--------------
/opt/toknclaw/config/solana_streaming.json

Primary Output
--------------
/opt/toknclaw/data/signal_lake.json

Author: TOKN Systems
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# STANDARD LIBRARIES
# ---------------------------------------------------

import asyncio
import json
import os
import signal
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------
# THIRD PARTY
# ---------------------------------------------------

import requests
import websockets
from dotenv import load_dotenv

# ---------------------------------------------------
# TOKNCLAW MODULES
# ---------------------------------------------------

from models.signal import Signal
from runtime_config import load_config
from signal_lake import append_signals


# ---------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------

ENV_PATH = "/opt/toknclaw/signal_engine/.env"
load_dotenv(ENV_PATH)

SOL_RPC = os.getenv("SOL_RPC", "").strip()
DEBUG = os.getenv("TOKN_DEBUG_COLLECTORS", "1") == "1"

CONFIG_FILE = "solana_streaming.json"
HTTP_TIMEOUT = float(os.getenv("TOKN_SOL_STREAM_HTTP_TIMEOUT_SEC", "8"))
MAX_LOG_CHARS = int(os.getenv("TOKN_SOL_STREAM_MAX_LOG_CHARS", "400"))


# ---------------------------------------------------
# DEFAULT CONFIG
# ---------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "ws_url": "",
    "reconnect_delay_sec": 5,
    "max_signature_cache": 5000,
    "subscriptions": [
        {
            "name": "jupiter",
            "program_id": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
            "signal_type": "solana_jupiter_stream_event",
            "title": "Streaming Jupiter activity detected",
            "confidence": 0.82,
            "sentiment_score": 0.15,
            "entity": "SOLANA",
        },
        {
            "name": "raydium",
            "program_id": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
            "signal_type": "solana_raydium_stream_event",
            "title": "Streaming Raydium activity detected",
            "confidence": 0.83,
            "sentiment_score": 0.18,
            "entity": "SOLANA",
        },
        {
            "name": "pumpfun",
            "program_id": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
            "signal_type": "solana_pumpfun_stream_event",
            "title": "Streaming Pump.fun activity detected",
            "confidence": 0.86,
            "sentiment_score": 0.22,
            "entity": "SOLANA",
        },
    ],
}


# ---------------------------------------------------
# GLOBALS
# ---------------------------------------------------

SHUTDOWN = False

STABLE_MINTS: Set[str] = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
}


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def debug_log(message: str) -> None:
    if DEBUG:
        print(f"[SOLANA STREAM] {message}")


def info_log(message: str) -> None:
    print(f"[SOLANA STREAM] {message}")


def warn_log(message: str) -> None:
    print(f"[SOLANA STREAM WARNING] {message}")


def error_log(message: str) -> None:
    print(f"[SOLANA STREAM ERROR] {message}")


def build_ws_url() -> Optional[str]:
    cfg = load_streaming_config()

    explicit = str(cfg.get("ws_url", "")).strip()
    if explicit:
        return explicit

    if not SOL_RPC:
        return None

    if SOL_RPC.startswith("https://"):
        return SOL_RPC.replace("https://", "wss://", 1)

    if SOL_RPC.startswith("http://"):
        return SOL_RPC.replace("http://", "ws://", 1)

    return None


def load_streaming_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return DEFAULT_CONFIG

    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)

    subs = merged.get("subscriptions", [])
    if not isinstance(subs, list):
        merged["subscriptions"] = DEFAULT_CONFIG["subscriptions"]

    return merged


def utc_now() -> datetime:
    return datetime.utcnow()


def short_sig(sig: Optional[str], n: int = 12) -> str:
    if not sig:
        return "unknown"
    return sig[:n]


def install_signal_handlers() -> None:
    def _handle_shutdown(signum, frame):
        global SHUTDOWN
        SHUTDOWN = True
        info_log(f"shutdown requested signum={signum}")

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)


def build_subscription_message(program_id: str, request_id: int) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "logsSubscribe",
        "params": [
            {"mentions": [program_id]},
            {"commitment": "confirmed"},
        ],
    }


def extract_notification_payload(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(message, dict):
        return None

    params = message.get("params")
    if not isinstance(params, dict):
        return None

    result = params.get("result")
    if not isinstance(result, dict):
        return None

    value = result.get("value")
    if not isinstance(value, dict):
        return None

    return value


def get_transaction(signature: str) -> Optional[Dict[str, Any]]:
    if not SOL_RPC:
        return None

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    }

    try:
        r = requests.post(SOL_RPC, json=payload, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return data.get("result")
    except Exception as e:
        debug_log(f"getTransaction failed signature={short_sig(signature)} error={e}")
        return None


def _walk_instructions(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    transaction = tx.get("transaction") or {}
    message = transaction.get("message") or {}
    meta = tx.get("meta") or {}

    for ix in message.get("instructions") or []:
        if isinstance(ix, dict):
            out.append(ix)

    for inner_group in meta.get("innerInstructions") or []:
        for ix in inner_group.get("instructions") or []:
            if isinstance(ix, dict):
                out.append(ix)

    return out


def infer_entity_from_tx(tx: Optional[Dict[str, Any]], default_entity: str) -> str:
    if not tx:
        return default_entity

    instructions = _walk_instructions(tx)
    mints: List[str] = []

    for ix in instructions:
        parsed = ix.get("parsed")
        if not isinstance(parsed, dict):
            continue

        info = parsed.get("info") or {}
        if not isinstance(info, dict):
            continue

        for key in (
            "mint",
            "inputMint",
            "outputMint",
            "sourceMint",
            "destinationMint",
        ):
            value = info.get(key)
            if isinstance(value, str) and value not in mints:
                mints.append(value)

    if not mints:
        return default_entity

    non_stable = [m for m in mints if m not in STABLE_MINTS]

    if len(non_stable) >= 2:
        return f"{non_stable[0]} / {non_stable[1]}"

    if len(non_stable) == 1:
        if len(mints) >= 2:
            partner = mints[0] if mints[0] != non_stable[0] else mints[-1]
            return f"{non_stable[0]} / {partner}"
        return non_stable[0]

    if len(mints) >= 2:
        return f"{mints[0]} / {mints[1]}"

    return mints[0]


def trim_logs(logs: List[str]) -> str:
    joined = " | ".join(logs or [])
    if len(joined) > MAX_LOG_CHARS:
        return joined[:MAX_LOG_CHARS] + "..."
    return joined


def build_signal_from_notification(
    sub_cfg: Dict[str, Any],
    notification: Dict[str, Any],
) -> Optional[Signal]:
    signature = notification.get("signature")
    logs = notification.get("logs") or []
    err = notification.get("err")

    if err is not None:
        return None

    if not signature:
        return None

    program_id = str(sub_cfg.get("program_id", "")).strip()
    signal_type = str(sub_cfg.get("signal_type", "solana_stream_event")).strip()
    title = str(sub_cfg.get("title", "Streaming Solana activity detected")).strip()
    default_entity = str(sub_cfg.get("entity", "SOLANA")).strip()

    confidence = float(sub_cfg.get("confidence", 0.80))
    sentiment_score = sub_cfg.get("sentiment_score", None)

    tx = get_transaction(signature)
    entity = infer_entity_from_tx(tx, default_entity)

    summary = (
        f"{title} via program {program_id}. "
        f"entity={entity}. "
        f"signature={signature}. "
        f"logs={trim_logs(logs)}"
    )

    return Signal(
        timestamp=utc_now(),
        source="chainstack",
        signal_type=signal_type,
        entity=entity,
        title=title,
        summary=summary,
        confidence=confidence,
        sentiment_score=sentiment_score,
        raw_url=f"https://solscan.io/tx/{signature}",
    )


# ---------------------------------------------------
# STREAMER
# ---------------------------------------------------

class SignatureCache:
    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        self.order = deque()
        self.index = set()

    def seen(self, sig: str) -> bool:
        return sig in self.index

    def add(self, sig: str) -> None:
        if sig in self.index:
            return

        self.order.append(sig)
        self.index.add(sig)

        while len(self.order) > self.max_size:
            old = self.order.popleft()
            self.index.discard(old)


async def subscribe_program(
    ws: websockets.WebSocketClientProtocol,
    sub_cfg: Dict[str, Any],
    request_id: int,
) -> None:
    program_id = str(sub_cfg.get("program_id", "")).strip()
    name = str(sub_cfg.get("name", program_id)).strip()

    if not program_id:
        raise ValueError(f"subscription missing program_id name={name}")

    msg = build_subscription_message(program_id, request_id)
    await ws.send(json.dumps(msg))

    debug_log(f"subscribe sent name={name} program_id={program_id}")


async def run_stream_loop() -> None:
    cfg = load_streaming_config()

    enabled = bool(cfg.get("enabled", True))
    if not enabled:
        info_log("streaming disabled by config")
        return

    ws_url = build_ws_url()
    if not ws_url:
        raise RuntimeError("unable to determine websocket URL from config or SOL_RPC")

    reconnect_delay_sec = int(cfg.get("reconnect_delay_sec", 5))
    max_signature_cache = int(cfg.get("max_signature_cache", 5000))
    subscriptions = cfg.get("subscriptions", [])

    if not subscriptions:
        raise RuntimeError("no subscriptions configured in solana_streaming.json")

    sig_cache = SignatureCache(max_signature_cache)

    while not SHUTDOWN:
        try:
            info_log(f"connecting url={ws_url}")

            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
                max_size=2**22,
            ) as ws:

                info_log("connected")

                request_id = 1
                sub_map: Dict[str, Dict[str, Any]] = {}

                for sub_cfg in subscriptions:
                    await subscribe_program(ws, sub_cfg, request_id)
                    sub_map[str(request_id)] = sub_cfg
                    request_id += 1

                while not SHUTDOWN:
                    raw = await ws.recv()

                    try:
                        message = json.loads(raw)
                    except Exception as e:
                        warn_log(f"json parse failed error={e}")
                        continue

                    if "id" in message and "result" in message and "params" not in message:
                        ack_id = str(message.get("id"))
                        sub_cfg = sub_map.get(ack_id, {})
                        name = str(sub_cfg.get("name", "unknown"))
                        debug_log(f"subscription confirmed id={ack_id} name={name}")
                        continue

                    notification = extract_notification_payload(message)
                    if not notification:
                        continue

                    signature = notification.get("signature")
                    if not signature:
                        continue

                    if sig_cache.seen(signature):
                        continue

                    sig_cache.add(signature)

                    matched_cfg = None
                    logs = notification.get("logs") or []
                    logs_joined = " | ".join(logs)

                    for sub_cfg in subscriptions:
                        program_id = str(sub_cfg.get("program_id", "")).strip()
                        if program_id and program_id in logs_joined:
                            matched_cfg = sub_cfg
                            break

                    if matched_cfg is None and subscriptions:
                        matched_cfg = subscriptions[0]

                    if matched_cfg is None:
                        continue

                    signal_obj = build_signal_from_notification(matched_cfg, notification)
                    if not signal_obj:
                        continue

                    append_signals(
                        new_signals=[signal_obj],
                        collector_name=f"stream_{matched_cfg.get('name', 'solana')}",
                    )

                    debug_log(
                        f"signal appended name={matched_cfg.get('name')} "
                        f"signature={short_sig(signature)} "
                        f"signal_type={getattr(signal_obj, 'signal_type', None)} "
                        f"entity={getattr(signal_obj, 'entity', None)}"
                    )

        except asyncio.CancelledError:
            warn_log("stream loop cancelled")
            raise

        except KeyboardInterrupt:
            warn_log("keyboard interrupt")
            return

        except Exception as e:
            error_log(f"connection loop failed error={e}")

            if SHUTDOWN:
                break

            info_log(f"reconnecting in {reconnect_delay_sec}s")
            await asyncio.sleep(reconnect_delay_sec)


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

async def async_main() -> None:
    install_signal_handlers()
    await run_stream_loop()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        info_log("stopped by user")
    except Exception as e:
        error_log(f"fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
