#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — PRICE ENGINE
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
# MODULE: price_engine
# PURPOSE:
# - Maintain live token/perp price history for trading and analytics
# - Prefer Hyperliquid allMids for Hyperliquid-enabled perp markets
# - Expand price coverage across trading_universe.json enabled assets
# - Preserve CoinGecko fallback and Dexscreener mint support
# - Feed relative strength, market structure, paper trading, and execution audits
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path("/opt/toknclaw")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import json
import os
import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from signal_engine.runtime_config import load_config

# ---------------------------------------------------
# PATHS / CONFIG
# ---------------------------------------------------

PRICE_PATH = Path("/opt/toknclaw/data/token_price_history.json")
TMP_PATH = Path("/opt/toknclaw/data/token_price_history.tmp")

TRADING_UNIVERSE_PATH = Path("/opt/toknclaw/config/trading_universe.json")

CONFIG_FILE = "price_engine.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "max_history_per_token": 200,
    "request_timeout": 8,

    "use_hyperliquid_all_mids": True,
    "track_enabled_universe": True,
    "prefer_hyperliquid_for_core": True,

    "force_track_entities": [
        "BTC",
        "ETH",
        "SOL",
        "BNB",
        "XRP",
        "DOGE",
        "LINK",
        "AVAX",
        "ARB",
        "OP",
        "INJ",
        "PYTH",
        "JUP",
        "RNDR"
    ],

    "coingecko_id_map": {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "DOGE": "dogecoin",
        "LINK": "chainlink",
        "AVAX": "avalanche-2",
        "ARB": "arbitrum",
        "OP": "optimism",
        "INJ": "injective-protocol",
        "PYTH": "pyth-network",
        "JUP": "jupiter-exchange-solana",
        "RNDR": "render-token",
        "RENDER": "render-token"
    },

    "skip_entity_prefixes": [
        "SOLANA_",
        "RAYDIUM_",
        "JUPITER_",
        "PUMPFUN_",
        "THEME_",
        "PERP_"
    ]
}

HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
COINGECKO_SIMPLE_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{token}"

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def debug(cfg: Dict[str, Any], msg: str) -> None:
    if cfg.get("debug"):
        print("[PRICE ENGINE]", msg, flush=True)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def clean_upper(value: Any) -> str:
    return clean_text(value).upper()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False

    if isinstance(value, (int, float)):
        return bool(value)

    return default


def safe_dict(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict):
        return x

    if hasattr(x, "__dict__"):
        try:
            return dict(x.__dict__)
        except Exception:
            return {}

    return {}


def safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    unique_tmp = tmp_path.with_name(
        f"{tmp_path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )

    with open(unique_tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    unique_tmp.replace(path)


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return deepcopy(DEFAULT_CONFIG)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)

    if not isinstance(merged.get("force_track_entities"), list):
        merged["force_track_entities"] = deepcopy(DEFAULT_CONFIG["force_track_entities"])
    else:
        merged["force_track_entities"] = [
            clean_upper(x)
            for x in merged["force_track_entities"]
            if clean_text(x)
        ]

    if not isinstance(merged.get("coingecko_id_map"), dict):
        merged["coingecko_id_map"] = deepcopy(DEFAULT_CONFIG["coingecko_id_map"])
    else:
        merged["coingecko_id_map"] = {
            clean_upper(k): clean_text(v)
            for k, v in merged["coingecko_id_map"].items()
            if clean_text(k) and clean_text(v)
        }

    if not isinstance(merged.get("skip_entity_prefixes"), list):
        merged["skip_entity_prefixes"] = deepcopy(DEFAULT_CONFIG["skip_entity_prefixes"])
    else:
        merged["skip_entity_prefixes"] = [
            clean_text(x)
            for x in merged["skip_entity_prefixes"]
            if clean_text(x)
        ]

    return merged


def is_probable_mint(entity: str) -> bool:
    text = clean_text(entity)

    if not text:
        return False

    if " " in text:
        return False

    if "/" in text:
        return False

    return len(text) >= 20


def is_skipped_entity(entity: str, cfg: Dict[str, Any]) -> bool:
    text = clean_text(entity)
    upper = text.upper()

    if not text:
        return True

    for prefix in cfg.get("skip_entity_prefixes", []):
        if upper.startswith(clean_text(prefix).upper()):
            return True

    return False

# ---------------------------------------------------
# UNIVERSE EXTRACTION
# ---------------------------------------------------

def enabled_universe_entities(cfg: Dict[str, Any]) -> Set[str]:
    if not safe_bool(cfg.get("track_enabled_universe"), True):
        return set()

    raw = read_json(TRADING_UNIVERSE_PATH, {})
    universe = safe_dict(raw)

    tiers = safe_dict(universe.get("tiers"))
    enabled_tiers = safe_list(universe.get("enabled_tiers"))

    entities: Set[str] = set()

    for tier in enabled_tiers:
        for asset in safe_list(tiers.get(tier)):
            asset = clean_upper(asset)

            if not asset:
                continue

            if is_skipped_entity(asset, cfg):
                continue

            entities.add(asset)

    return entities

# ---------------------------------------------------
# ENTITY EXTRACTION
# ---------------------------------------------------

def extract_entities_from_signals(snapshot: Dict[str, Any], cfg: Dict[str, Any]) -> Set[str]:
    entities: Set[str] = set()

    for raw in snapshot.get("signals", []):
        row = safe_dict(raw)
        entity = clean_text(row.get("entity"))

        if not entity:
            continue

        if is_skipped_entity(entity, cfg):
            continue

        if " / " in entity:
            parts = [clean_text(x) for x in entity.split(" / ") if clean_text(x)]
            for part in parts:
                if is_skipped_entity(part, cfg):
                    continue
                if is_probable_mint(part):
                    entities.add(part)
            continue

        if is_probable_mint(entity):
            entities.add(entity)

    return entities


def extract_entities_from_trade_signals(snapshot: Dict[str, Any], cfg: Dict[str, Any]) -> Set[str]:
    entities: Set[str] = set()

    trade_signals = safe_dict(snapshot.get("trade_signals"))
    rows = trade_signals.get("rows", [])

    if not isinstance(rows, list):
        return entities

    for row in rows:
        row = safe_dict(row)
        entity = clean_upper(row.get("entity"))

        if not entity:
            continue

        if is_skipped_entity(entity, cfg):
            continue

        entities.add(entity)

    return entities


def extract_entities(snapshot: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[Set[str], Set[str]]:
    """
    Returns:
        (mint_entities, core_entities)
    """

    mint_entities = extract_entities_from_signals(snapshot, cfg)
    core_entities = extract_entities_from_trade_signals(snapshot, cfg)

    for entity in cfg.get("force_track_entities", []):
        core_entities.add(clean_upper(entity))

    for entity in enabled_universe_entities(cfg):
        core_entities.add(clean_upper(entity))

    return mint_entities, core_entities

# ---------------------------------------------------
# PRICE FETCHERS
# ---------------------------------------------------

def fetch_hyperliquid_all_mids(cfg: Dict[str, Any]) -> Dict[str, float]:
    if not safe_bool(cfg.get("use_hyperliquid_all_mids"), True):
        return {}

    timeout = int(cfg.get("request_timeout", 8))

    try:
        response = requests.post(
            HYPERLIQUID_INFO_URL,
            json={"type": "allMids"},
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ToknClaw/1.0",
            },
        )

        if response.status_code != 200:
            debug(cfg, f"hyperliquid_all_mids_status={response.status_code}")
            return {}

        payload = response.json()

        if not isinstance(payload, dict):
            return {}

        out: Dict[str, float] = {}

        for key, value in payload.items():
            entity = clean_upper(key)
            price = safe_float(value, 0.0)

            if entity and price > 0:
                out[entity] = price

        return out

    except Exception as exc:
        debug(cfg, f"hyperliquid_all_mids_error={exc}")
        return {}


def fetch_dexscreener_price(token: str, timeout: int) -> Optional[float]:
    try:
        url = DEXSCREENER_TOKEN_URL.format(token=token)
        response = requests.get(url, timeout=timeout)

        if response.status_code != 200:
            return None

        data = response.json()
        pairs = data.get("pairs", [])

        if not isinstance(pairs, list) or not pairs:
            return None

        best_pair = None
        best_liquidity = -1.0

        for pair in pairs:
            if not isinstance(pair, dict):
                continue

            liquidity_usd = safe_float(safe_dict(pair.get("liquidity")).get("usd"), 0.0)
            if liquidity_usd > best_liquidity:
                best_liquidity = liquidity_usd
                best_pair = pair

        if not isinstance(best_pair, dict):
            return None

        price = safe_float(best_pair.get("priceUsd"), 0.0)
        if price > 0:
            return price

    except Exception:
        return None

    return None


def fetch_coingecko_prices(entities: List[str], cfg: Dict[str, Any]) -> Dict[str, float]:
    id_map = cfg.get("coingecko_id_map", {})
    timeout = int(cfg.get("request_timeout", 8))

    requested_ids: List[str] = []
    entity_to_id: Dict[str, str] = {}

    for entity in entities:
        coin_id = clean_text(id_map.get(clean_upper(entity)))
        if not coin_id:
            continue

        entity_to_id[clean_upper(entity)] = coin_id
        requested_ids.append(coin_id)

    requested_ids = sorted(set(requested_ids))
    if not requested_ids:
        return {}

    try:
        response = requests.get(
            COINGECKO_SIMPLE_PRICE_URL,
            params={
                "ids": ",".join(requested_ids),
                "vs_currencies": "usd",
                "include_last_updated_at": "true",
            },
            timeout=timeout,
        )

        if response.status_code != 200:
            return {}

        payload = response.json()
        if not isinstance(payload, dict):
            return {}

    except Exception:
        return {}

    prices: Dict[str, float] = {}

    for entity, coin_id in entity_to_id.items():
        row = safe_dict(payload.get(coin_id))
        price = safe_float(row.get("usd"), 0.0)

        if price > 0:
            prices[entity] = price

    return prices

# ---------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------

def append_price_point(
    tokens: Dict[str, Any],
    entity: str,
    price: float,
    cfg: Dict[str, Any],
    source: str,
) -> bool:
    if price <= 0:
        return False

    entity = clean_upper(entity)

    history = tokens.setdefault(entity, [])
    if not isinstance(history, list):
        tokens[entity] = []
        history = tokens[entity]

    history.append(
        {
            "timestamp": now_iso(),
            "price_usd": round(price, 12),
            "source": source,
        }
    )

    max_len = int(cfg.get("max_history_per_token", 200))
    if len(history) > max_len:
        tokens[entity] = history[-max_len:]

    return True


def update_price_history(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_engine_config()

    if not bool(cfg.get("enabled", True)):
        return {}

    data = read_json(PRICE_PATH, {"tokens": {}})
    tokens = data.setdefault("tokens", {})

    if not isinstance(tokens, dict):
        data["tokens"] = {}
        tokens = data["tokens"]

    mint_entities, core_entities = extract_entities(snapshot, cfg)

    debug(cfg, f"mint_entities={len(mint_entities)} core_entities={len(core_entities)}")

    updated_mints = 0
    updated_cores = 0
    hyperliquid_updates = 0
    coingecko_updates = 0

    # ---------------------------------------------------
    # CORE ENTITY PRICES — HYPERLIQUID ALL MIDS FIRST
    # ---------------------------------------------------

    remaining_core_entities = set(core_entities)

    hyperliquid_prices = fetch_hyperliquid_all_mids(cfg)

    for entity in sorted(core_entities):
        price = safe_float(hyperliquid_prices.get(entity), 0.0)

        if price <= 0:
            continue

        if append_price_point(tokens, entity, price, cfg, source="hyperliquid_all_mids"):
            updated_cores += 1
            hyperliquid_updates += 1
            remaining_core_entities.discard(entity)

    # ---------------------------------------------------
    # CORE ENTITY FALLBACK — COINGECKO MAPPED IDS
    # ---------------------------------------------------

    core_prices = fetch_coingecko_prices(sorted(remaining_core_entities), cfg)

    for entity, price in core_prices.items():
        if append_price_point(tokens, entity, price, cfg, source="coingecko"):
            updated_cores += 1
            coingecko_updates += 1

    # ---------------------------------------------------
    # MINT / TOKEN PRICES — DEXSCREENER
    # ---------------------------------------------------

    timeout = int(cfg.get("request_timeout", 8))

    for token in sorted(mint_entities):
        price = fetch_dexscreener_price(token, timeout)
        if price is None:
            continue

        if append_price_point(tokens, token, price, cfg, source="dexscreener"):
            updated_mints += 1

    data["updated_at"] = now_iso()
    data["meta"] = {
        "core_entities_tracked": sorted(core_entities),
        "mint_entities_tracked_count": len(mint_entities),
        "updated_core_entities": updated_cores,
        "updated_mint_entities": updated_mints,
        "hyperliquid_updates": hyperliquid_updates,
        "coingecko_updates": coingecko_updates,
        "total_tokens_keys": len(tokens),
    }

    write_atomic(PRICE_PATH, TMP_PATH, data)

    debug(
        cfg,
        f"updated_core_entities={updated_cores} "
        f"hyperliquid_updates={hyperliquid_updates} "
        f"coingecko_updates={coingecko_updates} "
        f"updated_mint_entities={updated_mints} "
        f"total_tokens_keys={len(tokens)}"
    )

    return data

# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main() -> None:
    snapshot_path = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")

    if not snapshot_path.exists():
        return

    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    update_price_history(snapshot)


if __name__ == "__main__":
    main()
