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
# MODULE: solana_pumpfun_launch_detector
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
Solana Pump.fun Launch Detector

Purpose
-------
Derive structured Pump.fun launch intelligence from recent
streaming Pump.fun events already stored in the ToknClaw signal lake.

Responsibilities
----------------
• read recent Pump.fun stream events from signal lake
• avoid duplicate processing via persistent state
• enrich launch events with getTransaction() when possible
• emit structured launch signals for:
  - solana_token_created
  - solana_initial_liquidity
  - solana_dev_wallet_detected
  - solana_pumpfun_launch
• support trading / bot workflows
• support ToknNews narrative and culture enrichment

Broadcast / Editorial Notes
---------------------------
These signals are intentionally written in a way that can support:
• top meme of the day
• funniest names / retail absurdity
• culture anchor commentary
• launch momentum narration
• memecoin trend roundups
• newsletter enrichment

Design Notes
------------
• this is a normal fetch_* collector
• it reads from the signal lake rather than directly from websocket
• it maintains a persistent processed-signature state file
• it is safe to run repeatedly inside the collector daemon

State File
----------
/opt/toknclaw/data/state/solana_pumpfun_launch_detector.json

Author: TOKN Systems
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from dotenv import load_dotenv

from signal_engine.collectors.registry import register_collector
from models.signal import Signal
from signal_lake import load_signal_lake


# ---------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------

ENV_PATH = "/opt/toknclaw/signal_engine/.env"
load_dotenv(ENV_PATH)

SOL_RPC = os.getenv("SOL_RPC", "").strip()
DEBUG = os.getenv("TOKN_DEBUG_COLLECTORS", "1") == "1"

HTTP_TIMEOUT = float(os.getenv("TOKN_SOL_PUMPFUN_HTTP_TIMEOUT_SEC", "8"))
LOOKBACK_MINUTES = int(os.getenv("TOKN_SOL_PUMPFUN_LOOKBACK_MINUTES", "30"))
MAX_EVENTS_PER_RUN = int(os.getenv("TOKN_SOL_PUMPFUN_MAX_EVENTS_PER_RUN", "100"))
STATE_RETENTION_DAYS = int(os.getenv("TOKN_SOL_PUMPFUN_STATE_RETENTION_DAYS", "7"))

STATE_PATH = Path("/opt/toknclaw/data/state/solana_pumpfun_launch_detector.json")
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Most Pump.fun mints end with "pump", but we should not require it.
MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


# ---------------------------------------------------
# DEBUG HELPERS
# ---------------------------------------------------

def debug_log(message: str) -> None:
    if DEBUG:
        print(f"[SOLANA PUMPFUN DETECTOR] {message}")


def warn_log(message: str) -> None:
    print(f"[SOLANA PUMPFUN DETECTOR WARNING] {message}")


# ---------------------------------------------------
# TIME HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if not isinstance(value, str):
        return None

    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


# ---------------------------------------------------
# STATE
# ---------------------------------------------------

def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"processed": {}}

    try:
        with open(STATE_PATH, "r") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"processed": {}}

        processed = data.get("processed", {})
        if not isinstance(processed, dict):
            processed = {}

        return {"processed": processed}

    except Exception:
        return {"processed": {}}


def save_state(state: Dict[str, Any]) -> None:
    tmp_path = STATE_PATH.with_suffix(".tmp")

    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2)

    tmp_path.replace(STATE_PATH)


def prune_state(state: Dict[str, Any]) -> Dict[str, Any]:
    processed = state.get("processed", {})
    if not isinstance(processed, dict):
        return {"processed": {}}

    cutoff = utc_now() - timedelta(days=STATE_RETENTION_DAYS)
    out: Dict[str, str] = {}

    for signature, ts in processed.items():
        dt = parse_dt(ts)
        if dt is None:
            continue
        if dt >= cutoff:
            out[signature] = dt.isoformat()

    return {"processed": out}


