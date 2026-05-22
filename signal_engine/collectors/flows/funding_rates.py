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
# MODULE: funding_rates
# PURPOSE: Collect and normalize perp funding rates across OKX and Hyperliquid
#          for flow trading, crowding analysis, and broadcast context.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This collector is designed to:
• fetch perp funding rates from OKX and Hyperliquid
• normalize venue responses into asset-level rows
• detect long-crowding and short-crowding extremes
• detect cross-venue funding divergence
• emit structured signals for ToknClaw strategy engines
• remain additive and OpenClaw agent ready

Primary Config
--------------
/opt/toknclaw/config/funding_rates_collector.json

Primary Outputs
---------------
• perp_funding_rate
• perp_funding_long_crowding
• perp_funding_short_crowding
• perp_funding_divergence
• perp_funding_summary
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

import requests

from signal_engine.collectors.registry import register_collector
from signal_engine.models.signal import Signal
from signal_engine.runtime_config import load_config

# ---------------------------------------------------
# CONFIG / URLS
# ---------------------------------------------------

CONFIG_FILE = "funding_rates_collector.json"

OKX_TICKERS_URL = "https://www.okx.com/api/v5/public/mark-price?instType=SWAP"
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "request_timeout_sec": 12,
    "max_signals_per_run": 120,
    "emit_neutral_rate_rows": True,
    "summary_top_n": 8,

    "symbols": [
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

    "venues_enabled": {
        "okx": True,
        "hyperliquid": True
    },

    "long_crowding_threshold": 0.0005,
    "short_crowding_threshold": -0.0005,
    "divergence_threshold": 0.00025,

    "okx_symbol_map": {
        "BTC": "BTC-USDT-SWAP",
        "ETH": "ETH-USDT-SWAP",
        "SOL": "SOL-USDT-SWAP",
        "BNB": "BNB-USDT-SWAP",
        "XRP": "XRP-USDT-SWAP",
        "DOGE": "DOGE-USDT-SWAP",
        "LINK": "LINK-USDT-SWAP",
        "AVAX": "AVAX-USDT-SWAP",
        "ARB": "ARB-USDT-SWAP",
        "OP": "OP-USDT-SWAP",
        "INJ": "INJ-USDT-SWAP",
        "PYTH": "PYTH-USDT-SWAP",
        "JUP": "JUP-USDT-SWAP",
        "RNDR": "RNDR-USDT-SWAP"
    },

    "hyperliquid_symbol_map": {
        "BTC": "BTC",
        "ETH": "ETH",
        "SOL": "SOL",
        "BNB": "BNB",
        "XRP": "XRP",
        "DOGE": "DOGE",
        "LINK": "LINK",
        "AVAX": "AVAX",
        "ARB": "ARB",
        "OP": "OP",
        "INJ": "INJ",
        "PYTH": "PYTH",
        "JUP": "JUP",
        "RNDR": "RNDR"
    }
}

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def clean_upper(value: Any) -> str:
    return clean_text(value).upper()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[FUNDING RATES] {message}")


def info_log(message: str) -> None:
    print(f"[FUNDING RATES] {message}")


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return deepcopy(DEFAULT_CONFIG)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)

    if not isinstance(merged.get("symbols"), list):
        merged["symbols"] = deepcopy(DEFAULT_CONFIG["symbols"])
    else:
        merged["symbols"] = [clean_upper(x) for x in merged["symbols"] if clean_text(x)]

    if not isinstance(merged.get("venues_enabled"), dict):
        merged["venues_enabled"] = deepcopy(DEFAULT_CONFIG["venues_enabled"])

    for key in ["okx_symbol_map", "hyperliquid_symbol_map"]:
        if not isinstance(merged.get(key), dict):
            merged[key] = deepcopy(DEFAULT_CONFIG[key])
        else:
            merged[key] = {
                clean_upper(k): clean_text(v)
                for k, v in merged[key].items()
                if clean_text(k) and clean_text(v)
            }

    return merged


