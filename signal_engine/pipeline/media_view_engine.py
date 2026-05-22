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
# MODULE: media_view_engine
# PURPOSE: Build the final ToknClaw media_view.json output by transforming the
#          unified snapshot into a structured, multi-domain, broadcast-ready
#          intelligence layer for ToknNews, UI surfaces, newsletters, alerts,
#          and future downstream products.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• read the central snapshot without mutating it
• route stories into media-ready domain segments
• preserve the ToknNews card contract while adding safe extensions
• surface richer market intelligence without writing dialogue
• support broadcast, website, newsletter, alerts, and future verticals
• remain additive and OpenClaw-ready
• preserve the unified-brain architecture

Primary Input
-------------
/opt/toknclaw/data/snapshots/latest_snapshot.json

Primary Output
--------------
/opt/toknclaw/data/views/media_view.json

Design Notes
------------
• no direct RPC calls
• no collector execution
• pure derived view
• multi-domain by default
• future-safe for BTC, ETH, macro, regulation, culture, defi, flows, and news
• preserves existing ToknNews ingest contract on card fields
• allows additive metadata for richer downstream use
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot.json")
OUTPUT_PATH = Path("/opt/toknclaw/data/views/media_view.json")
TMP_OUTPUT_PATH = Path("/opt/toknclaw/data/views/media_view.tmp")


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

MAJOR_TICKERS = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "LINK", "AVAX",
    "ARB", "OP", "INJ", "PYTH", "JUP", "RNDR"
}

ENTITY_REGISTRY_PATH = Path("/opt/toknclaw/config/entity_registry.json")

