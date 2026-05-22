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
# MODULE: liquidation_engine
# PURPOSE: Infer liquidation / squeeze stress conditions from existing funding,
#          open-interest, OI change, and strategy-watch signals using trading
#          loop inputs first and signal-lake fallback second.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This collector is designed to:
• consume funding, OI, OI change, and perp strategy-watch signals
• support direct trading-loop signal overrides for the fast PM2 pipeline
• infer long-liquidation / short-liquidation stress conditions
• emit squeeze-confirmation and unwind-risk signals
• remain additive and OpenClaw agent ready
• prioritize trading utility over broadcast niceties

Primary Config
--------------
/opt/toknclaw/config/liquidation_engine.json

Primary Inputs
--------------
• trading loop in-memory signal rows (preferred)
• /opt/toknclaw/data/signal_lake.json (fallback)

Primary Outputs
---------------
• perp_liquidation_risk_long_flush
• perp_liquidation_risk_short_flush
• perp_squeeze_confirmation_bullish
• perp_squeeze_confirmation_bearish
• perp_liquidation_stress_summary

Notes
-----
This is a no-key forced-flow proxy engine.
It does NOT claim to be a direct exchange liquidation tape.
If you later add Coinglass or another liquidation feed, this module can be
extended without refactoring downstream modules.
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

import ast
import re
import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

from signal_engine.collectors.registry import register_collector
from signal_engine.models.signal import Signal
from signal_engine.runtime_config import load_config
from signal_engine.signal_lake import load_signal_lake

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

CONFIG_FILE = "liquidation_engine.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "lookback_signal_count": 5000,
    "tracked_entities": [
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
        "RNDR",
    ],
    "require_tracked_entity": True,
    # relaxed to match real perp markets observed in your logs
    "positive_funding_threshold": 0.00005,
    "negative_funding_threshold": -0.00005,
    # relaxed rank floor for a 14-name tradable universe
    "oi_rank_min": 0.40,
    "oi_rank_strong": 0.80,
    "oi_change_rising_threshold_pct": 1.50,
    "oi_change_falling_threshold_pct": -1.50,
    "oi_change_strong_rising_threshold_pct": 4.00,
    "oi_change_strong_falling_threshold_pct": -4.00,
    # soft activation for muted-funding but crowded positioning regimes
    "soft_oi_rank_trigger_pct": 0.70,
    "soft_oi_change_trigger_pct": 1.00,
    "max_signals_per_run": 60,
    "max_summary_rows": 6,
    "confidence_base": 0.72,
    "confidence_bonus_strong_oi": 0.08,
    "confidence_bonus_strong_change": 0.08,
    "confidence_bonus_strategy_alignment": 0.08,
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


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[LIQUIDATION ENGINE] {message}")


def info_log(message: str) -> None:
    print(f"[LIQUIDATION ENGINE] {message}")


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

    return merged


