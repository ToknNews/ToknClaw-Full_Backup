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
# MODULE: market_commentary_engine
# PURPOSE: Convert trading snapshot intelligence into human-readable market
#          commentary for UI, broadcast, and staged ToknNews media_view ingestion.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• read live ToknClaw trading intelligence outputs
• turn structured signals into broadcaster-style commentary
• emit cool, readable market insights for UI/UX
• emit staged media_view-compatible payloads for ToknNews ingestion
• support SMA / overextension commentary when enough price history exists
• remain additive and OpenClaw agent ready

Primary Config
--------------
/opt/toknclaw/config/market_commentary_engine.json

Primary Inputs
--------------
/opt/toknclaw/data/snapshots/latest_snapshot_trading.json
/opt/toknclaw/data/paper_trading_state.json
/opt/toknclaw/data/token_price_history.json

Primary Outputs
---------------
/opt/toknclaw/data/commentary/trading_commentary.json
/opt/toknclaw/data/commentary/media_view_staging.json

Important Note
--------------
The media_view output generated here is a staging payload intended to feed your
ToknNews-side media_view.json path after schema alignment on that server.
"""

from __future__ import annotations

# ---------------------------------------------------
# PROJECT ROOT BOOTSTRAP
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from signal_engine.runtime_config import load_config

# ---------------------------------------------------
# PATHS / CONFIG
# ---------------------------------------------------

CONFIG_FILE = "market_commentary_engine.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "max_insights": 25,
    "max_media_view_items": 25,
    "tracked_entities": [
        "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "LINK",
        "AVAX", "ARB", "OP", "INJ", "PYTH", "JUP", "RNDR"
    ],
    "min_commentary_confidence": 0.22,
    "strong_signal_confidence": 0.55,
    "short_sma_period": 20,
    "long_sma_period": 200,
    "overextension_pct_above_short_sma": 6.0,
    "overextension_pct_below_short_sma": -6.0,
    "emit_sma_commentary": True,
    "emit_overextension_commentary": True,
    "emit_position_summary": True,
    "emit_low_priority_sma_state": False,
    "paths": {
        "trading_snapshot": "/opt/toknclaw/data/snapshots/latest_snapshot_trading.json",
        "paper_trading_state": "/opt/toknclaw/data/paper_trading_state.json",
        "price_history": "/opt/toknclaw/data/token_price_history.json",
        "commentary_output": "/opt/toknclaw/data/commentary/trading_commentary.json",
        "media_view_staging_output": "/opt/toknclaw/data/commentary/media_view_staging.json"
    }
}

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return utc_now().isoformat()


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
    text = clean_text(value).lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[MARKET COMMENTARY] {message}")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)

    if not isinstance(cfg, dict):
        return deepcopy(DEFAULT_CONFIG)

    merged = deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)

    tracked = merged.get("tracked_entities")
    if not isinstance(tracked, list):
        merged["tracked_entities"] = deepcopy(DEFAULT_CONFIG["tracked_entities"])
    else:
        merged["tracked_entities"] = [clean_upper(x) for x in tracked if clean_text(x)]

    merged["paths"] = {
        **deepcopy(DEFAULT_CONFIG["paths"]),
        **safe_dict(merged.get("paths")),
    }

    return merged


def hash_id(prefix: str, entity: str, text: str) -> str:
    raw = f"{prefix}|{entity}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


# ---------------------------------------------------
# PRICE / SMA HELPERS
# ---------------------------------------------------

def latest_prices_by_entity(price_history: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    return safe_dict(price_history.get("tokens"))


def last_n_prices(price_rows: List[Dict[str, Any]], count: int) -> List[float]:
    valid = []
    for row in safe_list(price_rows):
        if not isinstance(row, dict):
            continue
        px = safe_float(row.get("price_usd"), 0.0)
        if px > 0:
            valid.append(px)
    return valid[-count:]


def simple_sma(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def current_and_previous_sma_state(price_rows: List[Dict[str, Any]], period: int) -> Dict[str, Any]:
    values = last_n_prices(price_rows, max(period + 1, period))
    if len(values) < period:
        return {
            "has_sma": False,
            "current_price": None,
            "current_sma": None,
            "previous_price": None,
            "previous_sma": None,
            "crossed_above": False,
            "crossed_below": False,
        }

    current_window = values[-period:]
    current_sma = simple_sma(current_window)
    current_price = values[-1]

    previous_price = None
    previous_sma = None
    crossed_above = False
    crossed_below = False

    if len(values) >= period + 1:
        previous_window = values[-(period + 1):-1]
        previous_sma = simple_sma(previous_window)
        previous_price = values[-2]

        if previous_sma is not None and current_sma is not None:
            crossed_above = previous_price <= previous_sma and current_price > current_sma
            crossed_below = previous_price >= previous_sma and current_price < current_sma

    return {
        "has_sma": True,
        "current_price": current_price,
        "current_sma": current_sma,
        "previous_price": previous_price,
        "previous_sma": previous_sma,
        "crossed_above": crossed_above,
        "crossed_below": crossed_below,
    }


# ---------------------------------------------------
# COMMENTARY RULES
# ---------------------------------------------------

def build_reason_set(row: Dict[str, Any]) -> set[str]:
    return {clean_text(x) for x in safe_list(row.get("reasons")) if clean_text(x)}


def commentary_from_trade_row(
    row: Dict[str, Any],
    cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    entity = clean_upper(row.get("entity"))
    confidence = safe_float(row.get("confidence"), 0.0)
    direction = clean_text(row.get("direction"))
    reasons = build_reason_set(row)

    insights: List[Dict[str, Any]] = []
    min_conf = safe_float(cfg.get("min_commentary_confidence", 0.22), 0.22)

    if confidence < min_conf:
        return insights

    if direction == "strong_bullish":
        if {"trend_bull", "oi_build_accel"} & reasons:
            text = f"{entity} showing strong continuation with aligned trend and positioning."
        elif "short_unwind" in reasons:
            text = f"{entity} looks like it is squeezing higher as shorts unwind."
        else:
            text = f"{entity} is one of the strongest upside setups on the board right now."

        insights.append({
            "id": hash_id("commentary", entity, text),
            "entity": entity,
            "type": "signal_confluence",
            "confidence": confidence,
            "signal_direction": direction,
            "text": text,
            "reasons": sorted(list(reasons)),
            "priority": 100,
        })

    elif direction == "bullish":
        if "trend_bull" in reasons:
            text = f"{entity} is leaning higher with trend support building underneath price."
        elif "oi_build_accel" in reasons:
            text = f"{entity} is seeing fresh positioning come in, suggesting upward pressure."
        elif "short_unwind" in reasons:
            text = f"{entity} is catching a bounce as shorts unwind."
        else:
            text = f"{entity} is starting to firm up after a constructive shift in flow."

        insights.append({
            "id": hash_id("commentary", entity, text),
            "entity": entity,
            "type": "signal_confluence",
            "confidence": confidence,
            "signal_direction": direction,
            "text": text,
            "reasons": sorted(list(reasons)),
            "priority": 95,
        })

    elif direction == "strong_bearish":
        if {"trend_bear", "oi_unwind_accel"} & reasons:
            text = f"{entity} is under heavy pressure as positioning and structure both point lower."
        elif "long_unwind" in reasons:
            text = f"{entity} looks vulnerable as longs continue to unwind."
        else:
            text = f"{entity} is one of the weakest downside setups in the current market mix."

        insights.append({
            "id": hash_id("commentary", entity, text),
            "entity": entity,
            "type": "signal_confluence",
            "confidence": confidence,
            "signal_direction": direction,
            "text": text,
            "reasons": sorted(list(reasons)),
            "priority": 100,
        })

    elif direction == "bearish":
        if "long_unwind" in reasons:
            text = f"{entity} is showing signs of long liquidation pressure."
        elif "trend_bear" in reasons:
            text = f"{entity} is trending lower with weak structure."
        elif "oi_unwind_accel" in reasons:
            text = f"{entity} is losing positioning support and could stay soft near term."
        else:
            text = f"{entity} is fading as positioning starts to unwind."

        insights.append({
            "id": hash_id("commentary", entity, text),
            "entity": entity,
            "type": "signal_confluence",
            "confidence": confidence,
            "signal_direction": direction,
            "text": text,
            "reasons": sorted(list(reasons)),
            "priority": 95,
        })

    if "high_oi" in reasons and confidence >= 0.30:
        text = f"{entity} has elevated open interest, increasing the chance of sharp moves."
        insights.append({
            "id": hash_id("commentary", entity, text),
            "entity": entity,
            "type": "oi_context",
            "confidence": 0.50,
            "signal_direction": direction,
            "text": text,
            "reasons": ["high_oi"],
            "priority": 55,
        })

    if "oi_divergence" in reasons and confidence >= 0.30:
        text = f"{entity} is showing positioning divergence, suggesting potential volatility."
        insights.append({
            "id": hash_id("commentary", entity, text),
            "entity": entity,
            "type": "divergence_context",
            "confidence": 0.50,
            "signal_direction": direction,
            "text": text,
            "reasons": ["oi_divergence"],
            "priority": 50,
        })

    return insights


def commentary_from_raw_signals(signal_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []

    for row in signal_rows:
        st = clean_text(row.get("signal_type"))
        entity = clean_upper(row.get("entity"))

        if st == "perp_open_interest_build_accelerating":
            text = f"{entity} seeing aggressive positioning build, suggesting continuation pressure."
            insights.append({
                "id": hash_id("raw", entity, text),
                "entity": entity,
                "type": "flow",
                "confidence": 0.65,
                "signal_direction": "bullish",
                "text": text,
                "reasons": ["oi_build_accel"],
                "priority": 90,
            })

        elif st == "perp_open_interest_unwind_accelerating":
            text = f"{entity} under pressure as positions unwind quickly."
            insights.append({
                "id": hash_id("raw", entity, text),
                "entity": entity,
                "type": "flow",
                "confidence": 0.65,
                "signal_direction": "bearish",
                "text": text,
                "reasons": ["oi_unwind_accel"],
                "priority": 90,
            })

        elif st == "perp_trend_bullish":
            text = f"{entity} pushing higher with trend and positioning aligned."
            insights.append({
                "id": hash_id("raw", entity, text),
                "entity": entity,
                "type": "trend",
                "confidence": 0.70,
                "signal_direction": "bullish",
                "text": text,
                "reasons": ["trend_bull"],
                "priority": 95,
            })

        elif st == "perp_trend_bearish":
            text = f"{entity} trending lower with sustained downside structure."
            insights.append({
                "id": hash_id("raw", entity, text),
                "entity": entity,
                "type": "trend",
                "confidence": 0.70,
                "signal_direction": "bearish",
                "text": text,
                "reasons": ["trend_bear"],
                "priority": 95,
            })

    return insights


def commentary_from_price_structure(
    entity: str,
    price_rows: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []

    emit_sma = safe_bool(cfg.get("emit_sma_commentary", True), True)
    emit_overextension = safe_bool(cfg.get("emit_overextension_commentary", True), True)
    emit_low_priority_sma_state = safe_bool(cfg.get("emit_low_priority_sma_state", False), False)

    short_period = safe_int(cfg.get("short_sma_period", 20), 20)
    long_period = safe_int(cfg.get("long_sma_period", 200), 200)
    over_above = safe_float(cfg.get("overextension_pct_above_short_sma", 6.0), 6.0)
    over_below = safe_float(cfg.get("overextension_pct_below_short_sma", -6.0), -6.0)

    short_state = current_and_previous_sma_state(price_rows, short_period)
    long_state = current_and_previous_sma_state(price_rows, long_period)

    if emit_sma and long_state.get("has_sma"):
        current_price = safe_float(long_state.get("current_price"), 0.0)
        current_sma = safe_float(long_state.get("current_sma"), 0.0)

        if current_price > 0 and current_sma > 0:
            if long_state.get("crossed_below"):
                text = f"{entity} just slipped below its {long_period} SMA, which is a clean warning sign for momentum."
                insights.append({
                    "id": hash_id("commentary", entity, text),
                    "entity": entity,
                    "type": "sma_break",
                    "confidence": 0.78,
                    "signal_direction": "bearish",
                    "text": text,
                    "reasons": [f"below_{long_period}_sma"],
                    "priority": 92,
                })
            elif long_state.get("crossed_above"):
                text = f"{entity} just reclaimed its {long_period} SMA, a constructive shift in longer-term structure."
                insights.append({
                    "id": hash_id("commentary", entity, text),
                    "entity": entity,
                    "type": "sma_break",
                    "confidence": 0.78,
                    "signal_direction": "bullish",
                    "text": text,
                    "reasons": [f"above_{long_period}_sma"],
                    "priority": 92,
                })
            elif emit_low_priority_sma_state:
                if current_price < current_sma:
                    text = f"{entity} is still trading below its {long_period} SMA and has not repaired that structural damage yet."
                    insights.append({
                        "id": hash_id("commentary", entity, text),
                        "entity": entity,
                        "type": "sma_state",
                        "confidence": 0.62,
                        "signal_direction": "bearish",
                        "text": text,
                        "reasons": [f"below_{long_period}_sma"],
                        "priority": 25,
                    })
                elif current_price > current_sma:
                    text = f"{entity} is holding above its {long_period} SMA, which keeps the broader structure constructive."
                    insights.append({
                        "id": hash_id("commentary", entity, text),
                        "entity": entity,
                        "type": "sma_state",
                        "confidence": 0.60,
                        "signal_direction": "bullish",
                        "text": text,
                        "reasons": [f"above_{long_period}_sma"],
                        "priority": 25,
                    })

    if emit_overextension and short_state.get("has_sma"):
        current_price = safe_float(short_state.get("current_price"), 0.0)
        current_sma = safe_float(short_state.get("current_sma"), 0.0)

        if current_price > 0 and current_sma > 0:
            dist_pct = ((current_price - current_sma) / current_sma) * 100.0

            if dist_pct >= over_above:
                text = f"{entity} is looking overextended above its short-term trend and may be vulnerable to a cool-off."
                insights.append({
                    "id": hash_id("commentary", entity, text),
                    "entity": entity,
                    "type": "overextension",
                    "confidence": 0.66,
                    "signal_direction": "bearish_watch",
                    "text": text,
                    "reasons": ["overbought_short_term"],
                    "priority": 70,
                })

            elif dist_pct <= over_below:
                text = f"{entity} is getting stretched below its short-term trend and could be setting up for a reflex bounce."
                insights.append({
                    "id": hash_id("commentary", entity, text),
                    "entity": entity,
                    "type": "overextension",
                    "confidence": 0.66,
                    "signal_direction": "bullish_watch",
                    "text": text,
                    "reasons": ["oversold_short_term"],
                    "priority": 70,
                })

    return insights


def commentary_from_positions(
    paper_state: Dict[str, Any],
    cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not safe_bool(cfg.get("emit_position_summary", True), True):
        return []

    open_positions = safe_dict(paper_state.get("open_positions"))
    if not open_positions:
        return []

    insights: List[Dict[str, Any]] = []

    for position in open_positions.values():
        if not isinstance(position, dict):
            continue

        entity = clean_upper(position.get("entity"))
        side = clean_text(position.get("side"))
        unrealized_pnl_pct = safe_float(position.get("unrealized_pnl_pct"), 0.0)

        if side == "long":
            if unrealized_pnl_pct >= 2.0:
                text = f"{entity} is working higher in the live model and that long is starting to get traction."
            elif unrealized_pnl_pct <= -2.0:
                text = f"{entity} is pushing against the live long and that setup is under pressure."
            else:
                continue
        elif side == "short":
            if unrealized_pnl_pct >= 2.0:
                text = f"{entity} is trading lower in the live model and that short is beginning to work."
            elif unrealized_pnl_pct <= -2.0:
                text = f"{entity} is squeezing against the live short and traders should watch for instability."
            else:
                continue
        else:
            continue

        insights.append({
            "id": hash_id("commentary", entity, text),
            "entity": entity,
            "type": "live_position_context",
            "confidence": 0.58,
            "signal_direction": side,
            "text": text,
            "reasons": ["live_position_context"],
            "priority": 40,
        })

    return insights


# ---------------------------------------------------
# AGGREGATION + SYNTHESIS
# ---------------------------------------------------

def aggregate_market_state(insights: List[Dict[str, Any]]) -> Dict[str, Any]:
    state = {
        "bullish": 0,
        "bearish": 0,
        "trend_bull": 0,
        "trend_bear": 0,
        "unwind": 0,
        "high_oi": 0,
        "above_200_sma": 0,
        "below_200_sma": 0,
        "overbought": 0,
        "oversold": 0,
    }

    for insight in insights:
        reasons = safe_list(insight.get("reasons"))
        direction = clean_text(insight.get("signal_direction"))

        if direction == "bullish":
            state["bullish"] += 1
        elif direction == "bearish":
            state["bearish"] += 1

        if "trend_bull" in reasons:
            state["trend_bull"] += 1
        if "trend_bear" in reasons:
            state["trend_bear"] += 1
        if "long_unwind" in reasons or "short_unwind" in reasons:
            state["unwind"] += 1
        if "high_oi" in reasons:
            state["high_oi"] += 1
        if any("above_200_sma" == r for r in reasons):
            state["above_200_sma"] += 1
        if any("below_200_sma" == r for r in reasons):
            state["below_200_sma"] += 1
        if "overbought_short_term" in reasons:
            state["overbought"] += 1
        if "oversold_short_term" in reasons:
            state["oversold"] += 1

    return state


def synthesize_market_insight(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []

    bullish = safe_int(state.get("bullish", 0), 0)
    bearish = safe_int(state.get("bearish", 0), 0)
    trend_bull = safe_int(state.get("trend_bull", 0), 0)
    trend_bear = safe_int(state.get("trend_bear", 0), 0)
    unwind = safe_int(state.get("unwind", 0), 0)
    overbought = safe_int(state.get("overbought", 0), 0)
    oversold = safe_int(state.get("oversold", 0), 0)

    if bearish > bullish and trend_bear >= trend_bull:
        text = "Market structure remains weak with downside pressure still leading across the board."
        direction = "bearish"
    elif bullish > bearish and trend_bull >= trend_bear:
        text = "Market is showing signs of strength as trend and positioning begin to align higher."
        direction = "bullish"
    elif unwind >= 3:
        text = "Market looks like it is in an unwind phase with positioning being reduced across multiple assets."
        direction = "neutral"
    else:
        text = "Market conditions remain mixed with no clear directional dominance."
        direction = "neutral"

    insights.append({
        "id": hash_id("synth", "MARKET", text),
        "entity": "MARKET",
        "type": "market_synthesis",
        "confidence": 0.85,
        "signal_direction": direction,
        "text": text,
        "reasons": ["market_structure"],
        "priority": 120,
    })

    if overbought >= 3:
        text = "Several assets are getting stretched above short-term trend, raising the odds of a cool-off."
        insights.append({
            "id": hash_id("synth", "MARKET", text),
            "entity": "MARKET",
            "type": "market_synthesis",
            "confidence": 0.72,
            "signal_direction": "bearish_watch",
            "text": text,
            "reasons": ["overbought_cluster"],
            "priority": 110,
        })

    if oversold >= 3:
        text = "A pocket of the market is getting washed out below short-term trend and may be setting up for reflex bounces."
        insights.append({
            "id": hash_id("synth", "MARKET", text),
            "entity": "MARKET",
            "type": "market_synthesis",
            "confidence": 0.72,
            "signal_direction": "bullish_watch",
            "text": text,
            "reasons": ["oversold_cluster"],
            "priority": 110,
        })

    return insights


# ---------------------------------------------------
# OUTPUT BUILDERS
# ---------------------------------------------------

def dedupe_and_rank_insights(insights: List[Dict[str, Any]], max_items: int) -> List[Dict[str, Any]]:
    seen = set()
    out = []

    for row in sorted(
        [x for x in insights if isinstance(x, dict)],
        key=lambda x: (
            safe_int(x.get("priority", 0), 0),
            safe_float(x.get("confidence", 0.0), 0.0)
        ),
        reverse=True,
    ):
        key = (clean_upper(row.get("entity")), clean_text(row.get("text")))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)

        if len(out) >= max_items:
            break

    return out


def build_commentary_payload(
    trading_snapshot: Dict[str, Any],
    paper_state: Dict[str, Any],
    price_history: Dict[str, Any],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    tracked = set(cfg.get("tracked_entities", []))
    max_insights = safe_int(cfg.get("max_insights", 25), 25)

    trade_rows = safe_list(safe_dict(trading_snapshot.get("trade_signals")).get("rows"))
    price_tokens = latest_prices_by_entity(price_history)

    insights: List[Dict[str, Any]] = []

    raw_signals = safe_list(trading_snapshot.get("signals"))
    insights.extend(commentary_from_raw_signals(raw_signals))

    for row in trade_rows:
        if not isinstance(row, dict):
            continue

        entity = clean_upper(row.get("entity"))
        if tracked and entity not in tracked:
            continue

        insights.extend(commentary_from_trade_row(row, cfg))

        price_rows = safe_list(price_tokens.get(entity))
        if price_rows:
            insights.extend(commentary_from_price_structure(entity, price_rows, cfg))

    insights.extend(commentary_from_positions(paper_state, cfg))

    market_state = aggregate_market_state(insights)
    insights.extend(synthesize_market_insight(market_state))

    final_insights = dedupe_and_rank_insights(insights, max_insights)

    market_context = safe_dict(trading_snapshot.get("market_context"))
    portfolio = safe_dict(paper_state.get("portfolio"))

    return {
        "generated_at": now_iso(),
        "source": "toknclaw_market_commentary_engine",
        "market_state": market_state,
        "insights": final_insights,
        "summary": {
            "insight_count": len(final_insights),
            "open_position_count": safe_int(portfolio.get("open_position_count", 0), 0),
            "equity_usd": safe_float(portfolio.get("equity_usd", 0.0), 0.0),
            "trade_signal_summary": safe_dict(safe_dict(trading_snapshot.get("trade_signals")).get("summary")),
            "market_context_summary": {
                "tradable_assets": safe_list(market_context.get("tradable_assets")),
                "paper_trade_only_assets": safe_list(market_context.get("paper_trade_only_assets")),
            },
        },
    }


def build_media_view_staging_payload(
    commentary_payload: Dict[str, Any],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    max_items = safe_int(cfg.get("max_media_view_items", 25), 25)
    insights = safe_list(commentary_payload.get("insights"))[:max_items]

    items = []
    for row in insights:
        if not isinstance(row, dict):
            continue

        entity = clean_upper(row.get("entity"))
        text = clean_text(row.get("text"))
        confidence = safe_float(row.get("confidence", 0.0), 0.0)
        insight_type = clean_text(row.get("type"))

        items.append({
            "id": hash_id("media_view", entity, text),
            "kind": "market_commentary",
            "source": "toknclaw_commentary_engine",
            "entity": entity,
            "headline": text,
            "summary": text,
            "confidence": confidence,
            "category": "trading_intelligence",
            "tags": [insight_type] + safe_list(row.get("reasons")),
            "metadata": {
                "signal_direction": clean_text(row.get("signal_direction")),
                "priority": safe_int(row.get("priority", 0), 0),
                "commentary_type": insight_type,
            },
            "generated_at": commentary_payload.get("generated_at"),
        })

    return {
        "generated_at": commentary_payload.get("generated_at"),
        "source": "toknclaw_market_commentary_engine",
        "mode": "staging_for_toknnews_media_view",
        "items": items,
        "market_state": safe_dict(commentary_payload.get("market_state")),
        "notes": {
            "purpose": "Staged commentary feed for ToknNews media_view.json entrypoint mapping.",
            "requires_toknnews_schema_alignment": True
        }
    }


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

def run_market_commentary_engine() -> Dict[str, Any]:
    cfg = load_engine_config()

    if not bool(cfg.get("enabled", True)):
        return {
            "status": "disabled",
            "generated_at": now_iso(),
        }

    paths = safe_dict(cfg.get("paths"))

    trading_snapshot = safe_dict(read_json(Path(clean_text(paths.get("trading_snapshot"))), {}))
    paper_state = safe_dict(read_json(Path(clean_text(paths.get("paper_trading_state"))), {}))
    price_history = safe_dict(read_json(Path(clean_text(paths.get("price_history"))), {}))

    commentary_payload = build_commentary_payload(
        trading_snapshot=trading_snapshot,
        paper_state=paper_state,
        price_history=price_history,
        cfg=cfg,
    )

    media_view_payload = build_media_view_staging_payload(
        commentary_payload=commentary_payload,
        cfg=cfg,
    )

    commentary_output_path = Path(clean_text(paths.get("commentary_output")))
    media_view_output_path = Path(clean_text(paths.get("media_view_staging_output")))

    write_json_atomic(commentary_output_path, commentary_payload)
    write_json_atomic(media_view_output_path, media_view_payload)

    debug_log(
        cfg,
        f"insights={len(safe_list(commentary_payload.get('insights')))} "
        f"media_view_items={len(safe_list(media_view_payload.get('items')))}"
    )

    print("[MARKET COMMENTARY] complete")
    print(f"[MARKET COMMENTARY] commentary_output={commentary_output_path}")
    print(f"[MARKET COMMENTARY] media_view_staging_output={media_view_output_path}")

    return {
        "status": "ok",
        "generated_at": commentary_payload.get("generated_at"),
        "commentary_output": str(commentary_output_path),
        "media_view_staging_output": str(media_view_output_path),
        "insight_count": len(safe_list(commentary_payload.get("insights"))),
    }


def main() -> None:
    run_market_commentary_engine()


if __name__ == "__main__":
    main()
