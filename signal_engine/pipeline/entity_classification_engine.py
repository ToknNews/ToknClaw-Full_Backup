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
# MODULE: entity_classification_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
entity_classification_engine.py

ToknClaw Entity Classification Engine

Purpose
-------
Classify entities into canonical types and sectors using:
- asset registry
- discovered entities store
- snapshot entities
- cluster types
- signal context
- heuristic rules

Outputs
-------
snapshot["entity_classification"]
snapshot["entity_classification_summary"]
snapshot["entity_classification_alerts"]
snapshot["entity_classification_endpoints"]

Persistence
-----------
Updates /opt/toknclaw/data/assets/discovered_entities.json
for newly inferred entities and metadata improvements.

Design
------
• future-proof
• registry-first
• heuristic fallback
• confidence-based classification
• stable downstream schema
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Any


ASSET_DIR = Path("/opt/toknclaw/data/assets")
REGISTRY_PATH = ASSET_DIR / "asset_registry.json"
DISCOVERED_PATH = ASSET_DIR / "discovered_entities.json"


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _now_ts() -> int:
    return int(time.time())


def _unique_preserve(items: List[Any]) -> List[Any]:
    seen = set()
    out = []

    for item in items:
        key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


# -------------------------------------------------------
# Canonical keyword maps
# -------------------------------------------------------

STABLECOIN_SYMBOLS = {
    "USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "USDT0"
}

EXCHANGE_ENTITIES = {
    "BINANCE", "BYBIT", "BITGET", "HTX", "MEXC", "GATE",
    "DERIBIT", "GEMINI", "ROBINHOOD", "COINBASE", "COINBASE BRIDGE"
}

CHAIN_NAMES = {
    "BITCOIN": {"symbol": "BTC", "sector": "layer1"},
    "ETHEREUM": {"symbol": "ETH", "sector": "layer1"},
    "SOLANA": {"symbol": "SOL", "sector": "layer1"},
    "ARBITRUM": {"symbol": "ARB", "sector": "layer2"},
    "BASE": {"symbol": "BASE", "sector": "layer2"},
    "OPTIMISM": {"symbol": "OP", "sector": "layer2"},
    "AVALANCHE": {"symbol": "AVAX", "sector": "layer1"},
    "POLYGON": {"symbol": "MATIC", "sector": "layer2"},
}

WRAPPED_PATTERNS = {
    "WBTC": {"name": "Wrapped Bitcoin", "chain": "ethereum", "sector": "btc_beta"},
    "WETH": {"name": "Wrapped Ether", "chain": "ethereum", "sector": "eth_beta"},
}

PROTOCOL_KEYWORDS = {
    "LENDING": "lending",
    "STAKE": "staking",
    "STAKED": "staking",
    "BRIDGE": "bridge",
    "SWAP": "dex",
    "DEX": "dex",
    "VAULT": "yield",
    "YIELD": "yield",
    "PERP": "derivatives",
    "LIQUIDITY": "liquidity",
}

MEME_KEYWORDS = {
    "PEPE", "DOGE", "PENGU", "BONK", "FLOKI", "SHIB"
}


# -------------------------------------------------------
# Registry loading
# -------------------------------------------------------

def _load_registry() -> Dict[str, Any]:
    data = _load_json(REGISTRY_PATH)

    return {
        "tokens": _safe_dict(data.get("tokens")),
        "protocols": _safe_dict(data.get("protocols")),
        "chains": _safe_dict(data.get("chains")),
        "meta": _safe_dict(data.get("meta")),
    }


def _load_discovered() -> Dict[str, Any]:
    data = _load_json(DISCOVERED_PATH)

    if "entities" not in data:
        data = {
            "entities": {},
            "meta": {
                "created_at": _now_ts(),
                "updated_at": _now_ts(),
            }
        }

    return data


# -------------------------------------------------------
# Snapshot extraction
# -------------------------------------------------------