def object_rows_only(rows: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in rows or []:
        if isinstance(row, dict):
            out.append(row)

    return out


def latest_rows_by_type_entity(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for row in rows:
        signal_type = clean_text(row.get("signal_type"))
        entity = clean_upper(row.get("entity"))

        if not signal_type or not entity:
            continue

        out[(signal_type, entity)] = row

    return out


def parse_summary_number(summary: str, key: str) -> float:
    summary = clean_text(summary)
    pattern = rf"{re.escape(key)}=([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"
    match = re.search(pattern, summary)

    if not match:
        return 0.0

    return safe_float(match.group(1), 0.0)


def parse_summary_dict(summary: str, key: str) -> Dict[str, float]:
    summary = clean_text(summary)
    pattern = rf"{re.escape(key)}=(\{{.*\}})"
    match = re.search(pattern, summary)

    if not match:
        return {}

    raw = match.group(1)

    try:
        parsed = ast.literal_eval(raw)
        if not isinstance(parsed, dict):
            return {}
        return {clean_text(k): safe_float(v, 0.0) for k, v in parsed.items()}
    except Exception:
        return {}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

# ---------------------------------------------------
# SIGNAL PARSERS
# ---------------------------------------------------

def funding_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    summary = clean_text(row.get("summary"))

    return {
        "entity": clean_upper(row.get("entity")),
        "avg_funding": parse_summary_number(summary, "avg"),
        "venues": parse_summary_dict(summary, "venues"),
    }


def oi_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    summary = clean_text(row.get("summary"))

    return {
        "entity": clean_upper(row.get("entity")),
        "avg_oi": parse_summary_number(summary, "avg_oi"),
        "venues": parse_summary_dict(summary, "venues"),
    }


def oi_change_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    summary = clean_text(row.get("summary"))

    return {
        "entity": clean_upper(row.get("entity")),
        "oi_change_pct": parse_summary_number(summary, "oi_change_pct"),
        "current_oi": parse_summary_number(summary, "current_oi"),
        "previous_oi": parse_summary_number(summary, "previous_oi"),
        "venues": parse_summary_dict(summary, "venues"),
    }

# ---------------------------------------------------
# SIGNAL BUILDERS
# ---------------------------------------------------

def build_long_flush_risk_signal(
    entity: str,
    funding: float,
    avg_oi: float,
    oi_rank_pct: float,
    oi_change_pct: float,
    confidence: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_liquidation_risk_long_flush",
        entity=entity,
        title=f"{entity} long-flush liquidation risk",
        summary=(
            f"{entity} shows long-flush liquidation risk | "
            f"funding={funding:.6f} | "
            f"avg_oi={avg_oi:.2f} | "
            f"oi_rank_pct={oi_rank_pct:.2%} | "
            f"oi_change_pct={oi_change_pct:.4f}"
        ),
        confidence=confidence,
        sentiment_score=-0.28,
        raw_url=None,
    )


def build_short_flush_risk_signal(
    entity: str,
    funding: float,
    avg_oi: float,
    oi_rank_pct: float,
    oi_change_pct: float,
    confidence: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_liquidation_risk_short_flush",
        entity=entity,
        title=f"{entity} short-flush liquidation risk",
        summary=(
            f"{entity} shows short-flush liquidation risk | "
            f"funding={funding:.6f} | "
            f"avg_oi={avg_oi:.2f} | "
            f"oi_rank_pct={oi_rank_pct:.2%} | "
            f"oi_change_pct={oi_change_pct:.4f}"
        ),
        confidence=confidence,
        sentiment_score=0.28,
        raw_url=None,
    )


def build_bullish_squeeze_confirmation_signal(
    entity: str,
    funding: float,
    avg_oi: float,
    oi_rank_pct: float,
    oi_change_pct: float,
    confidence: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_squeeze_confirmation_bullish",
        entity=entity,
        title=f"{entity} bullish squeeze confirmation",
        summary=(
            f"{entity} shows bullish squeeze confirmation | "
            f"crowded shorts + elevated OI + expanding positioning | "
            f"funding={funding:.6f} | avg_oi={avg_oi:.2f} | "
            f"oi_rank_pct={oi_rank_pct:.2%} | oi_change_pct={oi_change_pct:.4f}"
        ),
        confidence=confidence,
        sentiment_score=0.36,
        raw_url=None,
    )


def build_bearish_squeeze_confirmation_signal(
    entity: str,
    funding: float,
    avg_oi: float,
    oi_rank_pct: float,
    oi_change_pct: float,
    confidence: float,
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_squeeze_confirmation_bearish",
        entity=entity,
        title=f"{entity} bearish squeeze confirmation",
        summary=(
            f"{entity} shows bearish squeeze confirmation | "
            f"crowded longs + elevated OI + expanding positioning | "
            f"funding={funding:.6f} | avg_oi={avg_oi:.2f} | "
            f"oi_rank_pct={oi_rank_pct:.2%} | oi_change_pct={oi_change_pct:.4f}"
        ),
        confidence=confidence,
        sentiment_score=-0.36,
        raw_url=None,
    )


def build_summary_signal(
    total_entities: int,
    long_flush_risk: int,
    short_flush_risk: int,
    bullish_confirmations: int,
    bearish_confirmations: int,
    top_rows: List[str],
) -> Signal:
    return Signal(
        timestamp=utc_now(),
        source="toknclaw",
        signal_type="perp_liquidation_stress_summary",
        entity="PERP_LIQUIDATION",
        title="Perpetual liquidation stress summary",
        summary=(
            f"entities={total_entities} | "
            f"long_flush_risk={long_flush_risk} | "
            f"short_flush_risk={short_flush_risk} | "
            f"bullish_confirmations={bullish_confirmations} | "
            f"bearish_confirmations={bearish_confirmations} | "
            f"top={', '.join(top_rows) if top_rows else 'none'}"
        ),
        confidence=0.84,
        sentiment_score=0.0,
        raw_url=None,
    )

# ---------------------------------------------------
# CORE
# ---------------------------------------------------

def build_entity_inputs(rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    latest = latest_rows_by_type_entity(rows)

    tracked = set(cfg.get("tracked_entities", []))
    require_tracked = bool(cfg.get("require_tracked_entity", True))

    funding_map: Dict[str, Dict[str, Any]] = {}
    oi_map: Dict[str, Dict[str, Any]] = {}
    oi_change_map: Dict[str, Dict[str, Any]] = {}

    long_liq_watch_entities: set[str] = set()
    short_squeeze_watch_entities: set[str] = set()

    for (signal_type, entity), row in latest.items():
        if require_tracked and entity not in tracked:
            continue

        if signal_type == "perp_funding_rate":
            funding_map[entity] = funding_payload(row)

        elif signal_type == "perp_open_interest":
            oi_map[entity] = oi_payload(row)

        elif signal_type == "perp_open_interest_change":
            oi_change_map[entity] = oi_change_payload(row)

        elif signal_type == "perp_strategy_long_liquidation_watch":
            long_liq_watch_entities.add(entity)

        elif signal_type == "perp_strategy_short_squeeze_watch":
            short_squeeze_watch_entities.add(entity)

    entities = set(funding_map.keys()) | set(oi_map.keys()) | set(oi_change_map.keys())

    oi_values = {
        entity: safe_float(payload.get("avg_oi"), 0.0)
        for entity, payload in oi_map.items()
        if safe_float(payload.get("avg_oi"), 0.0) > 0.0
    }

    ranked = sorted(oi_values.items(), key=lambda x: x[1], reverse=True)
    oi_rank_pct_map: Dict[str, float] = {}

    count = len(ranked)
    for idx, (entity, _) in enumerate(ranked):
        if count == 1:
            oi_rank_pct_map[entity] = 1.0
        else:
            oi_rank_pct_map[entity] = round(1.0 - (idx / (count - 1)), 6)

    out: Dict[str, Dict[str, Any]] = {}

    for entity in sorted(entities):
        out[entity] = {
            "entity": entity,
            "funding": safe_float(funding_map.get(entity, {}).get("avg_funding"), 0.0),
            "avg_oi": safe_float(oi_map.get(entity, {}).get("avg_oi"), 0.0),
            "oi_change_pct": safe_float(oi_change_map.get(entity, {}).get("oi_change_pct"), 0.0),
            "oi_rank_pct": safe_float(oi_rank_pct_map.get(entity), 0.0),
            "long_liq_watch": entity in long_liq_watch_entities,
            "short_squeeze_watch": entity in short_squeeze_watch_entities,
        }

    return out


def score_confidence(
    oi_rank_pct: float,
    oi_change_pct: float,
    strategy_alignment: bool,
    cfg: Dict[str, Any],
) -> float:
    confidence = safe_float(cfg.get("confidence_base", 0.72), 0.72)

    if oi_rank_pct >= safe_float(cfg.get("oi_rank_strong", 0.80), 0.80):
        confidence += safe_float(cfg.get("confidence_bonus_strong_oi", 0.08), 0.08)

    if (
        oi_change_pct >= safe_float(cfg.get("oi_change_strong_rising_threshold_pct", 4.0), 4.0)
        or oi_change_pct <= safe_float(cfg.get("oi_change_strong_falling_threshold_pct", -4.0), -4.0)
    ):
        confidence += safe_float(cfg.get("confidence_bonus_strong_change", 0.08), 0.08)

    if strategy_alignment:
        confidence += safe_float(cfg.get("confidence_bonus_strategy_alignment", 0.08), 0.08)

    return round(clamp(confidence, 0.0, 0.98), 4)


def infer_pressure_side(
    funding: float,
    oi_rank_pct: float,
    oi_change_pct: float,
    positive_funding_threshold: float,
    negative_funding_threshold: float,
    soft_oi_rank_trigger_pct: float,
    soft_oi_change_trigger_pct: float,
    strategy_long: bool,
    strategy_short: bool,
) -> Optional[str]:
    """
    Resolve which side is crowded / vulnerable.

    Returns:
    • "long"  -> crowded longs / long flush risk
    • "short" -> crowded shorts / short flush risk
    • None    -> insufficient directional pressure
    """

    # hard directional funding first
    if funding >= positive_funding_threshold:
        return "long"

    if funding <= negative_funding_threshold:
        return "short"

    # explicit strategy-watch hints next
    if strategy_long and not strategy_short:
        return "long"

    if strategy_short and not strategy_long:
        return "short"

    # muted-funding fallback: use funding sign only if positioning is clearly expanding
    if oi_rank_pct >= soft_oi_rank_trigger_pct and oi_change_pct >= soft_oi_change_trigger_pct:
        if funding > 0:
            return "long"
        if funding < 0:
            return "short"

    return None

# ---------------------------------------------------
# PUBLIC COLLECTOR
# ---------------------------------------------------

@register_collector(
    name="liquidation_engine",
    priority=1,
    tags=["flows", "liquidation", "squeeze", "perps", "trading"],
    category="flows",
    execution="fast",
)
def fetch_liquidation_stress_signals(signals_override=None) -> List[Signal]:
    started = time.time()
    cfg = load_engine_config()
    signals: List[Signal] = []

    if not bool(cfg.get("enabled", True)):
        info_log("disabled by config")
        return signals

    # ---------------------------------------------------
    # SIGNAL SOURCE (TRADING LOOP FIRST, LAKE FALLBACK)
    # ---------------------------------------------------

    if isinstance(signals_override, list) and signals_override:
        raw_rows = object_rows_only(signals_override)
        debug_log(cfg, f"using trading loop signals override rows={len(raw_rows)}")
    else:
        lake = load_signal_lake()
        raw_rows = object_rows_only(lake.get("signals", []))
        debug_log(cfg, f"using signal lake rows={len(raw_rows)}")

    lookback_signal_count = safe_int(cfg.get("lookback_signal_count", 5000), 5000)
    rows = raw_rows[-lookback_signal_count:]

    entity_inputs = build_entity_inputs(rows, cfg)

    if not entity_inputs:
        info_log("no entity inputs found")
        return signals

    positive_funding_threshold = safe_float(cfg.get("positive_funding_threshold", 0.00005), 0.00005)
    negative_funding_threshold = safe_float(cfg.get("negative_funding_threshold", -0.00005), -0.00005)

    oi_rank_min = safe_float(cfg.get("oi_rank_min", 0.40), 0.40)
    oi_change_rising_threshold_pct = safe_float(cfg.get("oi_change_rising_threshold_pct", 1.50), 1.50)
    oi_change_falling_threshold_pct = safe_float(cfg.get("oi_change_falling_threshold_pct", -1.50), -1.50)
    soft_oi_rank_trigger_pct = safe_float(cfg.get("soft_oi_rank_trigger_pct", 0.70), 0.70)
    soft_oi_change_trigger_pct = safe_float(cfg.get("soft_oi_change_trigger_pct", 1.00), 1.00)

    long_flush_risk = 0
    short_flush_risk = 0
    bullish_confirmations = 0
    bearish_confirmations = 0

    ranked_rows: List[Tuple[str, float, str]] = []

    for entity, payload in entity_inputs.items():
        funding = safe_float(payload.get("funding"), 0.0)
        avg_oi = safe_float(payload.get("avg_oi"), 0.0)
        oi_change_pct = safe_float(payload.get("oi_change_pct"), 0.0)
        oi_rank_pct = safe_float(payload.get("oi_rank_pct"), 0.0)

        if avg_oi <= 0.0:
            continue

        if oi_rank_pct < oi_rank_min:
            continue

        strategy_long = bool(payload.get("long_liq_watch", False))
        strategy_short = bool(payload.get("short_squeeze_watch", False))

        # ---------------------------------------------------
        # 🔴 PRESSURE DETECTION (UPGRADED)
        # ---------------------------------------------------

        pressure_side = infer_pressure_side(
            funding=funding,
            oi_rank_pct=oi_rank_pct,
            oi_change_pct=oi_change_pct,
            positive_funding_threshold=positive_funding_threshold,
            negative_funding_threshold=negative_funding_threshold,
            soft_oi_rank_trigger_pct=soft_oi_rank_trigger_pct,
            soft_oi_change_trigger_pct=soft_oi_change_trigger_pct,
            strategy_long=strategy_long,
            strategy_short=strategy_short,
        )

        # 🔴 NEW: detect squeeze independent of funding
        squeeze_long = (
            oi_rank_pct >= 0.7 and
            oi_change_pct >= 1.5 and
            funding > 0
        )

        squeeze_short = (
            oi_rank_pct >= 0.7 and
            oi_change_pct >= 1.5 and
            funding < 0
        )

        # ---------------------------------------------------
        # CROWDED LONGS → LONG FLUSH / BEARISH CONFIRMATION
        # ---------------------------------------------------

        if pressure_side == "long" or squeeze_long:
            confidence = score_confidence(
                oi_rank_pct=oi_rank_pct,
                oi_change_pct=oi_change_pct,
                strategy_alignment=strategy_long,
                cfg=cfg,
            )

            signals.append(
                build_long_flush_risk_signal(
                    entity=entity,
                    funding=funding,
                    avg_oi=avg_oi,
                    oi_rank_pct=oi_rank_pct,
                    oi_change_pct=oi_change_pct,
                    confidence=confidence,
                )
            )
            long_flush_risk += 1
            ranked_rows.append((entity, confidence, "long_flush_risk"))

            if oi_change_pct >= oi_change_rising_threshold_pct or strategy_long:
                signals.append(
                    build_bearish_squeeze_confirmation_signal(
                        entity=entity,
                        funding=funding,
                        avg_oi=avg_oi,
                        oi_rank_pct=oi_rank_pct,
                        oi_change_pct=oi_change_pct,
                        confidence=confidence,
                    )
                )
                bearish_confirmations += 1
                ranked_rows.append((entity, confidence, "bearish_confirmation"))

        # ---------------------------------------------------
        # CROWDED SHORTS → SHORT FLUSH / BULLISH CONFIRMATION
        # ---------------------------------------------------

        elif pressure_side == "short" or squeeze_short:
            confidence = score_confidence(
                oi_rank_pct=oi_rank_pct,
                oi_change_pct=oi_change_pct,
                strategy_alignment=strategy_short,
                cfg=cfg,
            )

            signals.append(
                build_short_flush_risk_signal(
                    entity=entity,
                    funding=funding,
                    avg_oi=avg_oi,
                    oi_rank_pct=oi_rank_pct,
                    oi_change_pct=oi_change_pct,
                    confidence=confidence,
                )
            )
            short_flush_risk += 1
            ranked_rows.append((entity, confidence, "short_flush_risk"))

            if oi_change_pct >= oi_change_rising_threshold_pct or strategy_short:
                signals.append(
                    build_bullish_squeeze_confirmation_signal(
                        entity=entity,
                        funding=funding,
                        avg_oi=avg_oi,
                        oi_rank_pct=oi_rank_pct,
                        oi_change_pct=oi_change_pct,
                        confidence=confidence,
                    )
                )
                bullish_confirmations += 1
                ranked_rows.append((entity, confidence, "bullish_confirmation"))

        # ---------------------------------------------------
        # OI COLLAPSE WITH EXTREME POSITIONING = FORCED UNWIND RISK
        # ---------------------------------------------------

        if oi_change_pct <= oi_change_falling_threshold_pct:
            confidence = score_confidence(
                oi_rank_pct=oi_rank_pct,
                oi_change_pct=oi_change_pct,
                strategy_alignment=False,
                cfg=cfg,
            )

            if funding > 0 or pressure_side == "long":
                signals.append(
                    build_long_flush_risk_signal(
                        entity=entity,
                        funding=funding,
                        avg_oi=avg_oi,
                        oi_rank_pct=oi_rank_pct,
                        oi_change_pct=oi_change_pct,
                        confidence=confidence,
                    )
                )
                long_flush_risk += 1
                ranked_rows.append((entity, confidence, "long_flush_unwind"))

            elif funding < 0 or pressure_side == "short":
                signals.append(
                    build_short_flush_risk_signal(
                        entity=entity,
                        funding=funding,
                        avg_oi=avg_oi,
                        oi_rank_pct=oi_rank_pct,
                        oi_change_pct=oi_change_pct,
                        confidence=confidence,
                    )
                )
                short_flush_risk += 1
                ranked_rows.append((entity, confidence, "short_flush_unwind"))

    ranked_rows = sorted(ranked_rows, key=lambda x: x[1], reverse=True)
    top_rows = [
        f"{entity}:{tag}:{confidence:.2f}"
        for entity, confidence, tag in ranked_rows[:safe_int(cfg.get("max_summary_rows", 6), 6)]
    ]

    signals.append(
        build_summary_signal(
            total_entities=len(entity_inputs),
            long_flush_risk=long_flush_risk,
            short_flush_risk=short_flush_risk,
            bullish_confirmations=bullish_confirmations,
            bearish_confirmations=bearish_confirmations,
            top_rows=top_rows,
        )
    )

    max_signals_per_run = safe_int(cfg.get("max_signals_per_run", 60), 60)
    signals = signals[:max_signals_per_run]

    runtime = round(time.time() - started, 2)
    debug_log(
        cfg,
        f"rows={len(rows)} entities={len(entity_inputs)} "
        f"long_flush_risk={long_flush_risk} short_flush_risk={short_flush_risk} "
        f"bullish_confirmations={bullish_confirmations} bearish_confirmations={bearish_confirmations} "
        f"signals_returned={len(signals)} runtime={runtime}s"
    )

    return signals

# ---------------------------------------------------
# DIRECT TEST MODE
# ---------------------------------------------------

if __name__ == "__main__":
    rows = fetch_liquidation_stress_signals()
    print(f"count={len(rows)}")
    for row in rows[:20]:
        print(
            getattr(row, "signal_type", None),
            getattr(row, "entity", None),
            getattr(row, "summary", None),
        )