# ---------------------------------------------------
# RPC ENRICHMENT
# ---------------------------------------------------

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
        debug_log(f"getTransaction failed signature={signature[:12]} error={e}")
        return None


def extract_signers(tx: Optional[Dict[str, Any]]) -> List[str]:
    if not tx:
        return []

    transaction = tx.get("transaction") or {}
    message = transaction.get("message") or {}
    account_keys = message.get("accountKeys") or []

    signers: List[str] = []

    for row in account_keys:
        if isinstance(row, dict):
            pubkey = row.get("pubkey")
            signer = row.get("signer")
            if signer and isinstance(pubkey, str):
                signers.append(pubkey)

    return signers


def walk_instructions(tx: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not tx:
        return []

    out: List[Dict[str, Any]] = []

    transaction = tx.get("transaction") or {}
    message = transaction.get("message") or {}
    meta = tx.get("meta") or {}

    for ix in message.get("instructions") or []:
        if isinstance(ix, dict):
            out.append(ix)

    for group in meta.get("innerInstructions") or []:
        for ix in group.get("instructions") or []:
            if isinstance(ix, dict):
                out.append(ix)

    return out


def extract_mints_from_tx(tx: Optional[Dict[str, Any]]) -> List[str]:
    found: List[str] = []

    for ix in walk_instructions(tx):
        parsed = ix.get("parsed")
        if not isinstance(parsed, dict):
            continue

        info = parsed.get("info") or {}
        if not isinstance(info, dict):
            continue

        for key in ("mint", "inputMint", "outputMint", "sourceMint", "destinationMint"):
            value = info.get(key)
            if isinstance(value, str) and value not in found and MINT_RE.match(value):
                found.append(value)

    return found


def infer_probable_dev_wallet(tx: Optional[Dict[str, Any]]) -> Optional[str]:
    signers = extract_signers(tx)
    if signers:
        return signers[0]
    return None


def infer_initial_liquidity(tx: Optional[Dict[str, Any]]) -> bool:
    for ix in walk_instructions(tx):
        parsed = ix.get("parsed")
        if not isinstance(parsed, dict):
            continue

        ix_type = str(parsed.get("type", "")).lower()
        if ix_type in {
            "mintto",
            "minttochecked",
            "transfer",
            "transferchecked",
            "initializeaccount",
            "initializeaccount3",
        }:
            return True

    return False


# ---------------------------------------------------
# SIGNAL LAKE INPUT
# ---------------------------------------------------

def get_recent_pumpfun_stream_events() -> List[Dict[str, Any]]:
    lake = load_signal_lake()
    rows = lake.get("signals", [])
    if not isinstance(rows, list):
        return []

    cutoff = utc_now() - timedelta(minutes=LOOKBACK_MINUTES)
    out: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        if row.get("signal_type") != "solana_pumpfun_stream_event":
            continue

        dt = parse_dt(row.get("timestamp"))
        if dt is None or dt < cutoff:
            continue

        out.append(row)

    out.sort(key=lambda x: x.get("timestamp", ""))
    return out[-MAX_EVENTS_PER_RUN:]


def extract_signature_from_raw_url(raw_url: Optional[str]) -> Optional[str]:
    if not raw_url or not isinstance(raw_url, str):
        return None

    raw_url = raw_url.strip()
    if "/tx/" in raw_url:
        return raw_url.rsplit("/tx/", 1)[-1].strip()

    return None


def build_funny_name_signal(token_mint: str) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="solana_funny_name_candidate",
        entity=token_mint,
        title="Bitsy meme name candidate detected",
        summary=(
            f"Pump.fun launch detected for token {token_mint}. "
            f"Queue this mint for meme-name review, culture commentary, "
            f"and possible 'funniest name' ranking."
        ),
        confidence=0.62,
        sentiment_score=0.35,
        raw_url=f"https://solscan.io/token/{token_mint}",
    )