def _collect_snapshot_entities(snapshot: Dict[str, Any]) -> List[str]:
    entities = []

    for signal in _safe_list(snapshot.get("signals")):
        signal = _safe_dict(signal)
        entity = _safe_str(signal.get("entity")).upper()
        if entity:
            entities.append(entity)

    for cluster in _safe_list(snapshot.get("clusters")):
        cluster = _safe_dict(cluster)
        entity = _safe_str(cluster.get("entity")).upper()
        if entity:
            entities.append(entity)

    for corr in _safe_list(snapshot.get("narrative_correlations")):
        corr = _safe_dict(corr)
        for entity in _safe_list(corr.get("entities")):
            entity = _safe_str(entity).upper()
            if entity:
                entities.append(entity)

    for narrative in _safe_list(snapshot.get("narratives")):
        narrative = _safe_dict(narrative)
        for entity in _safe_list(narrative.get("entities")):
            entity = _safe_str(entity).upper()
            if entity:
                entities.append(entity)

    for entity in _safe_dict(snapshot.get("entity_intelligence")).keys():
        entity = _safe_str(entity).upper()
        if entity:
            entities.append(entity)

    return _unique_preserve(entities)


def _entity_context(snapshot: Dict[str, Any], entity: str) -> Dict[str, Any]:
    context = {
        "cluster_types": [],
        "signal_titles": [],
        "signal_summaries": [],
        "sources": [],
        "total_value_usd": 0.0,
    }

    for cluster in _safe_list(snapshot.get("clusters")):
        cluster = _safe_dict(cluster)
        c_entity = _safe_str(cluster.get("entity")).upper()
        if c_entity != entity:
            continue

        context["cluster_types"].append(_safe_str(cluster.get("cluster_type")))
        context["total_value_usd"] += _safe_float(cluster.get("total_value_usd"), 0.0)

    for signal in _safe_list(snapshot.get("signals")):
        signal = _safe_dict(signal)
        s_entity = _safe_str(signal.get("entity")).upper()
        if s_entity != entity:
            continue

        context["signal_titles"].append(_safe_str(signal.get("title")))
        context["signal_summaries"].append(_safe_str(signal.get("summary")))
        context["sources"].append(_safe_str(signal.get("source")))

    context["cluster_types"] = _unique_preserve(context["cluster_types"])
    context["signal_titles"] = _unique_preserve(context["signal_titles"])
    context["signal_summaries"] = _unique_preserve(context["signal_summaries"])
    context["sources"] = _unique_preserve(context["sources"])

    return context


# -------------------------------------------------------
# Classification logic
# -------------------------------------------------------

def _registry_lookup(entity: str, registry: Dict[str, Any]) -> Dict[str, Any] | None:
    tokens = _safe_dict(registry.get("tokens"))
    protocols = _safe_dict(registry.get("protocols"))
    chains = _safe_dict(registry.get("chains"))

    if entity in tokens:
        row = _safe_dict(tokens[entity])
        return {
            "entity": entity,
            "entity_type": row.get("entity_type") or "token",
            "sector": row.get("sector"),
            "chain": row.get("chain"),
            "symbol": row.get("symbol") or entity,
            "name": row.get("name") or entity,
            "category": row.get("category"),
            "aliases": [entity],
            "classification_source": "asset_registry",
            "classification_confidence": 0.98,
        }

    if entity in protocols:
        row = _safe_dict(protocols[entity])
        return {
            "entity": entity,
            "entity_type": row.get("entity_type") or "protocol",
            "sector": row.get("sector"),
            "chain": row.get("chain"),
            "symbol": row.get("symbol"),
            "name": row.get("name") or entity,
            "category": row.get("category"),
            "aliases": [entity],
            "classification_source": "asset_registry",
            "classification_confidence": 0.98,
        }

    if entity in chains:
        row = _safe_dict(chains[entity])
        return {
            "entity": entity,
            "entity_type": row.get("entity_type") or "chain",
            "sector": row.get("sector"),
            "chain": entity.lower(),
            "symbol": row.get("symbol") or entity,
            "name": row.get("name") or entity,
            "category": row.get("category"),
            "aliases": [entity],
            "classification_source": "asset_registry",
            "classification_confidence": 0.98,
        }

    return None


