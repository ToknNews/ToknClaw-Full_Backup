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
# MODULE: asset_registry_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


ASSET_DIR = Path("/opt/toknclaw/data/assets")
ASSET_DIR.mkdir(parents=True, exist_ok=True)

REGISTRY_PATH = ASSET_DIR / "asset_registry.json"
DISCOVERED_PATH = ASSET_DIR / "discovered_entities.json"

REGISTRY_VERSION = 1


STATIC_TOKENS = {
    "BTC": {"name": "Bitcoin", "symbol": "BTC", "entity_type": "token", "sector": "store_of_value", "chain": "bitcoin"},
    "ETH": {"name": "Ethereum", "symbol": "ETH", "entity_type": "token", "sector": "smart_contract", "chain": "ethereum"},
    "SOL": {"name": "Solana", "symbol": "SOL", "entity_type": "token", "sector": "smart_contract", "chain": "solana"},
    "ADA": {"name": "Cardano", "symbol": "ADA", "entity_type": "token", "sector": "smart_contract", "chain": "cardano"},
    "BNB": {"name": "BNB", "symbol": "BNB", "entity_type": "token", "sector": "exchange", "chain": "bnb"},
    "XRP": {"name": "XRP", "symbol": "XRP", "entity_type": "token", "sector": "payments", "chain": "xrpl"},
    "DOGE": {"name": "Dogecoin", "symbol": "DOGE", "entity_type": "token", "sector": "meme", "chain": "dogecoin"},
    "PEPE": {"name": "Pepe", "symbol": "PEPE", "entity_type": "token", "sector": "meme", "chain": "ethereum"},
    "PENGU": {"name": "Pudgy Penguins", "symbol": "PENGU", "entity_type": "token", "sector": "meme", "chain": "solana"},
    "LDO": {"name": "Lido DAO", "symbol": "LDO", "entity_type": "token", "sector": "defi", "chain": "ethereum"},
    "AAVE": {"name": "Aave", "symbol": "AAVE", "entity_type": "token", "sector": "defi", "chain": "ethereum"},
    "UNI": {"name": "Uniswap", "symbol": "UNI", "entity_type": "token", "sector": "defi", "chain": "ethereum"},
    "PENDLE": {"name": "Pendle", "symbol": "PENDLE", "entity_type": "token", "sector": "defi", "chain": "ethereum"},
    "SSV": {"name": "SSV Network", "symbol": "SSV", "entity_type": "token", "sector": "defi", "chain": "ethereum"},
    "USDT": {"name": "Tether", "symbol": "USDT", "entity_type": "stablecoin", "sector": "stablecoin", "chain": "multi"},
    "USDC": {"name": "USD Coin", "symbol": "USDC", "entity_type": "stablecoin", "sector": "stablecoin", "chain": "multi"},
    "WBTC": {"name": "Wrapped Bitcoin", "symbol": "WBTC", "entity_type": "wrapped_asset", "sector": "btc_beta", "chain": "ethereum"},
    "WETH": {"name": "Wrapped Ether", "symbol": "WETH", "entity_type": "wrapped_asset", "sector": "eth_beta", "chain": "ethereum"},
}

STATIC_PROTOCOLS = {
    "AAVE": {"name": "Aave", "symbol": "AAVE", "entity_type": "protocol", "sector": "defi", "category": "lending", "chain": "ethereum"},
    "UNISWAP": {"name": "Uniswap", "symbol": "UNI", "entity_type": "protocol", "sector": "defi", "category": "dex", "chain": "ethereum"},
    "PENDLE": {"name": "Pendle", "symbol": "PENDLE", "entity_type": "protocol", "sector": "defi", "category": "yield", "chain": "ethereum"},
    "LIDO": {"name": "Lido", "symbol": "LDO", "entity_type": "protocol", "sector": "defi", "category": "staking", "chain": "ethereum"},
    "SSV NETWORK": {"name": "SSV Network", "symbol": "SSV", "entity_type": "protocol", "sector": "defi", "category": "staking_infra", "chain": "ethereum"},
    "BYBIT": {"name": "Bybit", "symbol": None, "entity_type": "exchange", "sector": "exchange", "category": "cex", "chain": None},
}