def annualized_funding_pct(rate: float) -> float:
    return rate * 3.0 * 365.0 * 100.0


def avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)

# ---------------------------------------------------
# FETCHERS
# ---------------------------------------------------

def fetch_okx_rows(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:

    timeout = safe_int(cfg.get("request_timeout_sec", 12), 12)
    symbol_map = safe_dict(cfg.get("okx_symbol_map"))

    out = {}

    for entity, inst_id in symbol_map.items():

        try:
            url = "https://www.okx.com/api/v5/public/funding-rate"

            response = requests.get(
                url,
                params={"instId": inst_id},
                timeout=timeout
            )
            response.raise_for_status()

            data = response.json()
            rows = safe_list(safe_dict(data).get("data"))

            if not rows:
                continue

            row = safe_dict(rows[0])

            rate = safe_float(row.get("fundingRate"), 0.0)

            # fallback if needed
            if abs(rate) < 1e-9:
                rate = safe_float(row.get("nextFundingRate"), 0.0)

            out[entity] = {
                "entity": entity,
                "venue": "okx",
                "funding": rate,
                "mark_price": 0.0,  # not needed here
                "raw_symbol": inst_id,
            }

        except Exception as e:
            print("[OKX ERROR]", entity, e)
            continue

    return out

    # ---------------------------------------------------
    # 🔥 FIXED OKX FUNDING EXTRACTION BLOCK
    # ---------------------------------------------------

    # primary funding
    rate = safe_float(row.get("fundingRate"), 0.0)

    # fallback → next funding
    if abs(rate) < 1e-9:
        rate = safe_float(row.get("nextFundingRate"), 0.0)

    # fallback → legacy field
    if abs(rate) < 1e-9:
        rate = safe_float(row.get("funding"), 0.0)

    out[entity] = {
        "entity": entity,
        "venue": "okx",
        "funding": rate,
        "mark_price": safe_float(row.get("markPx"), 0.0),
        "raw_symbol": inst_id,
    }

    return out


def fetch_hyperliquid_rows(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    timeout = safe_int(cfg.get("request_timeout_sec", 12), 12)
    wanted_map = safe_dict(cfg.get("hyperliquid_symbol_map"))
    wanted_symbols = set(wanted_map.values())

    out: Dict[str, Dict[str, Any]] = {}

    try:
        response = requests.post(
            HYPERLIQUID_INFO_URL,
            json={"type": "metaAndAssetCtxs"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        debug_log(cfg, f"hyperliquid fetch failed error={exc}")
        return out

    meta = {}
    asset_ctxs = []

    if isinstance(payload, list) and len(payload) >= 2:
        meta = safe_dict(payload[0])
        asset_ctxs = safe_list(payload[1])

    universe = safe_list(meta.get("universe"))

    # Hyperliquid docs structure: universe metadata and asset contexts are parallel arrays.
    for idx, ctx in enumerate(asset_ctxs):
        ctx = safe_dict(ctx)
        if idx >= len(universe):
            continue

        meta_row = safe_dict(universe[idx])

        coin = clean_upper(meta_row.get("name"))
        if not coin or coin not in wanted_symbols:
            continue

        entity = None
        for k, v in wanted_map.items():
            if clean_upper(v) == coin:
                entity = clean_upper(k)
                break

        if not entity:
            continue

        out[entity] = {
            "entity": entity,
            "venue": "hyperliquid",
            "funding": safe_float(ctx.get("funding"), 0.0),
            "mark_price": safe_float(ctx.get("markPx"), 0.0),
            "raw_symbol": coin,
        }

    return out

# ---------------------------------------------------
# SIGNAL BUILDERS
# ---------------------------------------------------

def build_funding_rate_signal(entity: str, venues: Dict[str, float], mark_prices: Dict[str, float]) -> Signal:
    funding_values = list(venues.values())
    avg_funding = avg(funding_values)
    annualized_pct = annualized_funding_pct(avg_funding)
    best_mark = next((v for v in mark_prices.values() if v > 0), 0.0)

    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_funding_rate",
        entity=entity,
        title=f"{entity} perpetual funding rate",
        summary=(
            f"avg={avg_funding:.6f} | "
            f"annualized_pct={annualized_pct:.4f} | "
            f"mark_price={best_mark:.6f} | "
            f"venues={venues}"
        ),
        confidence=0.88,
        sentiment_score=0.0,
        raw_url=None,
    )


def build_long_crowding_signal(entity: str, avg_funding_rate: float, venues: Dict[str, float]) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_funding_long_crowding",
        entity=entity,
        title=f"{entity} long crowding detected",
        summary=(
            f"avg_funding={avg_funding_rate:.6f} | "
            f"annualized_pct={annualized_funding_pct(avg_funding_rate):.4f} | "
            f"venues={venues}"
        ),
        confidence=0.86,
        sentiment_score=-0.18,
        raw_url=None,
    )


def build_short_crowding_signal(entity: str, avg_funding_rate: float, venues: Dict[str, float]) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_funding_short_crowding",
        entity=entity,
        title=f"{entity} short crowding detected",
        summary=(
            f"avg_funding={avg_funding_rate:.6f} | "
            f"annualized_pct={annualized_funding_pct(avg_funding_rate):.4f} | "
            f"venues={venues}"
        ),
        confidence=0.86,
        sentiment_score=0.18,
        raw_url=None,
    )


def build_divergence_signal(entity: str, venues: Dict[str, float], divergence: float) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_funding_divergence",
        entity=entity,
        title=f"{entity} funding divergence detected",
        summary=(
            f"funding_divergence={divergence:.6f} | "
            f"venues={venues}"
        ),
        confidence=0.82,
        sentiment_score=0.04,
        raw_url=None,
    )