def _heuristic_classification(entity: str, context: Dict[str, Any]) -> Dict[str, Any]:
    title_blob = " ".join(context.get("signal_titles") or []).upper()
    summary_blob = " ".join(context.get("signal_summaries") or []).upper()
    blob = f"{entity} {title_blob} {summary_blob}"

    cluster_types = set(context.get("cluster_types") or [])
    total_value_usd = _safe_float(context.get("total_value_usd"), 0.0)

    entity_type = "unknown"
    sector = None
    chain = None
    symbol = entity
    name = entity.title()
    category = None
    confidence = 0.35
    source = "heuristic"

    if entity in STABLECOIN_SYMBOLS:
        entity_type = "stablecoin"
        sector = "stablecoin"
        category = "stablecoin"
        confidence = 0.94

    elif entity in EXCHANGE_ENTITIES:
        entity_type = "exchange"
        sector = "exchange"
        category = "cex"
        confidence = 0.92

    elif entity in CHAIN_NAMES:
        row = CHAIN_NAMES[entity]
        entity_type = "chain"
        sector = row.get("sector")
        symbol = row.get("symbol") or entity
        chain = entity.lower()
        confidence = 0.92

    elif entity in WRAPPED_PATTERNS:
        row = WRAPPED_PATTERNS[entity]
        entity_type = "wrapped_asset"
        sector = row.get("sector")
        name = row.get("name") or entity.title()
        chain = row.get("chain")
        confidence = 0.90

    elif "protocol_tvl" in cluster_types or "protocol_revenue" in cluster_types or "protocol_fees" in cluster_types:
        entity_type = "protocol"
        sector = "defi"
        confidence = 0.82

    elif "whale_activity" in cluster_types:
        entity_type = "token"
        sector = "large_cap" if total_value_usd > 500_000_000 else "onchain"
        confidence = 0.72

    elif "retail_narrative" in cluster_types:
        entity_type = "token"
        sector = "meme" if entity in MEME_KEYWORDS else "retail"
        confidence = 0.70

    elif any(word in entity for word in MEME_KEYWORDS):
        entity_type = "token"
        sector = "meme"
        confidence = 0.72

    elif any(word in blob for word in ["ETF", "ISSUER", "TREASURY", "CUSTODY", "PRIME"]):
        entity_type = "institutional"
        sector = "institutional"
        category = "issuer_or_custody"
        confidence = 0.74

    elif any(word in blob for word in ["BRIDGE"]):
        entity_type = "protocol"
        sector = "infrastructure"
        category = "bridge"
        confidence = 0.70

    elif any(word in blob for word in ["LENDING", "VAULT", "YIELD", "STAKE", "STAKED", "SWAP"]):
        entity_type = "protocol"
        sector = "defi"
        confidence = 0.72

    elif len(entity) <= 6 and entity.isupper():
        entity_type = "token"
        sector = "unclassified_token"
        confidence = 0.58

    for keyword, inferred_category in PROTOCOL_KEYWORDS.items():
        if keyword in blob:
            if entity_type in {"protocol", "unknown"}:
                entity_type = "protocol"
                category = inferred_category
                if sector is None:
                    sector = "defi" if inferred_category in {"lending", "staking", "yield", "dex"} else "infrastructure"
                confidence = max(confidence, 0.74)

    return {
        "entity": entity,
        "entity_type": entity_type,
        "sector": sector,
        "chain": chain,
        "symbol": symbol,
        "name": name,
        "category": category,
        "aliases": [entity],
        "classification_source": source,
        "classification_confidence": round(confidence, 2),
    }

