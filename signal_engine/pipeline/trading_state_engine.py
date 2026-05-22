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
# MODULE: trading_state_engine
# PURPOSE: Assemble a single canonical trading_state.json contract from
#          existing ToknClaw intelligence outputs without duplicating
#          upstream trading, regime, volatility, structure, or portfolio logic.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• consume existing snapshot intelligence outputs
• normalize them into one stable machine-readable trading contract
• write /opt/toknclaw/data/trading/trading_state.json atomically
• preserve explainability for dashboards, bots, and OpenClaw agents
• remain extensible for future TA, ML, and execution modules

Primary Inputs
--------------
/opt/toknclaw/data/snapshots/latest_snapshot.json
/opt/toknclaw/data/paper_trading_state.json

Primary Output
--------------
/opt/toknclaw/data/trading/trading_state.json

Design Notes
------------
• no collector execution
• no duplicate signal scoring
• no duplicate regime classification
• assembler only
• OpenClaw hook friendly
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot.json")
PAPER_TRADING_STATE_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")

OUTPUT_PATH = Path("/opt/toknclaw/data/trading/trading_state.json")
TMP_OUTPUT_PATH = Path("/opt/toknclaw/data/trading/trading_state.tmp")

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


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


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in {"true", "True", "1", 1}:
        return True
    if value in {"false", "False", "0", 0}:
        return False
    return default


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


# ---------------------------------------------------
# LOADERS
# ---------------------------------------------------

def load_snapshot() -> Dict[str, Any]:
    data = read_json_file(SNAPSHOT_PATH, {})
    return data if isinstance(data, dict) else {}


def load_paper_trading_state() -> Dict[str, Any]:
    data = read_json_file(PAPER_TRADING_STATE_PATH, {})
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------
# EXTRACTORS
# ---------------------------------------------------