def build_summary_signal(
    rows_count: int,
    long_count: int,
    short_count: int,
    divergence_count: int,
    ranked: List[Dict[str, Any]],
    summary_top_n: int,
) -> Signal:
    top_parts: List[str] = []

    for row in ranked[:summary_top_n]:
        entity = clean_upper(row.get("entity"))
        value = safe_float(row.get("abs_avg_funding"), 0.0)
        top_parts.append(f"{entity}({value:.6f})")

    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_funding_summary",
        entity="PERP_FUNDING",
        title="Perpetual funding summary",
        summary=(
            f"rows={rows_count} | "
            f"long_crowding={long_count} | "
            f"short_crowding={short_count} | "
            f"divergence={divergence_count} | "
            f"top_abs_rates={', '.join(top_parts) if top_parts else 'none'}"
        ),
        confidence=0.84,
        sentiment_score=0.0,
        raw_url=None,
    )

# ---------------------------------------------------
# PUBLIC COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="funding_rates",
    priority=1,
    tags=["flows", "derivatives", "funding", "perps", "majors", "hyperliquid"],
    category="flows",
    execution="fast",
)
def fetch_funding_rate_signals() -> List[Signal]:
    started = time.time()
    cfg = load_engine_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        info_log("disabled by config")
        return signals

    venues_enabled = safe_dict(cfg.get("venues_enabled"))

    okx_rows = fetch_okx_rows(cfg) if venues_enabled.get("okx", True) else {}
    hyper_rows = fetch_hyperliquid_rows(cfg) if venues_enabled.get("hyperliquid", True) else {}

    # ---------------------------------------------------
    # 🔥 CRITICAL FIX: UNION OF ENTITIES
    # ---------------------------------------------------

    configured = set(cfg.get("symbols", []))
    okx_entities = set(okx_rows.keys())
    hl_entities = set(hyper_rows.keys())

    all_entities = configured | okx_entities | hl_entities

    emit_neutral = bool(cfg.get("emit_neutral_rate_rows", True))
    long_threshold = safe_float(cfg.get("long_crowding_threshold", 0.0005), 0.0005)
    short_threshold = safe_float(cfg.get("short_crowding_threshold", -0.0005), -0.0005)
    divergence_threshold = safe_float(cfg.get("divergence_threshold", 0.00025), 0.00025)
    max_signals = safe_int(cfg.get("max_signals_per_run", 120), 120)

    long_count = 0
    short_count = 0
    divergence_count = 0

    ranked_rows: List[Dict[str, Any]] = []

    # ---------------------------------------------------
    # 🔥 MAIN LOOP
    # ---------------------------------------------------

    for entity in sorted(all_entities):

        venues: Dict[str, float] = {}
        mark_prices: Dict[str, float] = {}

        okx = okx_rows.get(entity)
        hl = hyper_rows.get(entity)

        if okx:
            venues["okx"] = safe_float(okx.get("funding"), 0.0)
            mark_prices["okx"] = safe_float(okx.get("mark_price"), 0.0)

        if hl:
            venues["hyperliquid"] = safe_float(hl.get("funding"), 0.0)
            mark_prices["hyperliquid"] = safe_float(hl.get("mark_price"), 0.0)

        # ---------------------------------------------------
        # 🔥 DEBUG / VALIDATION
        # ---------------------------------------------------

        if hl:
            print("[HL MERGE]", entity, venues)

        if not venues:
            continue

        # ---------------------------------------------------
        # FUNDING AGGREGATION
        # ---------------------------------------------------

        hl = venues.get("hyperliquid")
        okx = venues.get("okx")

        if hl is not None and okx is not None:
            # HL leads, OKX confirms
            avg_funding_rate = (hl * 0.7) + (okx * 0.3)

        elif hl is not None:
            avg_funding_rate = hl

        elif okx is not None:
            avg_funding_rate = okx

        else:
            continue

        ranked_rows.append({
            "entity": entity,
            "abs_avg_funding": abs(avg_funding_rate),
        })

        # ---------------------------------------------------
        # BASE SIGNAL
        # ---------------------------------------------------

        if emit_neutral:
            signals.append(build_funding_rate_signal(entity, venues, mark_prices))

        # ---------------------------------------------------
        # CROWDING
        # ---------------------------------------------------

        if avg_funding_rate >= long_threshold:
            signals.append(build_long_crowding_signal(entity, avg_funding_rate, venues))
            long_count += 1

        elif avg_funding_rate <= short_threshold:
            signals.append(build_short_crowding_signal(entity, avg_funding_rate, venues))
            short_count += 1

        # ---------------------------------------------------
        # DIVERGENCE (KEY ALPHA)
        # ---------------------------------------------------

        if len(venues) >= 2:
            venue_values = list(venues.values())
            divergence = max(venue_values) - min(venue_values)

            if abs(divergence) >= divergence_threshold:

                # 🔥 BOOST conviction
                if hl is not None:
                    avg_funding_rate += hl * 0.25
                # ❌ No weak Shit
                if abs(avg_funding_rate) < 0.000003:
                    continue

                signals.append(build_divergence_signal(entity, venues, divergence))
                divergence_count += 1
        if len(signals) >= max_signals:
            break

    # ---------------------------------------------------
    # RANKING
    # ---------------------------------------------------

    ranked_rows.sort(
        key=lambda x: safe_float(x.get("abs_avg_funding"), 0.0),
        reverse=True
    )

    # ---------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------

    signals.append(
        build_summary_signal(
            rows_count=len(ranked_rows),
            long_count=long_count,
            short_count=short_count,
            divergence_count=divergence_count,
            ranked=ranked_rows,
            summary_top_n=safe_int(cfg.get("summary_top_n", 8), 8),
        )
    )

    runtime = round(time.time() - started, 2)

    debug_log(
        cfg,
        f"entities={len(all_entities)} "
        f"okx_rows={len(okx_rows)} "
        f"hyperliquid_rows={len(hyper_rows)} "
        f"signals={len(signals)} runtime={runtime}s"
    )

    return signals[:max_signals]
