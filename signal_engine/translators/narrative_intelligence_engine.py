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
# MODULE: narrative_intelligence_engine
# PURPOSE: Convert ToknClaw trading intelligence into structured narrative
#          state for downstream broadcast, pipeline, and ToknNews media_view use.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• read live ToknClaw trading intelligence outputs
• convert multi-factor signals into structured narrative state
• emit market, entity, and cluster-level intelligence
• generate machine-readable narrative hooks for broadcast pipelines
• stage narrative intelligence for ToknNews media_view ingestion
• remain additive and OpenClaw agent ready

Primary Config
--------------
/opt/toknclaw/config/narrative_intelligence_engine.json

Primary Inputs
--------------
/opt/toknclaw/data/snapshots/latest_snapshot_trading.json
/opt/toknclaw/data/paper_trading_state.json
/opt/toknclaw/data/token_price_history.json

Primary Outputs
---------------
/opt/toknclaw/data/commentary/narrative_intelligence.json
/opt/toknclaw/data/commentary/media_view_staging.json
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

CONFIG_FILE = "narrative_intelligence_engine.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "tracked_entities": [
        "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "LINK",
        "AVAX", "ARB", "OP", "INJ", "PYTH", "JUP", "RNDR"
    ],
    "short_sma_period": 20,
    "long_sma_period": 200,
    "max_entities": 50,
    "max_hooks": 50,
    "paths": {
        "trading_snapshot": "/opt/toknclaw/data/snapshots/latest_snapshot_trading.json",
        "paper_trading_state": "/opt/toknclaw/data/paper_trading_state.json",
        "price_history": "/opt/toknclaw/data/token_price_history.json",
        "narrative_output": "/opt/toknclaw/data/commentary/narrative_intelligence.json",
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
        print(f"[NARRATIVE INTEL] {message}")


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


def sma_state(price_rows: List[Dict[str, Any]], period: int) -> Dict[str, Any]:
    values = last_n_prices(price_rows, max(period + 1, period))
    if len(values) < period:
        return {
            "has_sma": False,
            "current_price": None,
            "current_sma": None,
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
        "crossed_above": crossed_above,
        "crossed_below": crossed_below,
    }


# ---------------------------------------------------
# SIGNAL NORMALIZATION
# ---------------------------------------------------

def signals_by_entity(snapshot: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    for row in safe_list(snapshot.get("signals")):
        if not isinstance(row, dict):
            continue
        entity = clean_upper(row.get("entity"))
        if not entity or entity == "PERP_TREND":
            continue
        out.setdefault(entity, []).append(row)

    return out


def trade_rows_by_entity(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}

    trade_rows = safe_list(safe_dict(snapshot.get("trade_signals")).get("rows"))
    for row in trade_rows:
        if not isinstance(row, dict):
            continue
        entity = clean_upper(row.get("entity"))
        if not entity:
            continue
        out[entity] = row

    return out


def reason_set(row: Dict[str, Any]) -> set[str]:
    return {clean_text(x) for x in safe_list(row.get("reasons")) if clean_text(x)}


# ---------------------------------------------------
# NARRATIVE STATE BUILDERS
# ---------------------------------------------------

def infer_structure(price_rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Any]:
    short_period = safe_int(cfg.get("short_sma_period", 20), 20)
    long_period = safe_int(cfg.get("long_sma_period", 200), 200)

    short_state = sma_state(price_rows, short_period)
    long_state = sma_state(price_rows, long_period)

    structure = "unknown"

    if long_state.get("has_sma"):
        current_price = safe_float(long_state.get("current_price"), 0.0)
        current_sma = safe_float(long_state.get("current_sma"), 0.0)

        if current_price > 0 and current_sma > 0:
            if long_state.get("crossed_above"):
                structure = f"reclaimed_{long_period}_sma"
            elif long_state.get("crossed_below"):
                structure = f"lost_{long_period}_sma"
            elif current_price > current_sma:
                structure = f"above_{long_period}_sma"
            else:
                structure = f"below_{long_period}_sma"

    short_extension = "normal"
    if short_state.get("has_sma"):
        current_price = safe_float(short_state.get("current_price"), 0.0)
        current_sma = safe_float(short_state.get("current_sma"), 0.0)

        if current_price > 0 and current_sma > 0:
            dist_pct = ((current_price - current_sma) / current_sma) * 100.0
            if dist_pct >= 6.0:
                short_extension = "overbought"
            elif dist_pct <= -6.0:
                short_extension = "oversold"

    return {
        "structure": structure,
        "extension": short_extension,
        "short_sma_state": short_state,
        "long_sma_state": long_state,
    }


def infer_phase(
    direction: str,
    reasons: set[str],
    structure: str,
    extension: str,
) -> str:
    if direction in {"strong_bullish", "bullish"}:
        if "oi_build_accel" in reasons or "trend_bull" in reasons:
            return "continuation"
        if extension == "oversold":
            return "recovery"
        if structure.startswith("above_"):
            return "accumulation"
        return "constructive"

    if direction in {"strong_bearish", "bearish"}:
        if "long_unwind" in reasons or "oi_unwind_accel" in reasons:
            return "distribution"
        if extension == "overbought":
            return "exhaustion"
        if structure.startswith("below_"):
            return "breakdown"
        return "deteriorating"

    if extension == "overbought":
        return "overextended"
    if extension == "oversold":
        return "washed_out"

    return "mixed"


def build_entity_state(
    entity: str,
    trade_row: Dict[str, Any],
    raw_signal_rows: List[Dict[str, Any]],
    price_rows: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    direction = clean_text(trade_row.get("direction", "neutral"))
    confidence = safe_float(trade_row.get("confidence", 0.0), 0.0)
    reasons = reason_set(trade_row)

    for signal in raw_signal_rows:
        st = clean_text(signal.get("signal_type"))
        if st == "perp_trend_bullish":
            reasons.add("trend_bull")
        elif st == "perp_trend_bearish":
            reasons.add("trend_bear")
        elif st == "perp_open_interest_build_accelerating":
            reasons.add("oi_build_accel")
        elif st == "perp_open_interest_unwind_accelerating":
            reasons.add("oi_unwind_accel")

    structure_info = infer_structure(price_rows, cfg)
    structure = clean_text(structure_info.get("structure"))
    extension = clean_text(structure_info.get("extension"))
    phase = infer_phase(direction, reasons, structure, extension)

    flow = "mixed"
    if "oi_build_accel" in reasons:
        flow = "build_acceleration"
    elif "oi_unwind_accel" in reasons or "long_unwind" in reasons:
        flow = "unwind"
    elif "short_unwind" in reasons:
        flow = "short_unwind"

    positioning = []
    if "high_oi" in reasons:
        positioning.append("high_oi")
    if "oi_divergence" in reasons:
        positioning.append("oi_divergence")
    if "funding_negative" in reasons:
        positioning.append("funding_negative")
    if "funding_divergence" in reasons:
        positioning.append("funding_divergence")

    hooks: List[Dict[str, Any]] = []

    if direction in {"strong_bullish", "bullish"}:
        if structure in {"above_200_sma", "reclaimed_200_sma"}:
            text = f"{entity} is leaning higher with structure and positioning starting to align."
        elif extension == "oversold":
            text = f"{entity} looks like a recovery candidate after getting stretched lower."
        else:
            text = f"{entity} is firming up on improving flow."
        hooks.append({
            "id": hash_id("hook", entity, text),
            "entity": entity,
            "hook_type": "directional",
            "priority": 100 if direction == "strong_bullish" else 90,
            "text": text,
        })

    elif direction in {"strong_bearish", "bearish"}:
        if "long_unwind" in reasons:
            text = f"{entity} is showing signs of long liquidation pressure."
        elif structure in {"below_200_sma", "lost_200_sma"}:
            text = f"{entity} is losing structure and still trading below long-term trend."
        else:
            text = f"{entity} is fading as positioning starts to unwind."
        hooks.append({
            "id": hash_id("hook", entity, text),
            "entity": entity,
            "hook_type": "directional",
            "priority": 100 if direction == "strong_bearish" else 90,
            "text": text,
        })

    if structure == "lost_200_sma":
        text = f"{entity} just slipped below its 200 SMA, a meaningful structural warning."
        hooks.append({
            "id": hash_id("hook", entity, text),
            "entity": entity,
            "hook_type": "structure_break",
            "priority": 88,
            "text": text,
        })
    elif structure == "reclaimed_200_sma":
        text = f"{entity} just reclaimed its 200 SMA, improving the broader setup."
        hooks.append({
            "id": hash_id("hook", entity, text),
            "entity": entity,
            "hook_type": "structure_reclaim",
            "priority": 88,
            "text": text,
        })

    if extension == "overbought":
        text = f"{entity} is starting to look overextended above short-term trend."
        hooks.append({
            "id": hash_id("hook", entity, text),
            "entity": entity,
            "hook_type": "extension",
            "priority": 70,
            "text": text,
        })
    elif extension == "oversold":
        text = f"{entity} is getting stretched below short-term trend and may be setting up for a reflex move."
        hooks.append({
            "id": hash_id("hook", entity, text),
            "entity": entity,
            "hook_type": "extension",
            "priority": 70,
            "text": text,
        })

    return {
        "entity": entity,
        "direction": direction,
        "confidence": confidence,
        "phase": phase,
        "structure": structure,
        "extension": extension,
        "flow": flow,
        "positioning": positioning,
        "reasons": sorted(list(reasons)),
        "score_breakdown": safe_dict(trade_row.get("score_breakdown")),
        "signal_count": safe_int(trade_row.get("signal_count", 0), 0),
        "hooks": hooks,
    }


def build_market_state(entity_states: List[Dict[str, Any]]) -> Dict[str, Any]:
    bullish = 0
    bearish = 0
    continuation = 0
    distribution = 0
    overbought = 0
    oversold = 0

    for state in entity_states:
        direction = clean_text(state.get("direction"))
        phase = clean_text(state.get("phase"))
        extension = clean_text(state.get("extension"))

        if direction in {"bullish", "strong_bullish"}:
            bullish += 1
        elif direction in {"bearish", "strong_bearish"}:
            bearish += 1

        if phase in {"continuation", "accumulation", "constructive"}:
            continuation += 1
        if phase in {"distribution", "breakdown", "deteriorating"}:
            distribution += 1

        if extension == "overbought":
            overbought += 1
        elif extension == "oversold":
            oversold += 1

    regime = "mixed"
    bias = "neutral"

    if bearish > bullish and distribution >= continuation:
        regime = "risk_off"
        bias = "bearish"
    elif bullish > bearish and continuation >= distribution:
        regime = "risk_on"
        bias = "bullish"
    elif overbought >= 3:
        regime = "late_extension"
    elif oversold >= 3:
        regime = "washout"

    return {
        "regime": regime,
        "bias": bias,
        "bullish_entities": bullish,
        "bearish_entities": bearish,
        "continuation_entities": continuation,
        "distribution_entities": distribution,
        "overbought_entities": overbought,
        "oversold_entities": oversold,
    }


def build_cluster_candidates(entity_states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clusters = {
        "bullish_continuation": [],
        "bearish_distribution": [],
        "overextended": [],
        "washed_out": [],
    }

    for state in entity_states:
        entity = clean_upper(state.get("entity"))
        direction = clean_text(state.get("direction"))
        phase = clean_text(state.get("phase"))
        extension = clean_text(state.get("extension"))

        if direction in {"bullish", "strong_bullish"} and phase in {"continuation", "accumulation", "constructive"}:
            clusters["bullish_continuation"].append(entity)

        if direction in {"bearish", "strong_bearish"} and phase in {"distribution", "breakdown", "deteriorating"}:
            clusters["bearish_distribution"].append(entity)

        if extension == "overbought":
            clusters["overextended"].append(entity)

        if extension == "oversold":
            clusters["washed_out"].append(entity)

    out = []
    for name, members in clusters.items():
        if not members:
            continue
        out.append({
            "cluster": name,
            "members": sorted(members),
            "count": len(members),
        })

    return out


def flatten_hooks(entity_states: List[Dict[str, Any]], market_state: Dict[str, Any], max_hooks: int) -> List[Dict[str, Any]]:
    hooks: List[Dict[str, Any]] = []

    regime = clean_text(market_state.get("regime"))
    bias = clean_text(market_state.get("bias"))

    if regime == "risk_off":
        text = "Broader market posture is still risk-off with downside structure leading."
        hooks.append({
            "id": hash_id("market_hook", "MARKET", text),
            "entity": "MARKET",
            "hook_type": "market_regime",
            "priority": 130,
            "text": text,
        })
    elif regime == "risk_on":
        text = "Broader market posture is turning constructive with more assets aligning higher."
        hooks.append({
            "id": hash_id("market_hook", "MARKET", text),
            "entity": "MARKET",
            "hook_type": "market_regime",
            "priority": 130,
            "text": text,
        })
    elif regime == "late_extension":
        text = "Parts of the market are getting extended, which raises the odds of cooling momentum."
        hooks.append({
            "id": hash_id("market_hook", "MARKET", text),
            "entity": "MARKET",
            "hook_type": "market_regime",
            "priority": 125,
            "text": text,
        })
    elif regime == "washout":
        text = "A washed-out pocket is forming across the board and could create reflex bounce conditions."
        hooks.append({
            "id": hash_id("market_hook", "MARKET", text),
            "entity": "MARKET",
            "hook_type": "market_regime",
            "priority": 125,
            "text": text,
        })
    elif bias == "neutral":
        text = "Market posture remains mixed without a dominant directional regime."
        hooks.append({
            "id": hash_id("market_hook", "MARKET", text),
            "entity": "MARKET",
            "hook_type": "market_regime",
            "priority": 120,
            "text": text,
        })

    for state in entity_states:
        for hook in safe_list(state.get("hooks")):
            if isinstance(hook, dict):
                hooks.append(hook)

    hooks.sort(key=lambda x: (safe_int(x.get("priority", 0), 0), clean_text(x.get("entity"))), reverse=True)

    seen = set()
    out = []
    for hook in hooks:
        key = (clean_text(hook.get("entity")), clean_text(hook.get("text")))
        if key in seen:
            continue
        seen.add(key)
        out.append(hook)
        if len(out) >= max_hooks:
            break

    return out


# ---------------------------------------------------
# MEDIA VIEW STAGING
# ---------------------------------------------------

def build_media_view_staging_payload(narrative_payload: Dict[str, Any]) -> Dict[str, Any]:
    items = []

    for hook in safe_list(narrative_payload.get("narrative_hooks")):
        if not isinstance(hook, dict):
            continue

        entity = clean_upper(hook.get("entity"))
        text = clean_text(hook.get("text"))
        hook_type = clean_text(hook.get("hook_type"))

        items.append({
            "id": hash_id("media_view", entity, text),
            "kind": "narrative_intelligence",
            "source": "toknclaw_narrative_intelligence_engine",
            "entity": entity,
            "headline": text,
            "summary": text,
            "confidence": 0.75,
            "category": "trading_narrative_state",
            "tags": [hook_type],
            "metadata": {
                "hook_type": hook_type,
                "priority": safe_int(hook.get("priority", 0), 0),
            },
            "generated_at": narrative_payload.get("generated_at"),
        })

    return {
        "generated_at": narrative_payload.get("generated_at"),
        "source": "toknclaw_narrative_intelligence_engine",
        "mode": "staging_for_toknnews_media_view",
        "items": items,
        "market_state": safe_dict(narrative_payload.get("market_state")),
        "cluster_candidates": safe_list(narrative_payload.get("cluster_candidates")),
        "notes": {
            "purpose": "Structured narrative intelligence feed for ToknNews media_view.json entrypoint mapping.",
            "requires_toknnews_schema_alignment": True
        }
    }


# ---------------------------------------------------
# MAIN BUILDERS
# ---------------------------------------------------

def build_narrative_payload(
    trading_snapshot: Dict[str, Any],
    paper_state: Dict[str, Any],
    price_history: Dict[str, Any],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    tracked = set(cfg.get("tracked_entities", []))
    max_entities = safe_int(cfg.get("max_entities", 50), 50)
    max_hooks = safe_int(cfg.get("max_hooks", 50), 50)

    signal_rows_map = signals_by_entity(trading_snapshot)
    trade_rows_map = trade_rows_by_entity(trading_snapshot)
    price_tokens = latest_prices_by_entity(price_history)

    entity_states: List[Dict[str, Any]] = []

    for entity, trade_row in trade_rows_map.items():
        if tracked and entity not in tracked:
            continue

        raw_signal_rows = safe_list(signal_rows_map.get(entity))
        price_rows = safe_list(price_tokens.get(entity))

        entity_state = build_entity_state(
            entity=entity,
            trade_row=trade_row,
            raw_signal_rows=raw_signal_rows,
            price_rows=price_rows,
            cfg=cfg,
        )
        entity_states.append(entity_state)

    entity_states.sort(
        key=lambda x: (
            safe_float(x.get("confidence", 0.0), 0.0),
            safe_int(x.get("signal_count", 0), 0)
        ),
        reverse=True,
    )
    entity_states = entity_states[:max_entities]

    market_state = build_market_state(entity_states)
    cluster_candidates = build_cluster_candidates(entity_states)
    narrative_hooks = flatten_hooks(entity_states, market_state, max_hooks)

    portfolio = safe_dict(paper_state.get("portfolio"))

    return {
        "generated_at": now_iso(),
        "source": "toknclaw_narrative_intelligence_engine",
        "market_state": market_state,
        "entity_states": entity_states,
        "cluster_candidates": cluster_candidates,
        "narrative_hooks": narrative_hooks,
        "summary": {
            "entity_count": len(entity_states),
            "cluster_count": len(cluster_candidates),
            "hook_count": len(narrative_hooks),
            "open_position_count": safe_int(portfolio.get("open_position_count", 0), 0),
            "equity_usd": safe_float(portfolio.get("equity_usd", 0.0), 0.0),
        },
    }


def run_narrative_intelligence_engine() -> Dict[str, Any]:
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

    narrative_payload = build_narrative_payload(
        trading_snapshot=trading_snapshot,
        paper_state=paper_state,
        price_history=price_history,
        cfg=cfg,
    )

    media_view_payload = build_media_view_staging_payload(narrative_payload)

    narrative_output_path = Path(clean_text(paths.get("narrative_output")))
    media_view_output_path = Path(clean_text(paths.get("media_view_staging_output")))

    write_json_atomic(narrative_output_path, narrative_payload)
    write_json_atomic(media_view_output_path, media_view_payload)

    debug_log(
        cfg,
        f"entity_states={len(safe_list(narrative_payload.get('entity_states')))} "
        f"hooks={len(safe_list(narrative_payload.get('narrative_hooks')))} "
        f"media_view_items={len(safe_list(media_view_payload.get('items')))}"
    )

    print("[NARRATIVE INTEL] complete")
    print(f"[NARRATIVE INTEL] narrative_output={narrative_output_path}")
    print(f"[NARRATIVE INTEL] media_view_staging_output={media_view_output_path}")

    return {
        "status": "ok",
        "generated_at": narrative_payload.get("generated_at"),
        "narrative_output": str(narrative_output_path),
        "media_view_staging_output": str(media_view_output_path),
        "entity_count": len(safe_list(narrative_payload.get("entity_states"))),
        "hook_count": len(safe_list(narrative_payload.get("narrative_hooks"))),
    }


def main() -> None:
    run_narrative_intelligence_engine()


if __name__ == "__main__":
    main()