STATIC_CHAINS = {
    "BITCOIN": {"name": "Bitcoin", "entity_type": "chain", "sector": "layer1"},
    "ETHEREUM": {"name": "Ethereum", "entity_type": "chain", "sector": "layer1"},
    "SOLANA": {"name": "Solana", "entity_type": "chain", "sector": "layer1"},
    "BASE": {"name": "Base", "entity_type": "chain", "sector": "layer2"},
    "ARBITRUM": {"name": "Arbitrum", "entity_type": "chain", "sector": "layer2"},
}


def _now_ts() -> int:
    return int(time.time())


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def initialize_asset_registry() -> None:
    if not REGISTRY_PATH.exists():
        payload = {
            "meta": {
                "version": REGISTRY_VERSION,
                "created_at": _now_ts(),
                "updated_at": _now_ts(),
                "source": "local_static_seed",
            },
            "tokens": STATIC_TOKENS,
            "protocols": STATIC_PROTOCOLS,
            "chains": STATIC_CHAINS,
        }
        _write_json(REGISTRY_PATH, payload)

    if not DISCOVERED_PATH.exists():
        payload = {
            "meta": {
                "created_at": _now_ts(),
                "updated_at": _now_ts(),
            },
            "entities": {},
        }
        _write_json(DISCOVERED_PATH, payload)


def load_asset_registry() -> Dict[str, Any]:
    initialize_asset_registry()
    registry = _read_json(
        REGISTRY_PATH,
        {
            "meta": {},
            "tokens": {},
            "protocols": {},
            "chains": {},
        },
    )
    registry.setdefault("meta", {})
    registry.setdefault("tokens", {})
    registry.setdefault("protocols", {})
    registry.setdefault("chains", {})
    return registry


def load_discovered_entities() -> Dict[str, Any]:
    initialize_asset_registry()
    discovered = _read_json(
        DISCOVERED_PATH,
        {
            "meta": {},
            "entities": {},
        },
    )
    discovered.setdefault("meta", {})
    discovered.setdefault("entities", {})
    return discovered


def save_discovered_entities(discovered: Dict[str, Any]) -> None:
    discovered = _safe_dict(discovered)
    discovered.setdefault("meta", {})
    discovered.setdefault("entities", {})
    discovered["meta"]["updated_at"] = _now_ts()
    _write_json(DISCOVERED_PATH, discovered)


def discover_entity(
    entity: str,
    *,
    entity_type: str | None = None,
    sector: str | None = None,
    chain: str | None = None,
    source: str | None = None,
) -> None:
    if not entity:
        return

    discovered = load_discovered_entities()
    entities = discovered["entities"]

    key = str(entity).upper().strip()
    record = _safe_dict(entities.get(key))

    if not record:
        record = {
            "entity": key,
            "entity_type": entity_type or "unknown",
            "sector": sector,
            "chain": chain,
            "first_seen": _now_ts(),
            "last_seen": _now_ts(),
            "sources": [source] if source else [],
            "observation_count": 1,
        }
    else:
        record["last_seen"] = _now_ts()
        record["observation_count"] = int(record.get("observation_count") or 0) + 1
        sources = _safe_list(record.get("sources"))
        if source and source not in sources:
            sources.append(source)
        record["sources"] = sources

        if entity_type and record.get("entity_type") in {None, "", "unknown"}:
            record["entity_type"] = entity_type
        if sector and not record.get("sector"):
            record["sector"] = sector
        if chain and not record.get("chain"):
            record["chain"] = chain

    entities[key] = record
    save_discovered_entities(discovered)


def get_registry_lookup() -> Dict[str, Dict[str, Any]]:
    registry = load_asset_registry()

    lookup: Dict[str, Dict[str, Any]] = {}

    for bucket in ("tokens", "protocols", "chains"):
        for key, value in _safe_dict(registry.get(bucket)).items():
            if not isinstance(value, dict):
                continue
            lookup[str(key).upper()] = value

            name = value.get("name")
            if name:
                lookup[str(name).upper()] = value

            symbol = value.get("symbol")
            if symbol:
                lookup[str(symbol).upper()] = value

    return lookup


def refresh_asset_registry_stub() -> Dict[str, Any]:
    registry = load_asset_registry()
    registry["meta"]["updated_at"] = _now_ts()
    registry["meta"]["source"] = "local_static_seed"
    _write_json(REGISTRY_PATH, registry)
    return registry


if __name__ == "__main__":
    initialize_asset_registry()
    refresh_asset_registry_stub()
    print(f"[ASSET REGISTRY] initialized → {REGISTRY_PATH}")
    print(f"[DISCOVERED ENTITIES] initialized → {DISCOVERED_PATH}")