def get_trade_signal_rows(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    trade_signals = safe_dict(snapshot.get("trade_signals"))
    rows = safe_list(trade_signals.get("rows"))
    return [safe_dict(row) for row in rows if isinstance(row, dict)]


def get_market_regime(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return safe_dict(snapshot.get("market_regime"))


def get_volatility_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    volatility = snapshot.get("volatility")

    if isinstance(volatility, dict) and "volatility_summary" in volatility:
        return volatility

    return {
        "volatility": safe_dict(snapshot.get("volatility")),
        "volatility_summary": safe_dict(snapshot.get("volatility_summary")),
        "volatility_alerts": safe_list(snapshot.get("volatility_alerts")),
    }


def get_market_structure_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    market_structure = snapshot.get("market_structure")

    if isinstance(market_structure, dict) and "market_structure_summary" in market_structure:
        return market_structure

    return {
        "market_structure": safe_dict(snapshot.get("market_structure")),
        "market_structure_summary": safe_dict(snapshot.get("market_structure_summary")),
        "market_structure_alerts": safe_list(snapshot.get("market_structure_alerts")),
        "market_structure_entities": safe_list(snapshot.get("market_structure_entities")),
        "market_structure_regime": snapshot.get("market_structure_regime"),
    }


def get_signal_velocity_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return safe_dict(snapshot.get("signal_velocity"))


def get_cross_asset_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return safe_dict(snapshot.get("cross_asset_intelligence"))


def get_paper_trading_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    paper = safe_dict(snapshot.get("paper_trading"))
    if paper:
        return paper
    return load_paper_trading_state()


# ---------------------------------------------------
# MARKET STATE
# ---------------------------------------------------

def build_market_state(
    regime_payload: Dict[str, Any],
    volatility_payload: Dict[str, Any],
    market_structure_payload: Dict[str, Any],
    cross_asset_payload: Dict[str, Any],
) -> Dict[str, Any]:
    regime_name = clean_text(regime_payload.get("name"))
    regime_bias = clean_text(regime_payload.get("broadcast_bias")).lower()
    regime_confidence = safe_float(regime_payload.get("confidence"), 0.0)

    volatility_summary = safe_dict(volatility_payload.get("volatility_summary"))
    volatility_regime = clean_text(volatility_summary.get("regime"))

    structure_summary = safe_dict(market_structure_payload.get("market_structure_summary"))
    structure_regime = clean_text(structure_summary.get("regime"))

    liquidity_regime = clean_text(regime_payload.get("liquidity_regime"))
    cross_liquidity_regime = clean_text(cross_asset_payload.get("liquidity_regime"))
    macro_alignment = clean_text(cross_asset_payload.get("macro_alignment"))

    if volatility_regime == "extreme_volatility":
        normalized_volatility = "extreme"
    elif volatility_regime in {"high_volatility", "elevated_volatility"}:
        normalized_volatility = "elevated"
    else:
        normalized_volatility = "contained"

    if regime_bias in {"bullish", "bearish", "neutral"}:
        normalized_bias = regime_bias
    else:
        normalized_bias = "neutral"

    if normalized_bias == "bullish" and normalized_volatility == "contained":
        normalized_regime = "risk_on"
    elif normalized_bias == "bearish":
        normalized_regime = "risk_off"
    else:
        normalized_regime = "mixed"

    return {
        "regime": normalized_regime,
        "bias": normalized_bias,
        "volatility": normalized_volatility,
        "regime_name": regime_name or None,
        "regime_confidence": round(regime_confidence, 4),
        "liquidity_regime": liquidity_regime or cross_liquidity_regime or None,
        "structure_regime": structure_regime or None,
        "macro_alignment": macro_alignment or None,
        "source_summary": {
            "market_regime": regime_payload,
            "volatility_summary": volatility_summary,
            "market_structure_summary": structure_summary,
        },
    }


# ---------------------------------------------------
# FLOW
# ---------------------------------------------------

def build_flow(snapshot: Dict[str, Any], trade_rows: List[Dict[str, Any]], cross_asset_payload: Dict[str, Any]) -> Dict[str, Any]:
    bullish_count = 0
    bearish_count = 0

    funding_negative = 0
    funding_positive = 0

    oi_build = 0
    oi_unwind = 0

    liquidation_long = 0
    liquidation_short = 0

    reasons_index: Dict[str, int] = {}

    for row in trade_rows:
        direction = clean_text(row.get("direction"))
        reasons = safe_list(row.get("reasons"))

        if direction in {"bullish", "strong_bullish"}:
            bullish_count += 1
        elif direction in {"bearish", "strong_bearish"}:
            bearish_count += 1

        for reason in reasons:
            reason_text = clean_text(reason)
            if not reason_text:
                continue

            reasons_index[reason_text] = reasons_index.get(reason_text, 0) + 1

            if reason_text == "funding_negative":
                funding_negative += 1
            elif reason_text == "funding_positive":
                funding_positive += 1
            elif reason_text in {"oi_accel_base", "oi_build_accel"}:
                oi_build += 1
            elif reason_text in {"oi_unwind_base", "oi_unwind_accel"}:
                oi_unwind += 1
            elif reason_text in {"long_flush"}:
                liquidation_long += 1
            elif reason_text in {"short_flush"}:
                liquidation_short += 1

    total_directional = bullish_count + bearish_count
    total_funding = funding_negative + funding_positive
    total_oi = oi_build + oi_unwind
    total_liq = liquidation_long + liquidation_short

    if total_funding == 0:
        funding_bias = "mixed"
    elif funding_negative > funding_positive:
        funding_bias = "negative"
    elif funding_positive > funding_negative:
        funding_bias = "positive"
    else:
        funding_bias = "mixed"

    liquidity_regime = clean_text(cross_asset_payload.get("liquidity_regime"))
    stablecoin_flow = clean_text(cross_asset_payload.get("stablecoin_flow"))

    return {
        "directional_balance": {
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "total_directional_count": total_directional,
        },
        "oi_build_pct": round((oi_build / total_oi), 4) if total_oi > 0 else 0.0,
        "oi_unwind_pct": round((oi_unwind / total_oi), 4) if total_oi > 0 else 0.0,
        "liquidation_activity": {
            "long_flush_count": liquidation_long,
            "short_flush_count": liquidation_short,
            "total_count": total_liq,
        },
        "funding_bias": funding_bias,
        "liquidity_regime": liquidity_regime or None,
        "stablecoin_flow": stablecoin_flow or None,
        "dominant_flow_reasons": [
            {"reason": k, "count": v}
            for k, v in sorted(reasons_index.items(), key=lambda x: (-x[1], x[0]))[:10]
        ],
    }


# ---------------------------------------------------
# MOMENTUM
# ---------------------------------------------------

def build_momentum(signal_velocity_payload: Dict[str, Any], trade_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = safe_dict(signal_velocity_payload.get("summary"))
    entity_rows = [
        safe_dict(row)
        for row in safe_list(signal_velocity_payload.get("entities"))
        if isinstance(row, dict)
    ]

    trend_up = 0
    trend_down = 0
    explosive = 0
    fast = 0

    trade_direction_by_entity: Dict[str, str] = {}
    trade_confidence_by_entity: Dict[str, float] = {}

    for row in trade_rows:
        entity = clean_upper(row.get("entity"))
        if not entity:
            continue
        trade_direction_by_entity[entity] = clean_text(row.get("direction"))
        trade_confidence_by_entity[entity] = safe_float(row.get("confidence"), 0.0)

    leaders: List[Dict[str, Any]] = []
    laggards: List[Dict[str, Any]] = []

    for row in entity_rows:
        entity = clean_upper(row.get("entity"))
        velocity_score = safe_float(row.get("velocity_score"), 0.0)
        velocity_bucket = clean_text(row.get("velocity_bucket"))
        trade_direction = trade_direction_by_entity.get(entity, "neutral")
        trade_confidence = trade_confidence_by_entity.get(entity, 0.0)

        if trade_direction in {"bullish", "strong_bullish"}:
            trend_up += 1
        elif trade_direction in {"bearish", "strong_bearish"}:
            trend_down += 1

        if velocity_bucket == "explosive":
            explosive += 1
        elif velocity_bucket == "fast":
            fast += 1

        row_out = {
            "entity": entity,
            "velocity_score": round(velocity_score, 4),
            "velocity_bucket": velocity_bucket or None,
            "trade_direction": trade_direction,
            "trade_confidence": round(trade_confidence, 4),
            "state": row.get("state"),
            "sectors": safe_list(row.get("sectors")),
        }

        if trade_direction in {"bullish", "strong_bullish"}:
            leaders.append(row_out)
        elif trade_direction in {"bearish", "strong_bearish"}:
            laggards.append(row_out)

    total_trending = trend_up + trend_down

    leaders.sort(
        key=lambda x: (
            x.get("velocity_score", 0.0),
            x.get("trade_confidence", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )
    laggards.sort(
        key=lambda x: (
            x.get("velocity_score", 0.0),
            x.get("trade_confidence", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    return {
        "trend_up_pct": round((trend_up / total_trending), 4) if total_trending > 0 else 0.0,
        "trend_down_pct": round((trend_down / total_trending), 4) if total_trending > 0 else 0.0,
        "explosive_count": explosive,
        "fast_count": fast,
        "broadcast_urgency": clean_text(summary.get("broadcast_urgency")) or None,
        "vertical_priority": safe_list(summary.get("vertical_priority")),
        "leaders": leaders[:15],
        "laggards": laggards[:15],
    }


# ---------------------------------------------------
# STRUCTURE
# ---------------------------------------------------

def build_structure(market_structure_payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = safe_dict(market_structure_payload.get("market_structure_summary"))
    entity_rows = [
        safe_dict(row)
        for row in safe_list(market_structure_payload.get("market_structure_entities"))
        if isinstance(row, dict)
    ]

    fragile_entities: List[str] = []
    constructive_entities: List[str] = []

    for row in entity_rows:
        entity = clean_upper(row.get("entity"))
        score = safe_float(row.get("market_structure_score"), 0.0)
        cluster_types = [clean_text(x) for x in safe_list(row.get("cluster_types"))]

        if not entity:
            continue

        if "defi_liquidation" in cluster_types or score >= 0.75:
            fragile_entities.append(entity)
        elif "protocol_tvl" in cluster_types or "protocol_revenue" in cluster_types or score <= 0.35:
            constructive_entities.append(entity)

    return {
        "regime": clean_text(summary.get("regime")) or None,
        "top_entity": clean_text(summary.get("top_entity")) or None,
        "top_entity_structure_score": round(safe_float(summary.get("top_entity_structure_score"), 0.0), 4),
        "constructive_entities": unique_preserve(constructive_entities)[:25],
        "fragile_entities": unique_preserve(fragile_entities)[:25],
        "factor_summary": safe_dict(summary.get("factors")),
    }


# ---------------------------------------------------
# POSITIONING
# ---------------------------------------------------

def build_positioning(trade_rows: List[Dict[str, Any]], paper_trading_payload: Dict[str, Any]) -> Dict[str, Any]:
    crowded_longs: List[str] = []
    crowded_shorts: List[str] = []
    short_squeeze_watch: List[str] = []
    long_liquidation_watch: List[str] = []
    weak_positions: List[Dict[str, Any]] = []
    rotation_candidates: List[Dict[str, Any]] = []

    for row in trade_rows:
        entity = clean_upper(row.get("entity"))
        confidence = safe_float(row.get("confidence"), 0.0)
        direction = clean_text(row.get("direction"))
        reasons = [clean_text(x) for x in safe_list(row.get("reasons"))]

        if "crowded_longs" in reasons:
            crowded_longs.append(entity)
        if "crowded_shorts" in reasons:
            crowded_shorts.append(entity)
        if "short_squeeze" in reasons:
            short_squeeze_watch.append(entity)
        if "long_liq" in reasons:
            long_liquidation_watch.append(entity)

        if direction in {"strong_bullish", "strong_bearish"} and confidence >= 0.60:
            rotation_candidates.append(
                {
                    "entity": entity,
                    "direction": direction,
                    "confidence": round(confidence, 4),
                    "reasons": reasons[:6],
                }
            )

    open_positions = safe_dict(paper_trading_payload.get("open_positions"))

    for position in open_positions.values():
        pos = safe_dict(position)

        entity = clean_upper(pos.get("entity"))
        side = clean_text(pos.get("side"))
        unrealized_pnl_pct = round(safe_float(pos.get("unrealized_pnl_pct"), 0.0), 4)
        confidence = round(safe_float(pos.get("confidence"), 0.0), 4)

        if confidence < 0.40 or unrealized_pnl_pct <= -2.0:
            weak_positions.append(
                {
                    "entity": entity,
                    "side": side,
                    "confidence": confidence,
                    "unrealized_pnl_pct": unrealized_pnl_pct,
                    "trade_id": clean_text(pos.get("trade_id")),
                }
            )

    rotation_candidates.sort(
        key=lambda x: (
            x.get("confidence", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    weak_positions.sort(
        key=lambda x: (
            x.get("confidence", 1.0),
            -x.get("unrealized_pnl_pct", 0.0),
            x.get("entity", ""),
        )
    )

    return {
        "crowded_longs": unique_preserve(crowded_longs)[:25],
        "crowded_shorts": unique_preserve(crowded_shorts)[:25],
        "short_squeeze_watch": unique_preserve(short_squeeze_watch)[:25],
        "long_liquidation_watch": unique_preserve(long_liquidation_watch)[:25],
        "weak_positions": weak_positions[:15],
        "rotation_candidates": rotation_candidates[:15],
    }


# ---------------------------------------------------
# ENTITY STATE
# ---------------------------------------------------

def build_entity_state(
    trade_rows: List[Dict[str, Any]],
    signal_velocity_payload: Dict[str, Any],
    market_structure_payload: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    velocity_rows = {
        clean_upper(row.get("entity")): safe_dict(row)
        for row in safe_list(signal_velocity_payload.get("entities"))
        if isinstance(row, dict) and clean_upper(row.get("entity"))
    }

    structure_rows = {
        clean_upper(row.get("entity")): safe_dict(row)
        for row in safe_list(market_structure_payload.get("market_structure_entities"))
        if isinstance(row, dict) and clean_upper(row.get("entity"))
    }

    entity_state: Dict[str, Dict[str, Any]] = {}

    for row in trade_rows:
        entity = clean_upper(row.get("entity"))
        if not entity:
            continue

        velocity = velocity_rows.get(entity, {})
        structure = structure_rows.get(entity, {})

        entity_state[entity] = {
            "direction": clean_text(row.get("direction")) or "neutral",
            "confidence": round(safe_float(row.get("confidence"), 0.0), 4),
            "reasons": [clean_text(x) for x in safe_list(row.get("reasons")) if clean_text(x)][:8],
            "score_breakdown": safe_dict(row.get("score_breakdown")),
            "signal_count": safe_int(row.get("signal_count"), 0),
            "perp_setups": [clean_text(x) for x in safe_list(row.get("perp_setups")) if clean_text(x)][:3],
            "velocity_score": round(safe_float(velocity.get("velocity_score"), 0.0), 4),
            "velocity_bucket": clean_text(velocity.get("velocity_bucket")) or None,
            "state": velocity.get("state"),
            "structure_score": round(safe_float(structure.get("market_structure_score"), 0.0), 4),
            "structure_cluster_types": safe_list(structure.get("cluster_types")),
            "total_value_usd": round(safe_float(structure.get("total_value_usd"), 0.0), 2),
        }

    return entity_state


# ---------------------------------------------------
# CHAIN STATE
# ---------------------------------------------------

def build_chain_state(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    signals = [safe_dict(row) for row in safe_list(snapshot.get("signals")) if isinstance(row, dict)]

    chain_distribution: Dict[str, int] = {}
    chain_keywords = {
        "solana": ["solana", "jupiter", "raydium", "pumpfun", "pump"],
        "ethereum": ["ethereum", "eth", "evm"],
        "bitcoin": ["bitcoin", "btc"],
    }

    for row in signals:
        signal_type = clean_text(row.get("signal_type")).lower()
        entity = clean_text(row.get("entity")).lower()
        text_blob = f"{signal_type} {entity}"

        matched_chain = None

        for chain_name, keywords in chain_keywords.items():
            if any(keyword in text_blob for keyword in keywords):
                matched_chain = chain_name
                break

        if matched_chain is None:
            matched_chain = "unknown"

        chain_distribution[matched_chain] = chain_distribution.get(matched_chain, 0) + 1

    dominant_chain = None
    if chain_distribution:
        dominant_chain = sorted(
            chain_distribution.items(),
            key=lambda x: (-x[1], x[0]),
        )[0][0]

    total = sum(chain_distribution.values()) or 1

    normalized_distribution = {
        chain: round(count / total, 4)
        for chain, count in sorted(chain_distribution.items(), key=lambda x: (-x[1], x[0]))
    }

    return {
        "dominant_chain": dominant_chain,
        "distribution": normalized_distribution,
        "raw_counts": chain_distribution,
    }


# ---------------------------------------------------
# PORTFOLIO STATE
# ---------------------------------------------------

def build_portfolio_state(paper_trading_payload: Dict[str, Any]) -> Dict[str, Any]:
    portfolio = safe_dict(paper_trading_payload.get("portfolio"))
    open_positions = safe_dict(paper_trading_payload.get("open_positions"))
    closed_positions = safe_list(paper_trading_payload.get("closed_positions"))
    summary = safe_dict(paper_trading_payload.get("summary"))
    engine_status = safe_dict(paper_trading_payload.get("engine_status"))

    open_rows: List[Dict[str, Any]] = []

    for position in open_positions.values():
        pos = safe_dict(position)

        open_rows.append(
            {
                "trade_id": clean_text(pos.get("trade_id")),
                "entity": clean_upper(pos.get("entity")),
                "side": clean_text(pos.get("side")),
                "direction": clean_text(pos.get("direction")),
                "confidence": round(safe_float(pos.get("confidence"), 0.0), 4),
                "entry_price_usd": round(safe_float(pos.get("entry_price_usd"), 0.0), 12),
                "mark_price_usd": round(safe_float(pos.get("mark_price_usd"), 0.0), 12),
                "position_size_usd": round(safe_float(pos.get("position_size_usd"), 0.0), 4),
                "unrealized_pnl_usd": round(safe_float(pos.get("unrealized_pnl_usd"), 0.0), 4),
                "unrealized_pnl_pct": round(safe_float(pos.get("unrealized_pnl_pct"), 0.0), 4),
                "opened_at": clean_text(pos.get("opened_at")) or None,
            }
        )

    open_rows.sort(
        key=lambda x: (
            x.get("confidence", 0.0),
            x.get("position_size_usd", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    return {
        "engine_status": engine_status,
        "portfolio": portfolio,
        "summary": summary,
        "open_positions": open_rows,
        "open_position_count": len(open_rows),
        "closed_position_count": len(closed_positions),
    }


# ---------------------------------------------------
# EXTENSIONS
# ---------------------------------------------------

def build_extensions(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    extensions: Dict[str, Any] = {}

    if "quant_factors" in snapshot:
        extensions["quant_factors"] = safe_dict(snapshot.get("quant_factors"))

    if "conviction_scores" in snapshot:
        extensions["conviction_scores"] = snapshot.get("conviction_scores")

    if "alpha_attribution" in snapshot:
        extensions["alpha_attribution"] = snapshot.get("alpha_attribution")

    if "market_stress" in snapshot:
        extensions["market_stress"] = snapshot.get("market_stress")

    if "macro_liquidity" in snapshot:
        extensions["macro_liquidity"] = snapshot.get("macro_liquidity")

    if "liquidity_rotation" in snapshot:
        extensions["liquidity_rotation"] = snapshot.get("liquidity_rotation")

    return extensions


# ---------------------------------------------------
# SOURCE MANIFEST
# ---------------------------------------------------

def build_source_manifest(snapshot: Dict[str, Any], paper_trading_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "snapshot_timestamp": snapshot.get("timestamp"),
        "snapshot_path": str(SNAPSHOT_PATH),
        "paper_trading_state_path": str(PAPER_TRADING_STATE_PATH),
        "paper_trading_status": safe_dict(paper_trading_payload.get("engine_status")).get("status"),
        "modules": {
            "trade_signals": "snapshot.trade_signals.rows",
            "market_regime": "snapshot.market_regime",
            "volatility": "snapshot.volatility / snapshot.volatility_summary",
            "market_structure": "snapshot.market_structure / snapshot.market_structure_summary",
            "signal_velocity": "snapshot.signal_velocity",
            "cross_asset_intelligence": "snapshot.cross_asset_intelligence",
            "paper_trading": "snapshot.paper_trading or /opt/toknclaw/data/paper_trading_state.json",
        },
    }


# ---------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------

def build_trading_state(snapshot: Optional[Dict[str, Any]] = None, write_output: bool = True) -> Dict[str, Any]:
    snapshot = snapshot if isinstance(snapshot, dict) else load_snapshot()

    # ---------------------------------------------------
    # CORE INPUTS
    # ---------------------------------------------------

    trade_rows = get_trade_signal_rows(snapshot)

    regime_payload = get_market_regime(snapshot)
    volatility_payload = get_volatility_payload(snapshot)
    market_structure_payload = get_market_structure_payload(snapshot)
    signal_velocity_payload = get_signal_velocity_payload(snapshot)
    cross_asset_payload = get_cross_asset_payload(snapshot)
    paper_trading_payload = get_paper_trading_payload(snapshot)

    momentum = build_momentum(signal_velocity_payload, trade_rows)

    # ---------------------------------------------------
    # 🔴 LEADERS / LAGGARDS (FIXED — SOURCE = TRADE ENGINE)
    # ---------------------------------------------------

    leaders: List[Dict[str, Any]] = []
    laggards: List[Dict[str, Any]] = []

    for row in trade_rows:
        entity = clean_upper(row.get("entity"))
        direction = clean_text(row.get("direction"))
        confidence = round(safe_float(row.get("confidence"), 0.0), 4)
        priority_score = round(safe_float(row.get("priority_score"), 0.0), 4)

        payload = {
            "entity": entity,
            "trade_direction": direction,
            "trade_confidence": confidence,
            "priority_score": priority_score,
            "setup_family": row.get("setup_family"),
            "entry_style": row.get("entry_style"),
        }

        if direction in {"bullish", "strong_bullish"}:
            leaders.append(payload)

        elif direction in {"bearish", "strong_bearish"}:
            laggards.append(payload)

    # sort by priority first, then confidence
    leaders.sort(
        key=lambda x: (
            x.get("priority_score", 0.0),
            x.get("trade_confidence", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    laggards.sort(
        key=lambda x: (
            x.get("priority_score", 0.0),
            x.get("trade_confidence", 0.0),
            x.get("entity", ""),
        ),
        reverse=True,
    )

    # ---------------------------------------------------
    # BUILD FINAL STATE
    # ---------------------------------------------------

    trading_state = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "system": "ToknClaw",
        "module": "trading_state_engine",

        "market_state": build_market_state(
            regime_payload=regime_payload,
            volatility_payload=volatility_payload,
            market_structure_payload=market_structure_payload,
            cross_asset_payload=cross_asset_payload,
        ),

        "flow": build_flow(
            snapshot=snapshot,
            trade_rows=trade_rows,
            cross_asset_payload=cross_asset_payload,
        ),

        "momentum": {
            "trend_up_pct": momentum.get("trend_up_pct", 0.0),
            "trend_down_pct": momentum.get("trend_down_pct", 0.0),
            "explosive_count": momentum.get("explosive_count", 0),
            "fast_count": momentum.get("fast_count", 0),
            "broadcast_urgency": momentum.get("broadcast_urgency"),
            "vertical_priority": momentum.get("vertical_priority", []),
        },

        "structure": build_structure(market_structure_payload),

        "positioning": build_positioning(trade_rows, paper_trading_payload),

        # 🔴 FIXED OUTPUT
        "leaders": leaders[:15],
        "laggards": laggards[:15],

        "entity_state": build_entity_state(
            trade_rows=trade_rows,
            signal_velocity_payload=signal_velocity_payload,
            market_structure_payload=market_structure_payload,
        ),

        "chain_state": build_chain_state(snapshot),

        "portfolio_state": build_portfolio_state(paper_trading_payload),

        "extensions": build_extensions(snapshot),

        "source_manifest": build_source_manifest(snapshot, paper_trading_payload),
    }

    # ---------------------------------------------------
    # WRITE OUTPUT
    # ---------------------------------------------------

    if write_output:
        write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, trading_state)

    return trading_state

# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main() -> None:
    payload = build_trading_state()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