def _derive_broadcast_fields(row: Dict[str, Any]) -> Dict[str, Any]:

    entity = str(row.get("entity") or "")
    etype = str(row.get("entity_type") or "")
    sector = str(row.get("sector") or "")
    confidence = float(row.get("classification_confidence") or 0.0)

    # ---------------------------------------------------
    # DOMAIN (BROADCAST SEGMENT)
    # ---------------------------------------------------

    if etype == "stablecoin":
        domain = "macro"

    elif etype == "chain":
        domain = "crypto_major"

    elif sector in {"defi", "yield", "lending"}:
        domain = "defi"

    elif sector == "meme":
        domain = "crypto_culture"

    elif etype == "exchange":
        domain = "flows"

    elif etype == "institutional":
        domain = "macro"

    elif etype == "protocol":
        domain = "defi"

    elif etype == "token":
        domain = "crypto_alt"

    else:
        domain = "general"

    # ---------------------------------------------------
    # INFRA FILTER
    # ---------------------------------------------------

    is_infrastructure = (
        entity.startswith("SOLANA_")
        or entity.startswith("RAYDIUM_")
        or entity.startswith("JUPITER_")
        or entity.startswith("PUMPFUN_")
        or entity.startswith("THEME_")
    )

    # ---------------------------------------------------
    # TRADEABILITY
    # ---------------------------------------------------

    is_tradeable = (
        etype in {"token", "stablecoin", "wrapped_asset"}
        and not is_infrastructure
    )

    # ---------------------------------------------------
    # BROADCAST PRIORITY
    # ---------------------------------------------------

    priority = 0.0

    if domain == "macro":
        priority += 2.5

    if domain == "crypto_major":
        priority += 2.2

    if domain == "defi":
        priority += 1.8

    if domain == "crypto_culture":
        priority += 1.6

    if confidence > 0.85:
        priority += 1.2

    # penalize garbage infra
    if is_infrastructure:
        priority -= 3.0

    # ---------------------------------------------------
    # NARRATIVE WEIGHT
    # ---------------------------------------------------

    narrative_weight = priority * (1.0 + confidence)

    return {
        "domain": domain,
        "is_tradeable": is_tradeable,
        "is_infrastructure": is_infrastructure,
        "broadcast_priority": round(priority, 3),
        "narrative_weight": round(narrative_weight, 3),
    }