# ---------------------------------------------------
# COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="solana_pumpfun_launch_detector",
    priority=1,
    tags=["solana", "pumpfun", "launch", "memecoin", "broadcast", "trading"],
    timeout=12,
)
def fetch_solana_pumpfun_launch_signals() -> List[Signal]:
    state = prune_state(load_state())
    processed: Dict[str, str] = state.get("processed", {})
    events = get_recent_pumpfun_stream_events()

    signals: List[Signal] = []
    launch_count = 0

    for row in events:
        signature = extract_signature_from_raw_url(row.get("raw_url"))
        if not signature:
            continue

        if signature in processed:
            continue

        token_mint = row.get("entity")
        tx = get_transaction(signature)

        mints = extract_mints_from_tx(tx)
        if isinstance(token_mint, str) and token_mint not in mints and MINT_RE.match(token_mint):
            mints.insert(0, token_mint)

        if not mints:
            processed[signature] = utc_now().isoformat()
            continue

        primary_mint = mints[0]
        dev_wallet = infer_probable_dev_wallet(tx)
        has_liquidity = infer_initial_liquidity(tx)

        # 1) token created
        signals.append(
            Signal(
                timestamp=utc_now(),
                source="toknclaw",
                signal_type="solana_token_created",
                entity=primary_mint,
                title="New Solana token created on Pump.fun",
                summary=(
                    f"Pump.fun launch path detected for token {primary_mint}. "
                    f"signature={signature}"
                ),
                confidence=0.83,
                sentiment_score=0.30,
                raw_url=f"https://solscan.io/token/{primary_mint}",
            )
        )

        # 2) initial liquidity
        if has_liquidity:
            signals.append(
                Signal(
                    timestamp=utc_now(),
                    source="toknclaw",
                    signal_type="solana_initial_liquidity",
                    entity=primary_mint,
                    title="Initial liquidity activity detected",
                    summary=(
                        f"Probable initial liquidity or token distribution "
                        f"detected for {primary_mint} on Pump.fun launch path."
                    ),
                    confidence=0.77,
                    sentiment_score=0.22,
                    raw_url=f"https://solscan.io/tx/{signature}",
                )
            )

        # 3) dev wallet
        if dev_wallet:
            signals.append(
                Signal(
                    timestamp=utc_now(),
                    source="toknclaw",
                    signal_type="solana_dev_wallet_detected",
                    entity=primary_mint,
                    title="Probable dev wallet detected",
                    summary=(
                        f"Probable developer / deployer wallet {dev_wallet} "
                        f"associated with Pump.fun token {primary_mint}."
                    ),
                    confidence=0.74,
                    sentiment_score=0.05,
                    raw_url=f"https://solscan.io/account/{dev_wallet}",
                )
            )

        # 4) launch summary
        launch_summary_bits = [f"token={primary_mint}"]
        if dev_wallet:
            launch_summary_bits.append(f"dev_wallet={dev_wallet}")
        if has_liquidity:
            launch_summary_bits.append("initial_liquidity=true")

        signals.append(
            Signal(
                timestamp=utc_now(),
                source="toknclaw",
                signal_type="solana_pumpfun_launch",
                entity=primary_mint,
                title="Pump.fun launch detected",
                summary=(
                    "Structured Pump.fun launch detected: "
                    + ", ".join(launch_summary_bits)
                ),
                confidence=0.88,
                sentiment_score=0.42,
                raw_url=f"https://solscan.io/tx/{signature}",
            )
        )

        # 5) broadcast / culture hook
        signals.append(build_funny_name_signal(primary_mint))

        processed[signature] = utc_now().isoformat()
        launch_count += 1

    state["processed"] = processed
    save_state(state)

    debug_log(
        f"events_scanned={len(events)} launches_emitted={launch_count} "
        f"signals_returned={len(signals)}"
    )

    return signals
