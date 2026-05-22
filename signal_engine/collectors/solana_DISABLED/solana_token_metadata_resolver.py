#!/usr/bin/env python3
"""
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
# MODULE: solana_token_metadata_resolver
# PURPOSE: Resolve human-usable metadata for Solana memecoin and launch-related
#          mints already observed elsewhere in ToknClaw.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module enriches raw mint addresses into:

• token name
• token symbol
• token uri
• token decimals
• supply hints
• culture / meme name candidates
• ToknNews narrative enrichment inputs

Feeds
-----
• trading watchlists
• migration / post-migration analysis
• OpenClaw agents
• ToknNews enrichment
• Bitsy culture segments
• social summaries
• article generation

Detection Inputs
----------------
Reads recent signal lake signals such as:

• solana_pumpfun_launch
• solana_pumpfun_activity
• solana_raydium_pool_init
• solana_jupiter_swap
• solana_token_mint
• solana_stream events
• other mint-shaped Solana entities

Resolution Strategy
-------------------
1. collect candidate mints from signal lake
2. fetch mint account via Solana RPC
3. fetch metadata PDA account via Metaplex metadata program
4. parse on-chain metadata bytes when available
5. emit normalized enrichment signals
6. emit culture / funny-name candidates and summary signals

OpenClaw Agent Notes
--------------------
Agents should modify runtime behavior through config files, not code.

Primary Config
--------------
/opt/toknclaw/config/solana_metadata_resolver.json

Primary Data Inputs
-------------------
/opt/toknclaw/data/signal_lake.json

Author: TOKN Systems
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

from signal_engine.collectors.registry import register_collector
from models.signal import Signal
from runtime_config import load_config

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


# ---------------------------------------------------
# CONSTANTS
# ---------------------------------------------------

ENV_PATH = "/opt/toknclaw/signal_engine/.env"
CONFIG_NAME = "solana_metadata_resolver.json"
SIGNAL_LAKE_PATH = Path("/opt/toknclaw/data/signal_lake.json")

SOL_RPC = os.getenv("SOL_RPC", "").strip()
DEBUG = os.getenv("TOKN_DEBUG_COLLECTORS", "1") == "1"

METAPLEX_METADATA_PROGRAM = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "max_candidate_mints": 60,
    "max_signals_per_run": 120,
    "lookback_signal_count": 1500,
    "request_timeout_sec": 12,
    "emit_funny_name_candidates": True,
    "emit_summary": True,
    "emit_name_theme_signals": True,
    "min_name_length": 2,
    "max_name_length": 48,
    "symbol_min_length": 1,
    "symbol_max_length": 12,
    "funny_keywords": [
        "dog",
        "cat",
        "pepe",
        "bonk",
        "moon",
        "pump",
        "based",
        "chad",
        "wife",
        "frog",
        "elon",
        "trump",
        "gigachad",
        "wojak",
        "meme",
        "degen",
        "send",
        "rekt",
        "bag",
        "ai",
        "agent",
        "robot",
        "sigma",
        "tax",
        "fart",
        "butt",
        "toilet",
        "coin",
        "cash",
        "inu",
    ],
    "name_theme_keywords": {
        "animals": ["dog", "cat", "inu", "frog", "monkey", "shark", "cow", "rat"],
        "politics": ["trump", "biden", "maga", "elon", "rfk", "vote"],
        "internet": ["wojak", "meme", "chad", "sigma", "based", "npc"],
        "money": ["cash", "money", "dollar", "lambo", "moon", "bag", "pump"],
        "ai": ["ai", "agent", "gpt", "bot", "robot", "claw"],
    },
    "candidate_signal_types": [
        "solana_pumpfun_launch",
        "solana_pumpfun_activity",
        "solana_raydium_pool_init",
        "solana_jupiter_swap",
        "solana_token_mint",
        "solana_pumpfun_stream_event",
        "solana_raydium_stream_event",
        "solana_jupiter_stream_event",
        "solana_token_created",
        "solana_initial_liquidity",
    ],
}

TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
}

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_MAP = {c: i for i, c in enumerate(BASE58_ALPHABET)}


# ---------------------------------------------------
# LOGGING
# ---------------------------------------------------

def debug_log(message: str) -> None:
    if DEBUG:
        print(f"[SOLANA META RESOLVER] {message}")


def info_log(message: str) -> None:
    print(f"[SOLANA META RESOLVER] {message}")


def warn_log(message: str) -> None:
    print(f"[SOLANA META RESOLVER WARNING] {message}")


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

def load_resolver_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_NAME)

    if not isinstance(cfg, dict):
        return dict(DEFAULT_CONFIG)

    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


# ---------------------------------------------------
# GENERIC HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def read_signal_lake() -> Dict[str, Any]:
    if not SIGNAL_LAKE_PATH.exists():
        return {"signals": [], "collector_runs": {}, "updated_at": None}

    try:
        with open(SIGNAL_LAKE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"signals": [], "collector_runs": {}, "updated_at": None}
        return data
    except Exception as e:
        warn_log(f"failed to read signal lake error={e}")
        return {"signals": [], "collector_runs": {}, "updated_at": None}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def looks_like_base58(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    if len(value) < 32 or len(value) > 44:
        return False
    return all(ch in BASE58_ALPHABET for ch in value)


def looks_like_mint(value: Any) -> bool:
    text = clean_text(value)
    return looks_like_base58(text)


def dedupe_keep_order(values: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)

    return out


def shorten(text: str, n: int = 120) -> str:
    text = clean_text(text)
    if len(text) <= n:
        return text
    return text[: n - 3] + "..."


def stable_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------
# BASE58 / PDA HELPERS
# ---------------------------------------------------

def b58decode(data: str) -> bytes:
    num = 0
    for char in data:
        num = num * 58 + BASE58_MAP[char]

    combined = num.to_bytes((num.bit_length() + 7) // 8, byteorder="big")

    pad = 0
    for char in data:
        if char == "1":
            pad += 1
        else:
            break

    return b"\x00" * pad + combined


def b58encode(data: bytes) -> str:
    num = int.from_bytes(data, byteorder="big")

    encoded = ""
    while num > 0:
        num, rem = divmod(num, 58)
        encoded = BASE58_ALPHABET[rem] + encoded

    pad = 0
    for b in data:
        if b == 0:
            pad += 1
        else:
            break

    return "1" * pad + (encoded or "1")


def find_program_address_simple(seeds: List[bytes], program_id: str) -> str:
    """
    Simplified PDA derivation for metadata lookup.

    This does not verify ed25519 off-curve rigorously. It is a pragmatic
    resolver helper and may fail for some edge cases. When it fails, the
    resolver simply degrades gracefully.
    """
    program_bytes = b58decode(program_id)

    for bump in range(255, -1, -1):
        payload = b"".join(seeds) + bytes([bump]) + program_bytes + b"ProgramDerivedAddress"
        digest = sha256(payload).digest()
        return b58encode(digest)

    raise ValueError("unable to derive PDA")


def metadata_pda_for_mint(mint: str) -> Optional[str]:
    try:
        return find_program_address_simple(
            [
                b"metadata",
                b58decode(METAPLEX_METADATA_PROGRAM),
                b58decode(mint),
            ],
            METAPLEX_METADATA_PROGRAM,
        )
    except Exception as e:
        debug_log(f"metadata PDA failed mint={mint} error={e}")
        return None


# ---------------------------------------------------
# RPC HELPERS
# ---------------------------------------------------

def rpc(method: str, params: List[Any], timeout_sec: int) -> Optional[Dict[str, Any]]:
    if not SOL_RPC or not requests:
        return None

    try:
        response = requests.post(
            SOL_RPC,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params,
            },
            timeout=timeout_sec,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            debug_log(f"rpc error method={method} error={data.get('error')}")
        return data
    except Exception as e:
        debug_log(f"rpc failed method={method} error={e}")
        return None


def get_account_info(address: str, timeout_sec: int) -> Optional[Dict[str, Any]]:
    data = rpc(
        "getAccountInfo",
        [
            address,
            {
                "encoding": "base64",
                "commitment": "confirmed",
            },
        ],
        timeout_sec,
    )

    if not isinstance(data, dict):
        return None

    result = data.get("result")
    if not isinstance(result, dict):
        return None

    value = result.get("value")
    if not isinstance(value, dict):
        return None

    return value


def get_parsed_account_info(address: str, timeout_sec: int) -> Optional[Dict[str, Any]]:
    data = rpc(
        "getAccountInfo",
        [
            address,
            {
                "encoding": "jsonParsed",
                "commitment": "confirmed",
            },
        ],
        timeout_sec,
    )

    if not isinstance(data, dict):
        return None

    result = data.get("result")
    if not isinstance(result, dict):
        return None

    value = result.get("value")
    if not isinstance(value, dict):
        return None

    return value


# ---------------------------------------------------
# METADATA PARSING
# ---------------------------------------------------

def decode_base64_account_data(value: Dict[str, Any]) -> Optional[bytes]:
    data = value.get("data")
    if not isinstance(data, list) or not data:
        return None

    raw = data[0]
    if not isinstance(raw, str):
        return None

    try:
        return base64.b64decode(raw)
    except Exception:
        return None


def parse_metaplex_metadata_bytes(blob: bytes) -> Dict[str, Any]:
    """
    Best-effort parser for Metaplex metadata account.

    We only need practical extraction of name / symbol / uri.
    This parser uses known offsets for the string triplet section and
    degrades gracefully when the blob is not in expected shape.
    """
    out = {
        "name": "",
        "symbol": "",
        "uri": "",
    }

    if not blob or len(blob) < 80:
        return out

    try:
        offset = 1 + 32 + 32  # key + update_authority + mint

        name_len = int.from_bytes(blob[offset : offset + 4], "little")
        offset += 4
        name = blob[offset : offset + name_len].decode("utf-8", errors="ignore")
        offset += name_len

        symbol_len = int.from_bytes(blob[offset : offset + 4], "little")
        offset += 4
        symbol = blob[offset : offset + symbol_len].decode("utf-8", errors="ignore")
        offset += symbol_len

        uri_len = int.from_bytes(blob[offset : offset + 4], "little")
        offset += 4
        uri = blob[offset : offset + uri_len].decode("utf-8", errors="ignore")

        out["name"] = clean_text(name)
        out["symbol"] = clean_text(symbol)
        out["uri"] = clean_text(uri)
        return out
    except Exception:
        return out


def parse_mint_info(mint: str, timeout_sec: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "mint": mint,
        "decimals": None,
        "supply": None,
        "mint_authority": None,
        "freeze_authority": None,
        "token_program": None,
    }

    parsed = get_parsed_account_info(mint, timeout_sec)
    if not parsed:
        return out

    owner = parsed.get("owner")
    if isinstance(owner, str):
        out["token_program"] = owner

    parsed_data = parsed.get("data")
    if isinstance(parsed_data, dict):
        parsed_inner = parsed_data.get("parsed")
        if isinstance(parsed_inner, dict):
            info = parsed_inner.get("info")
            if isinstance(info, dict):
                out["decimals"] = info.get("decimals")
                out["supply"] = info.get("supply")
                out["mint_authority"] = info.get("mintAuthority")
                out["freeze_authority"] = info.get("freezeAuthority")

    return out


def resolve_metadata_for_mint(mint: str, timeout_sec: int) -> Dict[str, Any]:
    mint_info = parse_mint_info(mint, timeout_sec)

    metadata = {
        "mint": mint,
        "name": "",
        "symbol": "",
        "uri": "",
        "decimals": mint_info.get("decimals"),
        "supply": mint_info.get("supply"),
        "mint_authority": mint_info.get("mint_authority"),
        "freeze_authority": mint_info.get("freeze_authority"),
        "token_program": mint_info.get("token_program"),
        "metadata_pda": None,
        "resolved": False,
    }

    pda = metadata_pda_for_mint(mint)
    metadata["metadata_pda"] = pda

    if not pda:
        return metadata

    account = get_account_info(pda, timeout_sec)
    if not account:
        return metadata

    raw = decode_base64_account_data(account)
    if not raw:
        return metadata

    parsed = parse_metaplex_metadata_bytes(raw)

    name = clean_text(parsed.get("name"))
    symbol = clean_text(parsed.get("symbol"))
    uri = clean_text(parsed.get("uri"))

    metadata["name"] = name
    metadata["symbol"] = symbol
    metadata["uri"] = uri
    metadata["resolved"] = bool(name or symbol or uri)

    return metadata


# ---------------------------------------------------
# SIGNAL-LAKE CANDIDATE EXTRACTION
# ---------------------------------------------------

def object_signals_only(rows: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in rows:
        if isinstance(row, dict):
            out.append(row)

    return out


def extract_candidate_mints(
    signals: List[Dict[str, Any]],
    allowed_types: Set[str],
    max_candidates: int,
) -> List[str]:
    candidates: List[str] = []

    for row in reversed(signals):
        signal_type = clean_text(row.get("signal_type"))
        entity = clean_text(row.get("entity"))
        summary = clean_text(row.get("summary"))
        title = clean_text(row.get("title"))

        if signal_type in allowed_types and looks_like_mint(entity):
            candidates.append(entity)

        for text in [summary, title]:
            matches = re.findall(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", text)
            for match in matches:
                if looks_like_mint(match):
                    candidates.append(match)

    candidates = dedupe_keep_order(candidates)
    return candidates[:max_candidates]


# ---------------------------------------------------
# CULTURE / THEME HELPERS
# ---------------------------------------------------

def classify_name_theme(name: str, config: Dict[str, Any]) -> List[str]:
    lowered = clean_text(name).lower()
    if not lowered:
        return []

    theme_map = config.get("name_theme_keywords", {})
    if not isinstance(theme_map, dict):
        return []

    themes: List[str] = []

    for theme, keywords in theme_map.items():
        if not isinstance(keywords, list):
            continue

        for keyword in keywords:
            kw = clean_text(keyword).lower()
            if kw and kw in lowered:
                themes.append(clean_text(theme))
                break

    return themes


def is_funny_name_candidate(name: str, symbol: str, config: Dict[str, Any]) -> bool:
    funny_keywords = config.get("funny_keywords", [])
    if not isinstance(funny_keywords, list):
        funny_keywords = []

    joined = f"{clean_text(name)} {clean_text(symbol)}".lower()

    if not joined.strip():
        return False

    for keyword in funny_keywords:
        kw = clean_text(keyword).lower()
        if kw and kw in joined:
            return True

    if any(ch.isdigit() for ch in joined):
        return True

    if len(joined.split()) >= 2:
        return True

    return False


# ---------------------------------------------------
# SIGNAL BUILDERS
# ---------------------------------------------------

def build_metadata_signals(
    metadata_rows: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> List[Signal]:
    now = utc_now()
    signals: List[Signal] = []
    max_signals = int(config.get("max_signals_per_run", 120))
    emit_funny = bool(config.get("emit_funny_name_candidates", True))
    emit_theme = bool(config.get("emit_name_theme_signals", True))
    emit_summary = bool(config.get("emit_summary", True))

    theme_counter: Counter[str] = Counter()
    funny_rows: List[Tuple[str, str, str]] = []
    resolved_names = 0

    for row in metadata_rows:
        mint = clean_text(row.get("mint"))
        name = clean_text(row.get("name"))
        symbol = clean_text(row.get("symbol"))
        uri = clean_text(row.get("uri"))
        decimals = row.get("decimals")
        supply = row.get("supply")

        if not mint:
            continue

        if name or symbol or uri:
            resolved_names += 1

        if name:
            signals.append(
                Signal(
                    timestamp=now,
                    source="chainstack",
                    signal_type="solana_token_name_detected",
                    entity=mint,
                    title="Solana token name detected",
                    summary=f"Resolved token name for {mint}: {name}",
                    confidence=0.84,
                    sentiment_score=0.12,
                    raw_url=f"https://solscan.io/token/{mint}",
                )
            )

        if symbol:
            signals.append(
                Signal(
                    timestamp=now,
                    source="chainstack",
                    signal_type="solana_token_symbol_detected",
                    entity=mint,
                    title="Solana token symbol detected",
                    summary=f"Resolved token symbol for {mint}: {symbol}",
                    confidence=0.83,
                    sentiment_score=0.10,
                    raw_url=f"https://solscan.io/token/{mint}",
                )
            )

        if name or symbol or uri:
            summary_parts = []
            if name:
                summary_parts.append(f"name={name}")
            if symbol:
                summary_parts.append(f"symbol={symbol}")
            if uri:
                summary_parts.append(f"uri={shorten(uri, 80)}")
            if decimals is not None:
                summary_parts.append(f"decimals={decimals}")
            if supply:
                summary_parts.append(f"supply={supply}")

            signals.append(
                Signal(
                    timestamp=now,
                    source="chainstack",
                    signal_type="solana_token_metadata_resolved",
                    entity=mint,
                    title="Solana token metadata resolved",
                    summary=f"{mint} | " + " | ".join(summary_parts),
                    confidence=0.87,
                    sentiment_score=0.14,
                    raw_url=f"https://solscan.io/token/{mint}",
                )
            )

        themes = classify_name_theme(name or symbol, config)

        if emit_theme:
            for theme in themes:
                theme_counter[theme] += 1
                signals.append(
                    Signal(
                        timestamp=now,
                        source="toknclaw",
                        signal_type="solana_token_name_theme",
                        entity=mint,
                        title=f"Solana token name theme: {theme}",
                        summary=f"Resolved token {mint} classified under theme '{theme}' using name '{name or symbol}'.",
                        confidence=0.72,
                        sentiment_score=0.22,
                        raw_url=f"https://solscan.io/token/{mint}",
                    )
                )

        if emit_funny and is_funny_name_candidate(name, symbol, config):
            label = name or symbol or mint
            funny_rows.append((mint, name, symbol))
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_funny_name_candidate",
                    entity=mint,
                    title="Bitsy meme name candidate detected",
                    summary=f"Resolved Solana meme-name candidate: {label}",
                    confidence=0.79,
                    sentiment_score=0.41,
                    raw_url=f"https://solscan.io/token/{mint}",
                )
            )

        if len(signals) >= max_signals:
            info_log(f"max signal cap reached max_per_run={max_signals}")
            break

    if emit_summary:
        if funny_rows:
            top_funny = []
            for mint, name, symbol in funny_rows[:8]:
                label = clean_text(name) or clean_text(symbol) or mint
                top_funny.append(label)

            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_memecoin_name_summary",
                    entity="SOLANA_CULTURE",
                    title="Solana memecoin name summary",
                    summary="Top resolved meme-name candidates: " + ", ".join(top_funny),
                    confidence=0.74,
                    sentiment_score=0.36,
                    raw_url=None,
                )
            )

        if theme_counter:
            theme_text = ", ".join(
                f"{theme}({count})" for theme, count in theme_counter.most_common(5)
            )
            signals.append(
                Signal(
                    timestamp=now,
                    source="toknclaw",
                    signal_type="solana_name_theme_summary",
                    entity="SOLANA_CULTURE",
                    title="Solana memecoin naming themes emerging",
                    summary=f"Current naming themes: {theme_text}",
                    confidence=0.70,
                    sentiment_score=0.26,
                    raw_url=None,
                )
            )

    debug_log(
        f"metadata_rows={len(metadata_rows)} "
        f"resolved_names={resolved_names} "
        f"theme_hits={sum(theme_counter.values())} "
        f"funny_candidates={len(funny_rows)} "
        f"signals_returned={len(signals)}"
    )

    return signals[:max_signals]


# ---------------------------------------------------
# PUBLIC COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="solana_token_metadata_resolver",
    priority=2,
    tags=["solana", "metadata", "culture", "broadcast", "agents"],
    category="onchain",
)
def fetch_solana_token_metadata_resolver_signals() -> List[Signal]:

    started = time.time()
    cfg = load_resolver_config()

    signals: List[Signal] = []

    # ---------------------------------------------------
    # CONFIG GUARDS
    # ---------------------------------------------------

    if not bool(cfg.get("enabled", True)):
        info_log("[SOLANA META RESOLVER] disabled by config")
        return signals

    if not SOL_RPC:
        info_log("[SOLANA META RESOLVER] SOL_RPC missing")
        return signals

    if requests is None:
        info_log("[SOLANA META RESOLVER] requests library unavailable")
        return signals

    # ---------------------------------------------------
    # LOAD SIGNAL LAKE
    # ---------------------------------------------------

    lake = read_signal_lake()

    raw_signals = object_signals_only(
        lake.get("signals", [])
    )

    lookback_signal_count = int(
        cfg.get("lookback_signal_count", 1500)
    )

    candidate_rows = raw_signals[-lookback_signal_count:]

    # ---------------------------------------------------
    # CANDIDATE FILTER
    # ---------------------------------------------------

    allowed_types = {
        clean_text(x)
        for x in cfg.get("candidate_signal_types", [])
        if clean_text(x)
    }

    max_candidate_mints = int(
        cfg.get("max_candidate_mints", 60)
    )

    timeout_sec = int(
        cfg.get("request_timeout_sec", 12)
    )

    candidate_mints = extract_candidate_mints(
        signals=candidate_rows,
        allowed_types=allowed_types,
        max_candidates=max_candidate_mints,
    )

    if not candidate_mints:
        info_log("[SOLANA META RESOLVER] no candidate mints found")
        return signals

    debug_log(f"[SOLANA META RESOLVER] candidate_mints={len(candidate_mints)}")

    # ---------------------------------------------------
    # METADATA RESOLUTION
    # ---------------------------------------------------

    metadata_rows: List[Dict[str, Any]] = []

    for mint in candidate_mints:

        try:

            row = resolve_metadata_for_mint(
                mint,
                timeout_sec
            )

            if row:
                metadata_rows.append(row)

        except Exception as e:

            debug_log(
                f"[SOLANA META RESOLVER] metadata resolution failed mint={mint} error={e}"
            )

    # ---------------------------------------------------
    # BUILD SIGNALS
    # ---------------------------------------------------

    signals = build_metadata_signals(
        metadata_rows,
        cfg
    )

    debug_log(f"[SOLANA META RESOLVER] returning_signals={len(signals)}")

    # ---------------------------------------------------
    # SIGNAL CAP
    # ---------------------------------------------------

    max_per_run = int(
        cfg.get("max_signals_per_run", 200)
    )

    if len(signals) > max_per_run:

        signals = signals[:max_per_run]

        debug_log(
            f"[SOLANA META RESOLVER] max signal cap reached max_per_run={max_per_run}"
        )

    # ---------------------------------------------------
    # WRITE TO SIGNAL LAKE
    # ---------------------------------------------------

    # ---------------------------------------------------
    # WRITE TO SIGNAL LAKE (DISABLED — PIPELINE HANDLES THIS)
    # ---------------------------------------------------

    # NOTE:
    # ToknClaw pipeline aggregates collector outputs centrally.
    # Do NOT write to signal lake here to avoid duplication and race conditions.

    pass
    # ---------------------------------------------------
    # RUNTIME STATS
    # ---------------------------------------------------

    runtime = round(time.time() - started, 2)

    info_log(
        f"[SOLANA META RESOLVER] "
        f"candidate_mints={len(candidate_mints)} "
        f"metadata_rows={len(metadata_rows)} "
        f"signals_returned={len(signals)} "
        f"runtime={runtime}s"
    )

    return signals

# ---------------------------------------------------
# DIRECT TEST MODE
# ---------------------------------------------------

if __name__ == "__main__":
    rows = fetch_solana_token_metadata_resolver_signals()
    print(f"count = {len(rows)}")
    for row in rows[:20]:
        print(
            getattr(row, "signal_type", None),
            getattr(row, "entity", None),
            getattr(row, "title", None),
        )
