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
# MODULE: entity_mapper
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

from typing import Any, Dict

from pipeline.asset_registry_engine import (
    get_registry_lookup,
    discover_entity,
)


STATIC_ALIASES = {
    "BITCOIN": "BTC",
    "ETHEREUM": "ETH",
    "SOLANA": "SOL",
    "CARDANO": "ADA",
    "DOGECOIN": "DOGE",
    "UNISWAP": "UNI",
    "LIDO": "LDO",
    "SSV NETWORK": "SSV NETWORK",
    "WRAPPED BITCOIN": "WBTC",
    "WRAPPED ETHER": "WETH",
}


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def normalize_entity(entity: str | None) -> str | None:
    entity = _safe_str(entity)
    if not entity:
        return None

    key = entity.upper()

    if key in STATIC_ALIASES:
        return STATIC_ALIASES[key]

    lookup = get_registry_lookup()
    match = lookup.get(key)

    if match:
        symbol = match.get("symbol")
        name = match.get("name")
        if symbol:
            return str(symbol).upper()
        if name:
            return str(name).upper()

    return key


def detect_entity_type(entity: str | None) -> str | None:
    entity = _safe_str(entity)
    if not entity:
        return None

    key = entity.upper()
    lookup = get_registry_lookup()
    match = lookup.get(key)

    if match:
        return match.get("entity_type") or "unknown"

    if key.endswith(" NETWORK"):
        return "protocol"

    if key in {"BASE", "ARBITRUM", "ETHEREUM", "SOLANA", "BITCOIN"}:
        return "chain"

    return "unknown"


def enrich_entity_metadata(
    entity: str | None,
    *,
    source: str | None = None,
    sector: str | None = None,
    chain: str | None = None,
) -> Dict[str, Any]:
    normalized = normalize_entity(entity)
    entity_type = detect_entity_type(normalized)

    lookup = get_registry_lookup()
    record = lookup.get(str(normalized).upper(), {}) if normalized else {}

    enriched = {
        "entity": normalized,
        "entity_type": entity_type,
        "sector": sector or record.get("sector"),
        "chain": chain or record.get("chain"),
        "symbol": record.get("symbol"),
        "name": record.get("name"),
        "category": record.get("category"),
    }

    if normalized:
        discover_entity(
            normalized,
            entity_type=enriched["entity_type"],
            sector=enriched["sector"],
            chain=enriched["chain"],
            source=source,
        )

    return enriched