def _merge_discovered(existing: Dict[str, Any], fresh: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    existing = _safe_dict(existing)
    fresh = _safe_dict(fresh)

    out = dict(existing)

    for field in [
        "entity", "entity_type", "sector", "chain", "symbol", "name",
        "category", "aliases", "classification_source", "classification_confidence"
    ]:
        if fresh.get(field) not in [None, "", []]:
            out[field] = fresh.get(field)

    out["aliases"] = _unique_preserve(_safe_list(out.get("aliases")) + _safe_list(fresh.get("aliases")))
    out["sources"] = _unique_preserve(_safe_list(out.get("sources")) + _safe_list(context.get("sources")))
    out["cluster_types"] = _unique_preserve(_safe_list(out.get("cluster_types")) + _safe_list(context.get("cluster_types")))
    out["last_seen"] = _now_ts()

    if not out.get("first_seen"):
        out["first_seen"] = _now_ts()

    if "observation_count" not in out:
        out["observation_count"] = 0
    out["observation_count"] += 1

    return out


# -------------------------------------------------------
# Alerts / summary / endpoints
# -------------------------------------------------------

def _build_alerts(rows: List[Dict[str, Any]], previous_discovered: Dict[str, Any]) -> List[Dict[str, Any]]:
    alerts = []

    prev_entities = set(_safe_dict(previous_discovered.get("entities")).keys())

    for row in rows:
        entity = row["entity"]
        confidence = _safe_float(row.get("classification_confidence"), 0.0)
        etype = str(row.get("entity_type") or "")

        if entity not in prev_entities and confidence >= 0.70:
            alerts.append({
                "type": "new_entity_classified",
                "severity": "medium",
                "entity": entity,
                "title": f"{entity} classified as {etype}",
            })

        if etype == "unknown":
            alerts.append({
                "type": "unknown_entity_needs_review",
                "severity": "low",
                "entity": entity,
                "title": f"{entity} remains unclassified",
            })

    return alerts[:50]


def _build_summary(rows: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    type_counts: Dict[str, int] = {}
    sector_counts: Dict[str, int] = {}

    for row in rows:
        etype = str(row.get("entity_type") or "unknown")
        sector = str(row.get("sector") or "unknown")

        type_counts[etype] = type_counts.get(etype, 0) + 1
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    return {
        "entity_count": len(rows),
        "unknown_count": type_counts.get("unknown", 0),
        "type_counts": type_counts,
        "sector_counts": sector_counts,
        "alert_count": len(alerts),
    }


def _endpoint_manifest() -> Dict[str, str]:
    return {
        "entity_classification": "/api/toknclaw/entities/classification",
        "entity_classification_summary": "/api/toknclaw/entities/classification/summary",
        "entity_classification_alerts": "/api/toknclaw/entities/classification/alerts",
    }


# -------------------------------------------------------
# Main engine
# -------------------------------------------------------

def build_entity_classification(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    registry = _load_registry()
    discovered_before = _load_discovered()
    discovered_after = _load_discovered()

    entities = _collect_snapshot_entities(snapshot)
    rows = []

    for entity in entities:
        context = _entity_context(snapshot, entity)

        row = _registry_lookup(entity, registry)
        if row is None:
            row = _heuristic_classification(entity, context)

        discovered_existing = _safe_dict(_safe_dict(discovered_after.get("entities")).get(entity))
        merged = _merge_discovered(discovered_existing, row, context)

        discovered_after.setdefault("entities", {})
        discovered_after["entities"][entity] = merged

        broadcast_fields = _derive_broadcast_fields(merged)

        rows.append({
            "entity": entity,
            "entity_type": merged.get("entity_type"),
            "sector": merged.get("sector"),
            "chain": merged.get("chain"),
            "symbol": merged.get("symbol"),
            "name": merged.get("name"),
            "category": merged.get("category"),
            "aliases": merged.get("aliases") or [],
            "classification_source": merged.get("classification_source"),
            "classification_confidence": round(_safe_float(merged.get("classification_confidence"), 0.0), 2),
            "sources": merged.get("sources") or [],
            "cluster_types": merged.get("cluster_types") or [],
            "observation_count": int(_safe_float(merged.get("observation_count"), 0)),
            "first_seen": merged.get("first_seen"),
            "last_seen": merged.get("last_seen"),

            # ✅ NEW FIELDS
            "domain": broadcast_fields["domain"],
            "is_tradeable": broadcast_fields["is_tradeable"],
            "is_infrastructure": broadcast_fields["is_infrastructure"],
            "broadcast_priority": broadcast_fields["broadcast_priority"],
            "narrative_weight": broadcast_fields["narrative_weight"],
        })

    rows.sort(
        key=lambda x: (
            _safe_float(x.get("classification_confidence"), 0.0),
            x.get("entity_type") != "unknown",
            x.get("entity", ""),
        ),
        reverse=True,
    )

    discovered_after["meta"] = {
        "created_at": _safe_dict(discovered_before.get("meta")).get("created_at") or _now_ts(),
        "updated_at": _now_ts(),
    }
    _write_json(DISCOVERED_PATH, discovered_after)

    alerts = _build_alerts(rows, discovered_before)
    summary = _build_summary(rows, alerts)

    return {
        "entity_classification": rows,
        "entity_classification_summary": summary,
        "entity_classification_alerts": alerts,
        "entity_classification_endpoints": _endpoint_manifest(),
    }