def load_entity_registry() -> Dict[str, Any]:
    if ENTITY_REGISTRY_PATH.exists():
        try:
            with open(ENTITY_REGISTRY_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

ENTITY_REGISTRY = load_entity_registry()

def is_valid_entity(e: str) -> bool:
    e = clean_text(e)

    if e.upper() in MAJOR_TICKERS:
        return True

    if len(e) <= 6:
        return True

    if "pump" in e.lower():
        return True

    return False

def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []

def build_entity_map(snapshot: Dict[str, Any]) -> Dict[str, str]:
    return {}

def unique_preserve(items: List[Any]) -> List[Any]:
    seen = set()
    out: List[Any] = []

    for item in items:
        key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out

#def build_entity_map(snapshot):
#    entity_map = {}

#    signals = snapshot.get("signals", [])

#    for row in signals:
#        entity = clean_text(row.get("entity"))
#        title = clean_text(row.get("title"))
#        summary = clean_text(row.get("summary"))

        # crude extraction of ticker from text
#        for word in (title + " " + summary).split():
#            word = word.upper().strip(",.()")
#            if len(word) <= 6 and word.isalpha():
#                entity_map[entity] = word

#    return entity_map

def object_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    out: List[Dict[str, Any]] = []

    for row in rows:
        if isinstance(row, dict):
            out.append(row)

    return out


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def load_snapshot() -> Dict[str, Any]:
    data = read_json_file(SNAPSHOT_PATH, {})
    return data if isinstance(data, dict) else {}


def top_n(rows: List[Any], n: int) -> List[Any]:
    return rows[:max(0, n)]


def maybe_round(value: Any, digits: int = 4) -> Optional[float]:
    try:
        return round(float(value), digits)
    except Exception:
        return None


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def read_path(obj: Dict[str, Any], path: List[str]) -> Any:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def compact_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            nested = compact_dict(v)
            if nested:
                out[k] = nested
            continue
        if isinstance(v, list):
            cleaned = [x for x in v if x is not None and x != ""]
            if cleaned:
                out[k] = cleaned
            continue
        out[k] = v
    return out


def is_contract_like(entity: str) -> bool:
    e = clean_text(entity)
    if not e:
        return False
    if len(e) >= 20 and re.fullmatch(r"[A-Za-z0-9]+", e):
        return True
    return False


def looks_like_short_symbol(entity: str) -> bool:
    e = clean_text(entity)
    return bool(e) and len(e) <= 8 and re.fullmatch(r"[A-Za-z0-9_\-]+", e) is not None


def format_entity(entity: str, entity_map: Optional[Dict[str, str]] = None) -> str:
    e = clean_text(entity)

    if e.upper() in MAJOR_TICKERS:
        return e.upper()

    if len(e) <= 6:
        return e.upper()

    if "pump" in e.lower():
        return e[:4].upper() + "...PUMP"

    if len(e) > 12:
        return e[:6] + "..." + e[-4:]

    return e

def entity_priority(entity: str) -> int:
    e = clean_text(entity).upper()

    if e in MAJOR_TICKERS:
        return 4

    if looks_like_short_symbol(entity) and not is_contract_like(entity):
        return 3

    if "pump" in clean_text(entity).lower():
        return 2

    return 1


def summarize_entities(entities: List[str], fallback: str) -> str:
    clean_entities = [
        format_entity(x)
        for x in entities
        if clean_text(x)
    ]

    clean_entities = unique_preserve(clean_entities)

    if not clean_entities:
        return fallback
    if len(clean_entities) == 1:
        return clean_entities[0]
    if len(clean_entities) == 2:
        return f"{clean_entities[0]} and {clean_entities[1]}"
    return f"{clean_entities[0]}, {clean_entities[1]}, and {clean_entities[2]}"

def normalized_reason_list(row: Dict[str, Any]) -> List[str]:
    return [clean_text(x).lower() for x in safe_list(row.get("reasons")) if clean_text(x)]


def score_trade_row(row: Dict[str, Any]) -> float:
    confidence = safe_float(row.get("confidence", 0.0))
    signal_count = safe_int(row.get("signal_count", 0))
    direction = clean_text(row.get("direction")).lower()

    base = confidence * 10.0 + signal_count * 0.35

    if direction == "strong_bullish":
        base += 2.0
    elif direction == "bullish":
        base += 1.0
    elif direction == "strong_bearish":
        base += 2.0
    elif direction == "bearish":
        base += 1.0

    return round(base, 4)

def resolve_entity(entity: str, mode: str = "symbol") -> str:
    e = clean_text(entity)

    # ---------------------------------------------------
    # 1. DIRECT MATCH (symbol keys like "arb")
    # ---------------------------------------------------
    if e in ENTITY_REGISTRY:
        entry = ENTITY_REGISTRY[e]
        return entry["name"] if mode == "name" else entry["symbol"]

    # ---------------------------------------------------
    # 2. CONTRACT MATCH (sol:mint format)
    # ---------------------------------------------------
    key = f"sol:{e}"
    if key in ENTITY_REGISTRY:
        entry = ENTITY_REGISTRY[key]
        return entry["name"] if mode == "name" else entry["symbol"]

    # ---------------------------------------------------
    # 3. MAJORS
    # ---------------------------------------------------
    if e.upper() in MAJOR_TICKERS:
        return e.upper()

    # ---------------------------------------------------
    # 4. SHORT SYMBOLS
    # ---------------------------------------------------
    if len(e) <= 6 and e.isalpha():
        return e.upper()

    # ---------------------------------------------------
    # 5. PUMP TOKENS
    # ---------------------------------------------------
    if "pump" in e.lower():
        return e[:4].upper() + "...PUMP"

    # ---------------------------------------------------
    # 6. FALLBACK
    # ---------------------------------------------------
    if len(e) > 12:
        return e[:6] + "..." + e[-4:]

    return e

def top_dict_items(d: Dict[str, int], n: int) -> List[Dict[str, Any]]:
    items = sorted(d.items(), key=lambda x: x[1], reverse=True)
    return [{"key": k, "count": v} for k, v in items[:n]]


def signal_type_counts(signals: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for row in signals:
        signal_type = clean_text(row.get("signal_type"))
        if not signal_type:
            continue
        counts[signal_type] = counts.get(signal_type, 0) + 1

    return counts


def source_counts(signals: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for row in signals:
        source = clean_text(row.get("source"))
        if not source:
            continue
        counts[source] = counts.get(source, 0) + 1

    return counts


def entity_counts(signals: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for row in signals:
        entity = clean_text(row.get("entity"))
        if not entity:
            continue
        counts[entity] = counts.get(entity, 0) + 1

    return counts


def index_signals_by_entity(signals: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    for row in signals:
        # 🔥 HARD FILTER
        if not isinstance(row, dict):
            continue

        entity = clean_text(row.get("entity"))
        if not entity:
            continue

        out.setdefault(entity, []).append(row)

    return out


# ---------------------------------------------------
# DOMAIN CLASSIFICATION
# ---------------------------------------------------

def classify_signal_domain(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return "general"

    signal_type = clean_text(row.get("signal_type"))
    entity = clean_text(row.get("entity"))
    title = clean_text(row.get("title"))
    summary = clean_text(row.get("summary"))

    text = f"{signal_type} {entity} {title} {summary}".lower()

    if entity.startswith("SOLANA_") or entity.endswith("_ACTIVITY"):
        return "infra"

    if signal_type.startswith("macro_"):
        return "macro"

    if signal_type in {"news", "news_theme", "macro_news"}:
        return "news"

    if any(x in text for x in ["sec", "etf", "regulat", "policy"]):
        return "regulation"

    if any(x in text for x in ["btc", "bitcoin"]):
        return "crypto_major"

    if any(x in text for x in ["eth", "ethereum"]):
        return "crypto_major"

    if signal_type.startswith("protocol_") or any(x in text for x in ["tvl", "yield", "lending", "dex"]):
        return "defi"

    if signal_type in {"large_token_transfer"}:
        return "flows"

    if signal_type.startswith("solana_"):
        if any(x in signal_type for x in ["pumpfun", "memecoin", "funny_name"]):
            return "crypto_culture"
        return "crypto_alt"

    return "general"


def classify_entity_domain(entity: str, rows: List[Dict[str, Any]]) -> str:
    entity_lower = clean_text(entity).lower()

    # ---------------------------------------------------
    # HARD RULES (FAST PATH)
    # ---------------------------------------------------
    if entity_lower in {"btc", "bitcoin", "eth", "ethereum"}:
        return "crypto_major"

    if entity_lower.startswith("solana_") or entity_lower.endswith("pump"):
        return "crypto_culture"

    if entity_lower in {"arb", "op", "inj", "link", "avax", "bnb", "xrp"}:
        return "crypto_alt"

    # ---------------------------------------------------
    # WEIGHTED DOMAIN SCORING
    # ---------------------------------------------------
    domain_scores: Dict[str, float] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        domain = classify_signal_domain(row)

        confidence = safe_float(row.get("confidence", 0.0))
        sentiment = abs(safe_float(row.get("sentiment_score", 0.0)))

        # base weight
        weight = 1.0 + confidence * 2 + sentiment

        # ---------------------------------------------------
        # BOOST IMPORTANT SIGNAL TYPES
        # ---------------------------------------------------
        signal_type = clean_text(row.get("signal_type"))

        if signal_type.startswith("macro_"):
            weight += 2.5

        if signal_type.startswith("protocol_"):
            weight += 1.5

        if signal_type in {"large_token_transfer"}:
            weight += 1.5

        if signal_type.startswith("solana_"):
            weight += 0.5

        # ---------------------------------------------------
        # DIRECTIONAL BOOST (helps narrative relevance)
        # ---------------------------------------------------
        direction = clean_text(row.get("direction")).lower()

        if direction in {"strong_bullish", "strong_bearish"}:
            weight += 1.5
        elif direction in {"bullish", "bearish"}:
            weight += 0.75

        domain_scores[domain] = domain_scores.get(domain, 0.0) + weight

    # ---------------------------------------------------
    # FALLBACK
    # ---------------------------------------------------
    if not domain_scores:
        return "general"

    # ---------------------------------------------------
    # RETURN HIGHEST WEIGHTED DOMAIN
    # ---------------------------------------------------
    return sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)[0][0]

# ---------------------------------------------------
# SNAPSHOT PROBES
# ---------------------------------------------------

def infer_chain_for_entity(entity: str, entity_rows: List[Dict[str, Any]]) -> str:
    for row in entity_rows:
        if not isinstance(row, dict):   # 🔥 ADD THIS
            continue
        for key in ["chain", "blockchain", "network"]:
            value = clean_text(row.get(key))
            if value:
                return value.lower()

    e = clean_text(entity).lower()
    if e.endswith("pump") or e.startswith("solana_"):
        return "solana"

    if e in {"btc", "bitcoin"}:
        return "bitcoin"

    if e in {"eth", "ethereum", "arb", "op", "inj", "link"}:
        return "ethereum"

    return "unknown"


def extract_entity_metrics(row: Dict[str, Any], entity_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    price_usd = first_non_null(
        row.get("price_usd"),
        read_path(row, ["metrics", "price_usd"]),
    )

    perf_24h = first_non_null(
        row.get("change_24h_pct"),
        row.get("pct_change_24h"),
        row.get("performance_24h_pct"),
        read_path(row, ["metrics", "change_24h_pct"]),
    )

    perf_1h = first_non_null(
        row.get("change_1h_pct"),
        row.get("pct_change_1h"),
        read_path(row, ["metrics", "change_1h_pct"]),
    )

    funding_rate = first_non_null(
        row.get("funding_rate"),
        read_path(row, ["metrics", "funding_rate"]),
    )

    open_interest_usd = first_non_null(
        row.get("open_interest_usd"),
        row.get("oi_usd"),
        read_path(row, ["metrics", "open_interest_usd"]),
    )

    oi_change_pct = first_non_null(
        row.get("oi_change_pct"),
        row.get("open_interest_change_pct"),
        read_path(row, ["metrics", "oi_change_pct"]),
    )

    volume_24h = first_non_null(
        row.get("volume_24h"),
        read_path(row, ["metrics", "volume_24h"]),
    )

    liquidity_usd = first_non_null(
        row.get("liquidity_usd"),
        read_path(row, ["metrics", "liquidity_usd"]),
    )

    # Probe raw signals if row-level metrics are missing
    if price_usd is None or perf_24h is None or perf_1h is None:
        for signal in entity_rows:
            price_usd = first_non_null(
                price_usd,
                signal.get("price_usd"),
                read_path(signal, ["metrics", "price_usd"]),
            )
            perf_24h = first_non_null(
                perf_24h,
                signal.get("change_24h_pct"),
                signal.get("pct_change_24h"),
                read_path(signal, ["metrics", "change_24h_pct"]),
            )
            perf_1h = first_non_null(
                perf_1h,
                signal.get("change_1h_pct"),
                signal.get("pct_change_1h"),
                read_path(signal, ["metrics", "change_1h_pct"]),
            )
            funding_rate = first_non_null(
                funding_rate,
                signal.get("funding_rate"),
                read_path(signal, ["metrics", "funding_rate"]),
            )
            open_interest_usd = first_non_null(
                open_interest_usd,
                signal.get("open_interest_usd"),
                signal.get("oi_usd"),
                read_path(signal, ["metrics", "open_interest_usd"]),
            )
            oi_change_pct = first_non_null(
                oi_change_pct,
                signal.get("oi_change_pct"),
                signal.get("open_interest_change_pct"),
                read_path(signal, ["metrics", "oi_change_pct"]),
            )
            volume_24h = first_non_null(
                volume_24h,
                signal.get("volume_24h"),
                read_path(signal, ["metrics", "volume_24h"]),
            )
            liquidity_usd = first_non_null(
                liquidity_usd,
                signal.get("liquidity_usd"),
                read_path(signal, ["metrics", "liquidity_usd"]),
            )

    return compact_dict({
        "price_usd": maybe_round(price_usd, 8),
        "change_1h_pct": maybe_round(perf_1h, 4),
        "change_24h_pct": maybe_round(perf_24h, 4),
        "funding_rate": maybe_round(funding_rate, 8),
        "open_interest_usd": maybe_round(open_interest_usd, 2),
        "oi_change_pct": maybe_round(oi_change_pct, 4),
        "volume_24h": maybe_round(volume_24h, 2),
        "liquidity_usd": maybe_round(liquidity_usd, 2),
    })

def compute_signal_diagnostics(trade_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(trade_rows)
    if total == 0:
        return {}

    counts = {
        "bullish": 0,
        "bearish": 0,
        "unwind": 0,
        "build": 0,
        "trend_up": 0,
        "trend_down": 0,
        "high_oi": 0,
    }

    for row in trade_rows:
        direction = clean_text(row.get("direction")).lower()
        reasons = [clean_text(x).lower() for x in row.get("reasons", [])]

        if direction in {"bullish", "strong_bullish"}:
            counts["bullish"] += 1
        if direction in {"bearish", "strong_bearish"}:
            counts["bearish"] += 1

        if any(x in reasons for x in ["long_unwind", "oi_unwind_accel"]):
            counts["unwind"] += 1

        if any(x in reasons for x in ["oi_build_accel", "short_unwind"]):
            counts["build"] += 1

        if "trend_bull" in reasons:
            counts["trend_up"] += 1

        if "trend_bear" in reasons:
            counts["trend_down"] += 1

        if "high_oi" in reasons:
            counts["high_oi"] += 1

    pct = lambda x: round(x / total, 3)

    print("DEBUG SAMPLE REASONS:", trade_rows[:3])

    return {
        "total_assets": total,
        "bullish_pct": pct(counts["bullish"]),
        "bearish_pct": pct(counts["bearish"]),
        "unwind_pct": pct(counts["unwind"]),
        "build_pct": pct(counts["build"]),
        "trend_down_pct": pct(counts["trend_down"]),
        "trend_up_pct": pct(counts["trend_up"]),
        "high_oi_pct": pct(counts["high_oi"]),
    }

def build_clusters(trade_rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    clusters = {
        "bearish": [],
        "bullish": [],
        "unwind": [],
        "build": [],
        "crowded": [],
        "trend_down": [],
        "trend_up": [],
    }

    for row in trade_rows:
        direction = clean_text(row.get("direction")).lower()
        reasons = normalized_reason_list(row)

        if direction in {"bearish", "strong_bearish"}:
            clusters["bearish"].append(row)

        if direction in {"bullish", "strong_bullish"}:
            clusters["bullish"].append(row)

        if any(x in reasons for x in ["long_unwind", "oi_unwind_accel", "oi_unwind_base"]):
            clusters["unwind"].append(row)

        if any(x in reasons for x in ["oi_build_accel", "oi_accel_base", "short_unwind"]):
            clusters["build"].append(row)

        if any(x in reasons for x in ["high_oi", "oi_divergence", "funding_divergence", "funding_negative"]):
            clusters["crowded"].append(row)

        if "trend_bear" in reasons:
            clusters["trend_down"].append(row)

        if "trend_bull" in reasons:
            clusters["trend_up"].append(row)

    return clusters


# ---------------------------------------------------
# OVERVIEW
# ---------------------------------------------------

def build_overview(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    metrics = safe_dict(snapshot.get("metrics"))
    signal_types = safe_dict(metrics.get("signal_types"))
    trade_rows = object_rows(safe_dict(snapshot.get("trade_signals")).get("rows"))

    bullish_count = len([
        row for row in trade_rows
        if clean_text(row.get("direction")).lower() in {"bullish", "strong_bullish"}
    ])
    bearish_count = len([
        row for row in trade_rows
        if clean_text(row.get("direction")).lower() in {"bearish", "strong_bearish"}
    ])

    return {
        "updated_at": utc_now_iso(),
        "snapshot_timestamp": snapshot.get("timestamp"),
        "total_signals": safe_int(metrics.get("total_signals", 0)),
        "unique_entities": safe_int(metrics.get("unique_entities", 0)),
        "source_count": len(safe_dict(metrics.get("sources"))),
        "headline_samples": top_n(metrics.get("headline_samples", []), 12),
        "trade_signal_count": len(trade_rows),
        "market_breadth": {
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
        },
        "domain_hints": {
            "macro_signal_count": sum(v for k, v in signal_types.items() if clean_text(k).startswith("macro_")),
            "news_signal_count": safe_int(signal_types.get("news", 0)) + safe_int(signal_types.get("news_theme", 0)),
            "defi_signal_count": sum(v for k, v in signal_types.items() if clean_text(k).startswith("protocol_")),
            "solana_signal_count": sum(v for k, v in signal_types.items() if clean_text(k).startswith("solana_")),
        },
    }


# ---------------------------------------------------
# STORY CANDIDATES
# ---------------------------------------------------

def score_story_signal(row: Dict[str, Any]) -> float:
    signal_type = clean_text(row.get("signal_type"))
    domain = classify_signal_domain(row)

    confidence = safe_float(row.get("confidence", 0.0))
    sentiment = abs(safe_float(row.get("sentiment_score", 0.0)))

    base = confidence * 8 + sentiment * 2

    domain_boosts = {
        "macro": 8.0,
        "news": 7.0,
        "regulation": 7.0,
        "crypto_major": 6.0,
        "defi": 5.5,
        "crypto_alt": 3.0,
        "crypto_culture": 1.2,
        "flows": 4.0,
    }

    base += domain_boosts.get(domain, 0.0)

    if signal_type == "macro_news":
        base += 5
    if signal_type == "solana_memecoin_of_the_day":
        base += 3
    if signal_type == "solana_alpha_entry_signal":
        base += 2
    if signal_type == "large_token_transfer":
        base += 2

    return round(base, 4)


def build_top_stories(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    signals = object_rows(snapshot.get("signals", []))

    buckets = {
        "macro": [],
        "news": [],
        "regulation": [],
        "crypto_major": [],
        "defi": [],
        "crypto_alt": [],
        "crypto_culture": [],
        "flows": [],
    }

    for row in signals:
        domain = classify_signal_domain(row)

        if domain == "infra":
            continue

        enriched = {
            "domain": domain,
            "signal_type": clean_text(row.get("signal_type")),
            "entity": clean_text(row.get("entity")),
            "title": clean_text(row.get("title")),
            "summary": clean_text(row.get("summary")),
            "confidence": safe_float(row.get("confidence", 0.0)),
            "sentiment_score": safe_float(row.get("sentiment_score", 0.0)),
            "raw_url": row.get("raw_url"),
            "story_score": score_story_signal(row),
        }

        buckets.setdefault(domain, []).append(enriched)

    for key in buckets:
        buckets[key].sort(key=lambda x: x["story_score"], reverse=True)

    limits = {
        "macro": 6,
        "news": 6,
        "regulation": 4,
        "crypto_major": 6,
        "defi": 5,
        "crypto_alt": 5,
        "crypto_culture": 6,
        "flows": 4,
    }

    final: List[Dict[str, Any]] = []

    for domain, limit in limits.items():
        final += buckets.get(domain, [])[:limit]

    if len(final) < 40:
        remaining: List[Dict[str, Any]] = []
        for key in buckets:
            remaining += buckets[key][limits.get(key, 0):]

        remaining.sort(key=lambda x: x["story_score"], reverse=True)
        final += remaining[: (40 - len(final))]

    return final[:40]


# ---------------------------------------------------
# SEGMENTS
# ---------------------------------------------------

def build_segment_from_domain(
    name: str,
    rows: List[Dict[str, Any]],
    by_entity: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:

    entities_seen: List[str] = []
    cards: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        entity = clean_text(row.get("entity"))
        entity_rows = by_entity.get(entity, [])

        # 🔥 HARDEN entity_rows (prevents future crashes)
        entity_rows = [x for x in entity_rows if isinstance(x, dict)]

        cards.append(
            {
                "entity": entity,
                "title": clean_text(row.get("title")),
                "summary": clean_text(row.get("summary")),
                "signal_type": clean_text(row.get("signal_type")),
                "confidence": safe_float(row.get("confidence", 0.0)),
                "sentiment_score": safe_float(row.get("sentiment_score", 0.0)),
                "story_score": safe_float(row.get("story_score", 0.0)),
                "entity_domain": classify_entity_domain(entity, entity_rows),

                "supporting_signal_types": sorted(
                    set(
                        clean_text(x.get("signal_type"))
                        for x in entity_rows
                        if clean_text(x.get("signal_type"))
                    )
                )[:15],

                "raw_url": row.get("raw_url"),

                "meta": {
                    "entity_display": resolve_entity(entity),
                    "chain": infer_chain_for_entity(entity, entity_rows),
                },
            }
        )

        if entity and entity not in entities_seen:
            entities_seen.append(entity)

    return {
        "segment": name,
        "story_count": len(rows),
        "entities": entities_seen[:20],
        "cards": cards[:20],
        "entity_displays": [resolve_entity(x) for x in entities_seen[:20]],
    }

def build_market_segment(snapshot: Dict[str, Any], by_entity: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    trade_rows = object_rows(safe_dict(snapshot.get("trade_signals")).get("rows"))
    signals = object_rows(snapshot.get("signals", []))
    scored_trade_rows = sorted(trade_rows, key=score_trade_row, reverse=True)
    signal_map = index_signals_by_entity(signals)
    clusters = build_clusters(scored_trade_rows)
    diagnostics = compute_signal_diagnostics(scored_trade_rows)

    chain_scores = {}

    for row in scored_trade_rows:
        entity = clean_text(row.get("entity"))
        if not entity:
            continue

        entity_rows = signal_map.get(entity, [])
        entity_rows = [x for x in entity_rows if isinstance(x, dict)]

        chain = infer_chain_for_entity(entity, entity_rows)

        if not chain or chain == "unknown":
            continue

        confidence = safe_float(row.get("confidence", 0.0))
        signal_count = safe_int(row.get("signal_count", 0))

        weight = confidence * 2 + (signal_count * 0.1)
        chain_scores[chain] = chain_scores.get(chain, 0.0) + weight

    total_score = sum(chain_scores.values())

    chain_distribution = {
        k: round(v / total_score, 3)
        for k, v in chain_scores.items()
    } if total_score > 0 else {}

    sorted_chains = sorted(
        chain_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    dominant_chain = sorted_chains[0][0] if sorted_chains else None
    dominance_pct = (
        round(sorted_chains[0][1] / total_score, 3)
        if total_score > 0 and sorted_chains else 0
    )

    chain_context = {
        "dominant_chain": dominant_chain,
        "dominance_pct": dominance_pct,
        "distribution": chain_distribution,
        "top_chains": sorted_chains[:5],
    }

    def resolve_entity(entity: str) -> str:
        return format_entity(entity)

    def select_entities_resolved(rows: List[Dict[str, Any]], n: int = 3) -> List[str]:
        ranked = sorted(
            [r for r in rows if isinstance(r, dict)],
            key=lambda r: (
                entity_priority(clean_text(r.get("entity"))),
                safe_float(r.get("confidence", 0.0)),
            ),
            reverse=True,
        )

        picked: List[str] = []

        for row in ranked:
            entity = clean_text(row.get("entity"))

            if not entity:
                continue

            # 🔥 FIX: FILTER FIRST
            if not is_valid_entity(entity):
                continue

            if entity not in picked:
                picked.append(entity)

            if len(picked) >= n:
                break

        return [resolve_entity(x) for x in picked]

    def trade_row_support(row: Dict[str, Any]) -> Dict[str, Any]:
        entity = clean_text(row.get("entity"))
        reasons = normalized_reason_list(row)
        reason_set = set(reasons)

        raw_entity_rows = signal_map.get(entity, [])
        entity_rows = [x for x in raw_entity_rows if isinstance(x, dict)]

        raw_signal_types = unique_preserve(
            [
                clean_text(x.get("signal_type"))
                for x in entity_rows
                if clean_text(x.get("signal_type"))
            ]
        )

        flow = "mixed"
        if any(x in reason_set for x in ["oi_build_accel", "oi_accel_base", "short_unwind"]):
            flow = "build"
        elif any(x in reason_set for x in ["oi_unwind_accel", "oi_unwind_base", "long_unwind"]):
            flow = "unwind"

        structure = "unknown"
        if any(x in reason_set for x in ["below_200_sma", "lost_200_sma"]):
            structure = "below_200_sma"
        elif any(x in reason_set for x in ["above_200_sma", "reclaimed_200_sma"]):
            structure = "above_200_sma"
        else:
            joined = " ".join(raw_signal_types).lower()
            if "trend_bear" in joined:
                structure = "weak_structure"
            elif "trend_bull" in joined:
                structure = "strong_structure"

        momentum = "mixed"
        if any(x in reason_set for x in ["trend_bull", "oi_build_accel", "oi_accel_base"]):
            momentum = "up"
        elif any(x in reason_set for x in ["trend_bear", "oi_unwind_accel", "oi_unwind_base"]):
            momentum = "down"

        crowding_flags: List[str] = []
        if "high_oi" in reason_set:
            crowding_flags.append("high_oi")
        if any(x in reason_set for x in ["oi_divergence", "funding_divergence"]):
            crowding_flags.append("divergence")
        if "funding_negative" in reason_set:
            crowding_flags.append("negative_funding")

        entity_metrics = extract_entity_metrics(row, entity_rows)

        return {
            "entity": entity,
            "entity_display": resolve_entity(entity),
            "reasons": reasons,
            "reason_set": reason_set,
            "raw_signal_types": raw_signal_types,
            "flow": flow,
            "structure": structure,
            "momentum": momentum,
            "crowding_flags": crowding_flags,
            "metrics": entity_metrics,
            "chain": infer_chain_for_entity(entity, entity_rows),
            "entity_domain": classify_entity_domain(entity, entity_rows),
        }

    def build_card(
        *,
        entity: str,
        title: str,
        summary: str,
        signal_type: str,
        confidence: float,
        sentiment_score: float,
        story_score: float,
        entity_domain: str,
        supporting_signal_types: List[str],
        intelligence: Dict[str, Any],
        raw_url: Any = None,
    ) -> Dict[str, Any]:
        return {
            "entity": entity,
            "title": title,
            "summary": summary,
            "signal_type": signal_type,
            "confidence": round(confidence, 4),
            "sentiment_score": round(sentiment_score, 4),
            "story_score": round(story_score, 4),
            "entity_domain": entity_domain,
            "supporting_signal_types": unique_preserve(
                [clean_text(x) for x in supporting_signal_types if clean_text(x)]
            )[:15],
            "raw_url": raw_url,
            "intelligence": compact_dict(intelligence),
        }

    def build_regime_card(bullish_rows: List[Dict[str, Any]], bearish_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        bullish_count = len(bullish_rows)
        bearish_count = len(bearish_rows)

        bullish_entities = select_entities_resolved(bullish_rows, 3)
        bearish_entities = select_entities_resolved(bearish_rows, 3)

        unwind_pct = diagnostics.get("unwind_pct", 0)
        build_pct = diagnostics.get("build_pct", 0)
        bearish_pct = diagnostics.get("bearish_pct", 0)
        bullish_pct = diagnostics.get("bullish_pct", 0)

        dominant_chain = chain_context.get("dominant_chain")
        dominance_pct = int(chain_context.get("dominance_pct", 0) * 100)

        # ---------------------------------------------------
        # DETERMINE REGIME
        # ---------------------------------------------------
        if bearish_count > bullish_count:
            direction_label = "Downside pressure"
            dominant_entities = bearish_entities
            dominant_pct = int(bearish_pct * 100)
            sentiment_score = -0.2

            if clusters["unwind"]:
                dominant_theme = "unwind"
                driver = "position unwinds"
            else:
                dominant_theme = "trend_bear"
                driver = "bearish trend alignment"

        elif bullish_count > bearish_count:
            direction_label = "Upside participation"
            dominant_entities = bullish_entities
            dominant_pct = int(bullish_pct * 100)
            sentiment_score = 0.2

            if clusters["build"]:
                dominant_theme = "build"
                driver = "fresh positioning"
            else:
                dominant_theme = "trend_bull"
                driver = "trend confirmation"

        else:
            return build_card(
                entity="MARKET",
                title="Market Regime",
                summary="Market conditions remain mixed with no dominant directional regime.",
                signal_type="market_regime",
                confidence=0.65,
                sentiment_score=0.0,
                story_score=14.0,
                entity_domain="market",
                supporting_signal_types=["trade_signals"],
                intelligence={
                    "theme": "mixed",
                    "breadth": {
                        "bullish_count": bullish_count,
                        "bearish_count": bearish_count,
                        "bullish_pct": bullish_pct,
                        "bearish_pct": bearish_pct,
                    },
                    "chain_context": chain_context,
                },
            )

        # ---------------------------------------------------
        # BUILD SUMMARY (UPGRADED)
        # ---------------------------------------------------
        summary = f"{direction_label} across {dominant_pct}% of tracked assets"

        if dominant_chain:
            summary += f", with activity concentrated on {dominant_chain} ({dominance_pct}%)"

        if dominant_entities:
            summary += f", led by {summarize_entities(dominant_entities, 'major assets')}"

        if driver:
            summary += f", driven by {driver}"

        summary += "."

        # ---------------------------------------------------
        # RETURN CARD
        # ---------------------------------------------------
        return build_card(
            entity="MARKET",
            title="Market Regime",
            summary=summary,
            signal_type="market_regime",
            confidence=0.72,
            sentiment_score=sentiment_score,
            story_score=15.0,
            entity_domain="market",
            supporting_signal_types=["trade_signals", "market_breadth"],
            intelligence={
                "theme": dominant_theme,
                "breadth": {
                    "bullish_count": bullish_count,
                    "bearish_count": bearish_count,
                    "bullish_pct": bullish_pct,
                    "bearish_pct": bearish_pct,
                },
                "chain_context": chain_context,
                "leaders": bullish_entities[:3],
                "laggards": bearish_entities[:3],
            },
        )

    def build_regime_card(bullish_rows: List[Dict[str, Any]], bearish_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        bullish_count = len(bullish_rows)
        bearish_count = len(bearish_rows)

        bullish_entities = select_entities_resolved(bullish_rows, 3)
        bearish_entities = select_entities_resolved(bearish_rows, 3)

        unwind_pct = diagnostics.get("unwind_pct", 0)
        build_pct = diagnostics.get("build_pct", 0)
        bearish_pct = diagnostics.get("bearish_pct", 0)
        bullish_pct = diagnostics.get("bullish_pct", 0)

        if bearish_count > bullish_count:
            if clusters["unwind"]:
                summary = (
                    f"Broad unwind across {int(unwind_pct * 100)}% of tracked assets, "
                    f"with downside pressure concentrated in "
                    f"{summarize_entities(bearish_entities, 'major assets')}."
                )
                dominant_theme = "unwind"
            else:
                summary = (
                    f"Downside pressure building across "
                    f"{summarize_entities(bearish_entities, 'major assets')} "
                    f"with bearish trend alignment."
                )
                dominant_theme = "trend_bear"

            sentiment_score = -0.2
        elif bullish_count > bearish_count:
            if clusters["build"]:
                summary = (
                    f"Constructive positioning is building across {int(build_pct * 100)}% of tracked assets, "
                    f"led by {summarize_entities(bullish_entities, 'key assets')}."
                )
                dominant_theme = "build"
            else:
                summary = (
                    f"Upside participation broadening across {int(bullish_pct * 100)}% of tracked assets, "
                    f"with strength led by {summarize_entities(bullish_entities, 'higher-beta assets')}."
                )
                dominant_theme = "trend_bull"

            sentiment_score = 0.2
        else:
            summary = (
                "Market conditions remain mixed with no dominant directional regime, "
                "as positioning and trend signals diverge."
            )
            dominant_theme = "mixed"
            sentiment_score = 0.0

        return build_card(
            entity="MARKET",
            title="Market Regime",
            summary=summary,
            signal_type="market_regime",
            confidence=0.72,
            sentiment_score=sentiment_score,
            story_score=15.0,
            entity_domain="market",
            supporting_signal_types=["trade_signals", "market_breadth"],
            intelligence={
                "theme": dominant_theme,
                "breadth": {
                    "bullish_count": bullish_count,
                    "bearish_count": bearish_count,
                    "bullish_pct": bullish_pct,
                    "bearish_pct": bearish_pct,
                },
                "leaders": bullish_entities[:3],
                "laggards": bearish_entities[:3],
            },
        )

    def build_flow_card() -> Optional[Dict[str, Any]]:
        unwind_rows = sorted(clusters["unwind"], key=score_trade_row, reverse=True)
        build_rows = sorted(clusters["build"], key=score_trade_row, reverse=True)

        unwind_entities = select_entities_resolved(unwind_rows, 3)
        build_entities = select_entities_resolved(build_rows, 3)

        dominant_chain = chain_context.get("dominant_chain")
        dominance_pct = int(chain_context.get("dominance_pct", 0) * 100)

        # ---------------------------------------------------
        # DETERMINE FLOW DIRECTION
        # ---------------------------------------------------
        if len(unwind_rows) > len(build_rows) and unwind_rows:
            top = unwind_rows[0]
            support = trade_row_support(top)

            flow_pct = diagnostics.get("unwind_pct", 0)
            flow_label = "Open interest unwinding"
            flow_direction = "unwind"
            sentiment = -0.1
            entities = unwind_entities
            theme = "oi_unwind"

        elif build_rows:
            top = build_rows[0]
            support = trade_row_support(top)

            flow_pct = diagnostics.get("build_pct", 0)
            flow_label = "Fresh positioning building"
            flow_direction = "build"
            sentiment = 0.1
            entities = build_entities
            theme = "oi_build"

        else:
            return None

        # ---------------------------------------------------
        # BUILD SUMMARY (UPGRADED)
        # ---------------------------------------------------
        summary = f"{flow_label} across {int(flow_pct * 100)}% of tracked assets"

        if dominant_chain:
            summary += f", with activity concentrated on {dominant_chain} ({dominance_pct}%)"

        if entities:
            summary += f", led by {summarize_entities(entities, 'key assets')}"

        if support["crowding_flags"]:
            summary += f", with {', '.join(support['crowding_flags'][:2])} signals present"

        summary += "."

        # ---------------------------------------------------
        # RETURN CARD
        # ---------------------------------------------------
        return build_card(
            entity=support["entity_display"] or "MARKET",
            title="Flow and Open Interest",
            summary=summary,
            signal_type="market_flow",
            confidence=max(0.58, safe_float(top.get("confidence", 0.0))),
            sentiment_score=sentiment,
            story_score=max(14.2, score_trade_row(top)),
            entity_domain="market",
            supporting_signal_types=support["reasons"][:8] + support["raw_signal_types"][:6],
            intelligence={
                "theme": theme,
                "flow": flow_direction,
                "flow_pct": flow_pct,
                "entities": entities[:3],
                "support_entity": support["entity_display"],
                "chain_context": chain_context,
                "crowding_flags": support["crowding_flags"],
                "metrics": support["metrics"],
            },
        )

    def build_momentum_card() -> Optional[Dict[str, Any]]:
        down_rows = sorted(clusters["trend_down"], key=score_trade_row, reverse=True)
        up_rows = sorted(clusters["trend_up"], key=score_trade_row, reverse=True)

        if not down_rows and not up_rows:
            return None

        dominant_chain = chain_context.get("dominant_chain")
        dominance_pct = int(chain_context.get("dominance_pct", 0) * 100)

        # ---------------------------------------------------
        # DETERMINE MOMENTUM DIRECTION
        # ---------------------------------------------------
        if len(down_rows) >= len(up_rows) and down_rows:
            top = down_rows[0]
            support = trade_row_support(top)

            entities = select_entities_resolved(down_rows, 3)
            momentum_pct = diagnostics.get("trend_down_pct", 0)

            direction_label = "Downside momentum accelerating"
            theme = "velocity_down"
            sentiment = -0.12
            chosen_rows = down_rows

        else:
            top = up_rows[0]
            support = trade_row_support(top)

            entities = select_entities_resolved(up_rows, 3)
            momentum_pct = diagnostics.get("trend_up_pct", 0)

            direction_label = "Upside momentum improving"
            theme = "velocity_up"
            sentiment = 0.12
            chosen_rows = up_rows

        # ---------------------------------------------------
        # BUILD SUMMARY (UPGRADED)
        # ---------------------------------------------------
        summary = f"{direction_label} across {int(momentum_pct * 100)}% of tracked assets"

        if dominant_chain:
            summary += f", with activity concentrated on {dominant_chain} ({dominance_pct}%)"

        if entities:
            summary += f", led by {summarize_entities(entities, 'leaders')}"

        # add structural context if available
        if support["structure"] != "unknown":
            summary += f", with structure {support['structure'].replace('_', ' ')}"

        summary += "."

        # ---------------------------------------------------
        # RETURN CARD
        # ---------------------------------------------------
        return build_card(
            entity=support["entity_display"] or "MARKET",
            title="Momentum and Velocity",
            summary=summary,
            signal_type="market_velocity",
            confidence=max(0.57, safe_float(top.get("confidence", 0.0))),
            sentiment_score=sentiment,
            story_score=max(13.8, score_trade_row(top)),
            entity_domain="market",
            supporting_signal_types=support["reasons"][:8] + support["raw_signal_types"][:6],
            intelligence={
                "theme": theme,
                "momentum_pct": momentum_pct,
                "entities": select_entities_resolved(chosen_rows, 5),
                "support_entity": support["entity_display"],
                "flow": support["flow"],
                "structure": support["structure"],
                "momentum": support["momentum"],
                "chain_context": chain_context,
            },
        )

    def build_performance_card() -> Optional[Dict[str, Any]]:
        bullish_sorted = sorted(clusters["bullish"], key=score_trade_row, reverse=True)
        bearish_sorted = sorted(clusters["bearish"], key=score_trade_row, reverse=True)

        if not bullish_sorted and not bearish_sorted:
            return None

        top_bullish = bullish_sorted[:3]
        top_bearish = bearish_sorted[:3]

        leader_entities = select_entities_resolved(top_bullish, 3)
        laggard_entities = select_entities_resolved(top_bearish, 3)

        leader_row = top_bullish[0] if top_bullish else {}
        laggard_row = top_bearish[0] if top_bearish else {}

        leader_support = trade_row_support(leader_row) if leader_row else {}
        laggard_support = trade_row_support(laggard_row) if laggard_row else {}

        bullish_pct = diagnostics.get("bullish_pct", 0)
        bearish_pct = diagnostics.get("bearish_pct", 0)

        dominant_chain = chain_context.get("dominant_chain")
        dominance_pct = int(chain_context.get("dominance_pct", 0) * 100)

        # ---------------------------------------------------
        # BUILD SUMMARY (UPGRADED)
        # ---------------------------------------------------
        summary = "Relative performance remains mixed"

        if bullish_pct > bearish_pct:
            summary = f"Upside leadership across {int(bullish_pct * 100)}% of tracked assets"
        elif bearish_pct > bullish_pct:
            summary = f"Weakness dominating across {int(bearish_pct * 100)}% of tracked assets"

        if dominant_chain:
            summary += f", with activity skewed toward {dominant_chain} ({dominance_pct}%)"

        if leader_entities:
            summary += f", led by {summarize_entities(leader_entities, 'leaders')}"

        if laggard_entities:
            summary += f", while laggards include {summarize_entities(laggard_entities, 'weak assets')}"

        summary += "."

        # ---------------------------------------------------
        # RETURN CARD
        # ---------------------------------------------------
        return build_card(
            entity=leader_support.get("entity_display") or "MARKET",
            title="Leaders and Laggards",
            summary=summary,
            signal_type="market_performance",
            confidence=max(
                0.56,
                safe_float(leader_row.get("confidence", 0.0)),
                safe_float(laggard_row.get("confidence", 0.0)),
            ),
            sentiment_score=0.0,
            story_score=13.6,
            entity_domain="market",
            supporting_signal_types=unique_preserve(
                safe_list(leader_support.get("reasons"))[:6]
                + safe_list(laggard_support.get("reasons"))[:6]
                + safe_list(leader_support.get("raw_signal_types"))[:4]
                + safe_list(laggard_support.get("raw_signal_types"))[:4]
            )[:15],
            intelligence={
                "theme": "relative_performance",
                "leaders": leader_entities[:5],
                "laggards": laggard_entities[:5],
                "leader_metrics": safe_dict(leader_support.get("metrics")),
                "laggard_metrics": safe_dict(laggard_support.get("metrics")),
                "breadth": {
                    "bullish_pct": bullish_pct,
                    "bearish_pct": bearish_pct,
                },
                "chain_context": chain_context,
            },
        )

    def build_positioning_card() -> Optional[Dict[str, Any]]:
        crowded_rows = sorted(clusters["crowded"], key=score_trade_row, reverse=True)
        if not crowded_rows:
            return None

        entities = select_entities_resolved(crowded_rows, 3)
        top = crowded_rows[0]
        support = trade_row_support(top)

        crowded_pct = diagnostics.get("high_oi_pct", 0)

        dominant_chain = chain_context.get("dominant_chain")
        dominance_pct = int(chain_context.get("dominance_pct", 0) * 100)

        # ---------------------------------------------------
        # IDENTIFY RISK FACTORS
        # ---------------------------------------------------
        bits: List[str] = []

        if "high_oi" in support["reason_set"]:
            bits.append("elevated open interest")

        if "divergence" in support["crowding_flags"]:
            bits.append("positioning divergence")

        if "negative_funding" in support["crowding_flags"]:
            bits.append("negative funding")

        # ---------------------------------------------------
        # BUILD SUMMARY (UPGRADED)
        # ---------------------------------------------------
        summary = f"Crowded positioning risk across {int(crowded_pct * 100)}% of tracked assets"

        if dominant_chain:
            summary += f", concentrated on {dominant_chain} ({dominance_pct}%)"

        if entities:
            summary += f", most visible in {summarize_entities(entities, 'select assets')}"

        if bits:
            summary += f", with {', '.join(bits[:3])}"

        summary += "."

        # ---------------------------------------------------
        # RETURN CARD
        # ---------------------------------------------------
        return build_card(
            entity=support["entity_display"] or "MARKET",
            title="Positioning Risk",
            summary=summary,
            signal_type="market_positioning",
            confidence=max(0.55, safe_float(top.get("confidence", 0.0))),
            sentiment_score=-0.05,
            story_score=max(13.4, score_trade_row(top)),
            entity_domain="market",
            supporting_signal_types=support["reasons"][:8] + support["raw_signal_types"][:6],
            intelligence={
                "theme": "positioning_risk",
                "entities": entities[:5],
                "crowding_flags": support["crowding_flags"],
                "support_entity": support["entity_display"],
                "metrics": support["metrics"],
                "chain_context": chain_context,
                "crowded_pct": crowded_pct,
            },
        )

    def entity_context_row(row: Dict[str, Any]) -> Dict[str, Any]:
        support = trade_row_support(row)
        return compact_dict({
            "display": support["entity_display"],
            "direction": clean_text(row.get("direction")),
            "confidence": safe_float(row.get("confidence", 0.0)),
            "signals": support["reasons"][:12],
            "signal_count": safe_int(row.get("signal_count", 0)),
            "score_breakdown": safe_dict(row.get("score_breakdown")),
            "strategy_modules": safe_list(row.get("strategy_modules"))[:12],
            "entity_domain": support["entity_domain"],
            "chain": support["chain"],
            "flow": support["flow"],
            "structure": support["structure"],
            "momentum": support["momentum"],
            "crowding_flags": support["crowding_flags"][:6],
            "supporting_signal_types": support["raw_signal_types"][:12],
            "metrics": support["metrics"],
        })

    if not trade_rows:
        return {
            "segment": "market",
            "story_count": 0,
            "entities": [],
            "cards": [],
            "entity_context": {},
            "ticker_board": [],
            "performance_board": {"leaders": [], "laggards": []},
            "chain_context": {"top_chains": []},
            "market_snapshot": {},
        }

    all_entities = set()
    for row in trade_rows:
        entity = clean_text(row.get("entity"))
        if entity:
            all_entities.add(entity)
    for row in signals:
        entity = clean_text(row.get("entity"))
        if entity:
            all_entities.add(entity)

    bullish_rows = [
        row for row in scored_trade_rows
        if clean_text(row.get("direction")).lower() in {"bullish", "strong_bullish"}
    ]
    bearish_rows = [
        row for row in scored_trade_rows
        if clean_text(row.get("direction")).lower() in {"bearish", "strong_bearish"}
    ]

    cards: List[Optional[Dict[str, Any]]] = [
        build_regime_card(bullish_rows, bearish_rows),
        build_flow_card(),
        build_momentum_card(),
        build_performance_card(),
        build_positioning_card(),
    ]

    deduped_cards: List[Dict[str, Any]] = []
    seen_card_keys = set()

    for card in cards:
        if not card:
            continue
        key = f"{clean_text(card.get('title'))}::{clean_text(card.get('summary'))}"
        if key in seen_card_keys:
            continue
        seen_card_keys.add(key)
        deduped_cards.append(card)

    entity_context: Dict[str, Any] = {}

    chain_scores: Dict[str, float] = {}

    for row in scored_trade_rows:
        entity = clean_text(row.get("entity"))
        if not entity:
            continue

        entity_rows = signal_map.get(entity, [])
        entity_rows = [x for x in entity_rows if isinstance(x, dict)]

        chain = infer_chain_for_entity(entity, entity_rows)

        if not chain or chain == "unknown":
            continue

        confidence = safe_float(row.get("confidence", 0.0))
        signal_count = safe_int(row.get("signal_count", 0))

        # 🔥 weighted scoring (important)
        weight = confidence * 2 + (signal_count * 0.1)

        chain_scores[chain] = chain_scores.get(chain, 0.0) + weight

    # ---------------------------------------------------
    # CHAIN INTELLIGENCE (ADD HERE)
    # ---------------------------------------------------

    total_score = sum(chain_scores.values())

    chain_distribution = {
        k: round(v / total_score, 3)
        for k, v in chain_scores.items()
    } if total_score > 0 else {}

    sorted_chains = sorted(
        chain_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    dominant_chain = sorted_chains[0][0] if sorted_chains else None
    dominance_pct = (
        round(sorted_chains[0][1] / total_score, 3)
        if total_score > 0 and sorted_chains else 0
    )

    chain_context = {
        "dominant_chain": dominant_chain,
        "dominance_pct": dominance_pct,
        "distribution": chain_distribution,
        "top_chains": sorted_chains[:5],
    }


    ticker_board: List[Dict[str, Any]] = []
    for row in scored_trade_rows[:20]:
        entity = clean_text(row.get("entity"))
        if not entity:
            continue
        support = trade_row_support(row)
        ticker_board.append(compact_dict({
            "entity": entity,
            "display": support["entity_display"],
            "direction": clean_text(row.get("direction")),
            "confidence": safe_float(row.get("confidence", 0.0)),
            "flow": support["flow"],
            "momentum": support["momentum"],
            "structure": support["structure"],
            "entity_domain": support["entity_domain"],
            "chain": support["chain"],
            "metrics": support["metrics"],
        }))

    leaders = [
        {
            "entity": clean_text(row.get("entity")),
            "display": resolve_entity(clean_text(row.get("entity"))),
            "confidence": safe_float(row.get("confidence", 0.0)),
        }
        for row in bullish_rows[:5]
        if clean_text(row.get("entity"))
    ]
    laggards = [
        {
            "entity": clean_text(row.get("entity")),
            "display": resolve_entity(clean_text(row.get("entity"))),
            "confidence": safe_float(row.get("confidence", 0.0)),
        }
        for row in bearish_rows[:5]
        if clean_text(row.get("entity"))
    ]

    # ---------------------------------------------------
    # CHAIN INTELLIGENCE (UPGRADED)
    # ---------------------------------------------------

    total_score = sum(chain_scores.values())

    chain_distribution = {
        k: round(v / total_score, 3)
        for k, v in chain_scores.items()
    } if total_score > 0 else {}

    sorted_chains = sorted(
        chain_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    dominant_chain = sorted_chains[0][0] if sorted_chains else None
    dominance_pct = (
        round(sorted_chains[0][1] / total_score, 3)
        if total_score > 0 and sorted_chains else 0
    )

    chain_context = {
        "dominant_chain": dominant_chain,
        "dominance_pct": dominance_pct,
        "distribution": chain_distribution,
        "top_chains": sorted_chains[:5],
    }

    return {
        "segment": "market",
        "story_count": len(deduped_cards),
        "entities": sorted(list(all_entities))[:50],
        "cards": deduped_cards[:5],
        "entity_context": entity_context,
        "ticker_board": ticker_board,
        "performance_board": {
            "leaders": leaders,
            "laggards": laggards,
        },

        "chain_context": chain_context,
        "market_snapshot": {
            "breadth": {
                "bullish_count": len(bullish_rows),
                "bearish_count": len(bearish_rows),
            },
            "cluster_counts": {k: len(v) for k, v in clusters.items()},
            "signal_diagnostics": diagnostics
        },
    }


def build_segments(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    # ---------------------------------------------------
    # CORE DATA EXTRACTION
    # ---------------------------------------------------
    top_stories = build_top_stories(snapshot)
    signals = object_rows(snapshot.get("signals", []))
    entity_map = build_entity_map(snapshot)
    # Index signals by entity (used everywhere)
    by_entity = index_signals_by_entity(signals)


    # ---------------------------------------------------
    # DOMAIN BUCKETING
    # ---------------------------------------------------
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "crypto_major": [],
        "crypto_alt": [],
        "crypto_culture": [],
        "macro": [],
        "regulation": [],
        "news": [],
        "defi": [],
        "flows": [],
        "market": [],  # stays for consistency (not used directly)
        "general": [],
    }

    for row in top_stories:
        domain = clean_text(row.get("domain")) or "general"
        buckets.setdefault(domain, []).append(row)

    # ---------------------------------------------------
    # BUILD SEGMENTS (WITH ENTITY MAP PROPAGATION)
    # ---------------------------------------------------
    segments = {
        "crypto_major": build_segment_from_domain(
            "crypto_major",
            buckets.get("crypto_major", []),
            by_entity,
        ),
        "crypto_alt": build_segment_from_domain(
            "crypto_alt",
            buckets.get("crypto_alt", []),
            by_entity,
        ),
        "crypto_culture": build_segment_from_domain(
            "crypto_culture",
            buckets.get("crypto_culture", []),
            by_entity,
        ),
        "macro": build_segment_from_domain(
            "macro",
            buckets.get("macro", []),
            by_entity,
        ),
        "regulation": build_segment_from_domain(
            "regulation",
            buckets.get("regulation", []),
            by_entity,
        ),
        "news": build_segment_from_domain(
            "news",
            buckets.get("news", []),
            by_entity,
        ),
        "defi": build_segment_from_domain(
            "defi",
            buckets.get("defi", []),
            by_entity,
        ),
        "flows": build_segment_from_domain(
            "flows",
            buckets.get("flows", []),
            by_entity,
        ),

        # 🔥 MARKET SEGMENT (brain output)
        "market": build_market_segment(snapshot, by_entity),
    }

    # ---------------------------------------------------
    # 🔥 OPTIONAL — SEGMENT METADATA (SAFE EXTENSION)
    # ---------------------------------------------------
    segments_meta = {
        "segment_counts": {
            k: len(v.get("cards", []))
            for k, v in segments.items()
        },
        "total_segments": len(segments),
    }

    # Attach meta safely (ToknNews ignores unknown fields)
    segments["_meta"] = segments_meta

    return segments

# ---------------------------------------------------
# FEATURED ITEMS
# ---------------------------------------------------

def build_featured_items(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    signals = object_rows(snapshot.get("signals", []))

    def first_of(signal_type: str) -> Dict[str, Any]:
        for row in signals:
            if clean_text(row.get("signal_type")) == signal_type:
                return row
        return {}

    memecoin_of_day = first_of("solana_memecoin_of_the_day")
    culture_rotation = first_of("solana_culture_rotation")
    macro_news = first_of("macro_news")

    return {
        "memecoin_of_the_day": memecoin_of_day,
        "culture_rotation": culture_rotation,
        "macro_news": macro_news,
    }


# ---------------------------------------------------
# ANCHOR ENRICHMENT
# ---------------------------------------------------

def build_anchor_enrichment(snapshot: Dict[str, Any], segments: Dict[str, Any]) -> Dict[str, Any]:
    narratives = object_rows(snapshot.get("narratives", []))
    narrative_summary = safe_dict(snapshot.get("narrative_summary"))
    narrative_alerts = object_rows(snapshot.get("narrative_alerts", []))
    clusters = object_rows(snapshot.get("clusters", []))
    metrics = safe_dict(snapshot.get("metrics"))
    market_segment = safe_dict(segments.get("market"))

    return {
        "lead_angles": top_n(narratives, 12),
        "narrative_summary": narrative_summary,
        "narrative_alerts": top_n(narrative_alerts, 20),
        "cluster_count": len(clusters),
        "headline_samples": top_n(metrics.get("headline_samples", []), 10),
        "top_entities": top_n(metrics.get("top_entities", []), 10),
        "market_intelligence": {
            "cards": top_n(market_segment.get("cards", []), 5),
            "ticker_board": top_n(market_segment.get("ticker_board", []), 12),
            "performance_board": safe_dict(market_segment.get("performance_board")),
            "chain_context": safe_dict(market_segment.get("chain_context")),
            "market_snapshot": safe_dict(market_segment.get("market_snapshot")),
        },
    }


# ---------------------------------------------------
# CHANNEL ADAPTER PAYLOADS
# ---------------------------------------------------

def build_channel_payloads(snapshot: Dict[str, Any], segments: Dict[str, Any]) -> Dict[str, Any]:
    top_stories = build_top_stories(snapshot)

    market_block = segments.get("market", {}).get("cards", [])[:5]
    crypto_block = (
        segments.get("crypto_major", {}).get("cards", [])[:3]
        + segments.get("crypto_alt", {}).get("cards", [])[:3]
        + segments.get("crypto_culture", {}).get("cards", [])[:3]
    )

    macro_block = segments.get("macro", {}).get("cards", [])[:5]
    regulation_block = segments.get("regulation", {}).get("cards", [])[:5]
    news_block = segments.get("news", {}).get("cards", [])[:5]
    defi_block = segments.get("defi", {}).get("cards", [])[:5]
    flows_block = segments.get("flows", {}).get("cards", [])[:5]

    return {
        "broadcast": {
            "top_stories": top_stories[:8],
            "market_block": market_block,
            "market_entities": segments.get("market", {}).get("entities", [])[:20],
            "market_entity_context": segments.get("market", {}).get("entity_context", {}),
            "market_ticker_board": segments.get("market", {}).get("ticker_board", [])[:15],
            "market_performance_board": segments.get("market", {}).get("performance_board", {}),
            "market_chain_context": segments.get("market", {}).get("chain_context", {}),
            "crypto_block": crypto_block[:6],
            "macro_block": macro_block,
            "regulation_block": regulation_block,
            "news_block": news_block,
            "defi_block": defi_block,
            "flows_block": flows_block,
        },
        "website": {
            "hero_story": top_stories[:1],
            "top_stories": top_stories[:12],
            "segments": segments,
        },
        "newsletter": {
            "lead": top_stories[:3],
            "market_briefs": market_block[:3] + crypto_block[:3] + macro_block[:2] + regulation_block[:2],
            "culture_briefs": segments.get("crypto_culture", {}).get("cards", [])[:4],
            "ticker_board": segments.get("market", {}).get("ticker_board", [])[:10],
        },
        "alerts": {
            "market_cards": market_block[:3],
            "leaders": safe_dict(segments.get("market", {}).get("performance_board")).get("leaders", [])[:3],
            "laggards": safe_dict(segments.get("market", {}).get("performance_board")).get("laggards", [])[:3],
            "top_flows": flows_block[:3],
        },
    }


# ---------------------------------------------------
# VERTICAL OPPORTUNITIES
# ---------------------------------------------------

def build_vertical_opportunities(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    metrics = safe_dict(snapshot.get("metrics"))
    signal_types = safe_dict(metrics.get("signal_types"))
    trade_rows = object_rows(safe_dict(snapshot.get("trade_signals")).get("rows"))

    opportunities: List[Dict[str, Any]] = []

    if sum(v for k, v in signal_types.items() if clean_text(k).startswith("macro_")) > 0:
        opportunities.append({
            "vertical": "macro_briefing",
            "reason": "Macro signals are present and can support a dedicated briefing product.",
        })

    if sum(v for k, v in signal_types.items() if clean_text(k).startswith("protocol_")) > 0:
        opportunities.append({
            "vertical": "defi_dashboard",
            "reason": "Protocol revenue and TVL data support a DeFi-focused content and analytics vertical.",
        })

    if safe_int(signal_types.get("solana_memecoin_trending", 0)) > 0:
        opportunities.append({
            "vertical": "memecoin_watch",
            "reason": "Memecoin trending and culture signals support a higher-frequency culture product.",
        })

    if safe_int(signal_types.get("news", 0)) + safe_int(signal_types.get("news_theme", 0)) > 0:
        opportunities.append({
            "vertical": "daily_newswire",
            "reason": "News and theme clustering support a recurring multi-domain news product.",
        })

    if safe_int(signal_types.get("large_token_transfer", 0)) > 0:
        opportunities.append({
            "vertical": "flow_monitor",
            "reason": "Large transfer data supports a flow-monitoring and alerting product.",
        })

    if trade_rows:
        opportunities.append({
            "vertical": "trading_desk",
            "reason": "Trade signals, ticker boards, positioning, and market cards support a dedicated trading-intelligence product.",
        })

    return opportunities


# ---------------------------------------------------
# MASTER VIEW
# ---------------------------------------------------

def build_media_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    segments = build_segments(snapshot)

    return {
        "view_name": "media",
        "updated_at": utc_now_iso(),
        "overview": build_overview(snapshot),
        "top_stories": build_top_stories(snapshot),
        "segments": segments,
        "featured_items": build_featured_items(snapshot),
        "anchor_enrichment": build_anchor_enrichment(snapshot, segments),
        "channel_payloads": build_channel_payloads(snapshot, segments),
        "vertical_opportunities": build_vertical_opportunities(snapshot),
    }


def run_media_view_engine() -> Dict[str, Any]:
    snapshot = load_snapshot()
    view = build_media_view(snapshot)
    write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, view)
    return view


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    payload = run_media_view_engine()
    print(json.dumps(payload, indent=2))
