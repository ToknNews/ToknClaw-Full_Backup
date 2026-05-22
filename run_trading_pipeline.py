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
# MODULE: run_trading_pipeline
# PURPOSE: Run a fast, isolated trading-only pipeline using direct market-data
#          collectors, pluggable strategy hooks, and durable trading snapshot
#          outputs without invoking the full narrative / Solana ingestion stack.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This runner is designed to:
• call direct market-data collectors needed for trading
• support majors, midcaps, and paper-first discovered assets
• support long and short downstream decision flow
• run pluggable strategy adapters and module hooks
• build trade_signals and paper_trading from a dedicated trading snapshot
• persist translator-ready context outside the full ToknNews pipeline
• remain additive and OpenClaw agent ready

Primary Config
--------------
/opt/toknclaw/config/trading_runner.json
/opt/toknclaw/config/trading_universe.json

Primary Outputs
---------------
/opt/toknclaw/data/snapshots/latest_snapshot_trading.json
/opt/toknclaw/data/narrative/trading_context.json
"""

from __future__ import annotations

# ---------------------------------------------------
# PATH SETUP
# ---------------------------------------------------

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SIGNAL_ENGINE_DIR = ROOT_DIR / "signal_engine"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if str(SIGNAL_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(SIGNAL_ENGINE_DIR))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import argparse
import importlib
import json
import os
import time
import traceback
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from signal_engine.pipeline.price_engine import update_price_history
from signal_engine.pipeline.trade_signal_engine import build_trade_signals
from signal_engine.pipeline.paper_trading_engine import build_paper_trading
from signal_engine.pipeline.trading_state_engine import build_trading_state
from signal_engine.pipeline.market_regime_engine import build_regime
from signal_engine.pipeline.trade_sizing_engine import build_trade_sizing
from signal_engine.pipeline.trade_leverage_engine import build_trade_leverage
# ---------------------------------------------------
# PATHS / DEFAULTS
# ---------------------------------------------------

RUNNER_CONFIG_PATH = Path("/opt/toknclaw/config/trading_runner.json")
UNIVERSE_CONFIG_PATH = Path("/opt/toknclaw/config/trading_universe.json")

DEFAULT_RUNNER_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "loop_interval_sec": 5,
    "snapshot_path": "/opt/toknclaw/data/snapshots/latest_snapshot_trading.json",
    "snapshot_tmp_path": "/opt/toknclaw/data/snapshots/latest_snapshot_trading.tmp",
    "persist_versioned_snapshots": False,
    "versioned_snapshot_dir": "/opt/toknclaw/data/snapshots/trading_runs",
    "translator_output_path": "/opt/toknclaw/data/narrative/trading_context.json",
    "include_market_context": True,
    "include_translator_payload": True,
    "market_modules": [],
    "strategy_modules": [],
    "trade_signal_filters": {
        "drop_neutral_rows": False,
        "drop_non_tradable_entities": True
    },
    "agent_hooks": {
        "enabled": True
    }
}

DEFAULT_UNIVERSE_CONFIG: Dict[str, Any] = {
    "tiers": {
        "majors": ["BTC", "ETH", "SOL", "BNB", "XRP"],
        "midcaps": ["DOGE", "LINK", "AVAX", "ARB", "OP", "INJ", "RNDR", "PYTH", "JUP"],
        "paper_candidates": []
    },
    "enabled_tiers": ["majors", "midcaps", "paper_candidates"],
    "paper_trade_only_tiers": ["paper_candidates"],
    "discovery_policy": {
        "enabled": True,
        "paper_first": True,
        "auto_add_to_tier": "paper_candidates",
        "auto_promote_to_live": False
    },
    "agent_hooks": {
        "enabled": True
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


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default


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


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("debug", True))


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[TRADING RUNNER] {message}")


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default)

    tmp_path.replace(path)


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:
            pass

    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)

    return str(obj)


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value

    return merged

# ---------------------------------------------------
# CONFIG LOADERS
# ---------------------------------------------------

def load_runner_config() -> Dict[str, Any]:
    raw = read_json_file(RUNNER_CONFIG_PATH, {})
    if not isinstance(raw, dict):
        raw = {}

    cfg = merge_dicts(DEFAULT_RUNNER_CONFIG, raw)

    cfg["snapshot_path"] = clean_text(cfg.get("snapshot_path")) or DEFAULT_RUNNER_CONFIG["snapshot_path"]
    cfg["snapshot_tmp_path"] = clean_text(cfg.get("snapshot_tmp_path")) or DEFAULT_RUNNER_CONFIG["snapshot_tmp_path"]
    cfg["translator_output_path"] = clean_text(cfg.get("translator_output_path")) or DEFAULT_RUNNER_CONFIG["translator_output_path"]
    cfg["versioned_snapshot_dir"] = clean_text(cfg.get("versioned_snapshot_dir")) or DEFAULT_RUNNER_CONFIG["versioned_snapshot_dir"]
    cfg["loop_interval_sec"] = safe_int(cfg.get("loop_interval_sec", 5), 5)

    return cfg


def load_universe_config() -> Dict[str, Any]:
    raw = read_json_file(UNIVERSE_CONFIG_PATH, {})
    if not isinstance(raw, dict):
        raw = {}

    cfg = merge_dicts(DEFAULT_UNIVERSE_CONFIG, raw)

    tiers = safe_dict(cfg.get("tiers"))
    normalized_tiers: Dict[str, List[str]] = {}

    for tier_name, assets in tiers.items():
        normalized_tiers[clean_text(tier_name)] = [
            clean_upper(x) for x in safe_list(assets) if clean_text(x)
        ]

    cfg["tiers"] = normalized_tiers
    cfg["enabled_tiers"] = [clean_text(x) for x in safe_list(cfg.get("enabled_tiers")) if clean_text(x)]
    cfg["paper_trade_only_tiers"] = [clean_text(x) for x in safe_list(cfg.get("paper_trade_only_tiers")) if clean_text(x)]

    return cfg


def enabled_universe_assets(universe_cfg: Dict[str, Any]) -> set[str]:
    tiers = safe_dict(universe_cfg.get("tiers"))
    enabled_tiers = safe_list(universe_cfg.get("enabled_tiers"))

    assets: set[str] = set()

    for tier in enabled_tiers:
        for asset in safe_list(tiers.get(tier)):
            assets.add(clean_upper(asset))

    return assets


def paper_trade_only_assets(universe_cfg: Dict[str, Any]) -> set[str]:
    tiers = safe_dict(universe_cfg.get("tiers"))
    paper_tiers = safe_list(universe_cfg.get("paper_trade_only_tiers"))

    assets: set[str] = set()

    for tier in paper_tiers:
        for asset in safe_list(tiers.get(tier)):
            assets.add(clean_upper(asset))

    return assets


def tier_for_entity(entity: str, universe_cfg: Dict[str, Any]) -> str:
    target = clean_upper(entity)
    tiers = safe_dict(universe_cfg.get("tiers"))

    for tier_name, assets in tiers.items():
        if target in {clean_upper(x) for x in safe_list(assets)}:
            return clean_text(tier_name)

    return "unknown"

# ---------------------------------------------------
# CALLABLE RESOLUTION
# ---------------------------------------------------

def resolve_callable(module_path: str, function_names: List[str]) -> Tuple[Optional[Callable[..., Any]], str]:
    if not module_path:
        return None, "missing_module_path"

    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        return None, f"module_import_failed:{exc}"

    for fn_name in function_names:
        if hasattr(module, fn_name):
            fn = getattr(module, fn_name)
            if callable(fn):
                return fn, "ok"

    return None, "function_not_found"


def normalize_callable_result(raw: Any) -> List[Any]:
    if raw is None:
        return []

    if isinstance(raw, list):
        return raw

    if isinstance(raw, tuple):
        return list(raw)

    if isinstance(raw, dict):
        return [raw]

    try:
        return list(raw)
    except Exception:
        return []


def signal_to_dict(signal: Any) -> Dict[str, Any]:
    if isinstance(signal, dict):
        row = dict(signal)
    elif hasattr(signal, "__dict__"):
        row = dict(signal.__dict__)
    else:
        return {}

    ts = row.get("timestamp")
    if hasattr(ts, "isoformat"):
        row["timestamp"] = ts.isoformat()

    entity = row.get("entity")
    if isinstance(entity, str):
        row["entity"] = clean_upper(entity)

    return row

# ---------------------------------------------------
# SIGNAL FILTERS
# ---------------------------------------------------

def filter_signal_rows_to_universe(signal_rows: List[Dict[str, Any]], tradable_assets: set[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in signal_rows:
        entity = clean_upper(row.get("entity"))
        if entity in tradable_assets:
            row = dict(row)
            row["entity"] = entity
            out.append(row)

    return out


def filter_trade_signal_rows(
    trade_signals: Dict[str, Any],
    tradable_assets: set[str],
    paper_only_assets: set[str],
    universe_cfg: Dict[str, Any],
    runner_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    out = deepcopy(trade_signals if isinstance(trade_signals, dict) else {})
    rows = safe_list(out.get("rows"))
    filtered_rows: List[Dict[str, Any]] = []

    drop_neutral = safe_bool(
        safe_dict(runner_cfg.get("trade_signal_filters")).get("drop_neutral_rows", False),
        False,
    )
    drop_non_tradable = safe_bool(
        safe_dict(runner_cfg.get("trade_signal_filters")).get("drop_non_tradable_entities", True),
        True,
    )

    for row in rows:
        if not isinstance(row, dict):
            continue

        entity = clean_upper(row.get("entity"))
        direction = clean_text(row.get("direction"))

        if drop_non_tradable and entity not in tradable_assets:
            continue

        if drop_neutral and direction == "neutral":
            continue

        new_row = dict(row)
        new_row["entity"] = entity
        new_row["universe_tier"] = tier_for_entity(entity, universe_cfg)
        new_row["paper_trade_only"] = entity in paper_only_assets
        filtered_rows.append(new_row)

    out["rows"] = filtered_rows
    summary = safe_dict(out.get("summary"))
    summary["filtered_row_count"] = len(filtered_rows)
    out["summary"] = summary

    return out

# ---------------------------------------------------
# STRATEGY ADAPTERS
# ---------------------------------------------------

def build_funding_oi_strategy_from_raw_signals(
    raw_signals: List[Dict[str, Any]],
    tradable_assets: set[str],
    runner_cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    try:
        module = importlib.import_module("signal_engine.collectors.flows.funding_oi_strategy")
    except Exception as exc:
        debug_log(runner_cfg, f"funding_oi_strategy import failed error={exc}")
        return []

    try:
        cfg = module.load_engine_config()
        cfg["tracked_entities"] = sorted(tradable_assets)
        cfg["require_tracked_entity"] = True

        rows = [dict(x) for x in raw_signals if isinstance(x, dict)]
        entity_inputs = module.build_entity_inputs(rows, cfg)

        if not entity_inputs:
            summary_obj = module.build_summary_signal(
                total_entities=0,
                crowded_longs=0,
                crowded_shorts=0,
                short_squeeze_watch=0,
                long_liq_watch=0,
                top_setups=[],
            )
            return [signal_to_dict(summary_obj)]

        min_oi_rank_pct = module.safe_float(cfg.get("min_oi_rank_pct", 0.60), 0.60)
        strong_oi_rank_pct = module.safe_float(cfg.get("strong_oi_rank_pct", 0.80), 0.80)
        long_crowding_threshold = module.safe_float(cfg.get("long_crowding_threshold", 0.0004), 0.0004)
        short_crowding_threshold = module.safe_float(cfg.get("short_crowding_threshold", -0.0004), -0.0004)
        max_broadcast = module.safe_int(cfg.get("max_broadcast_setups", 5), 5)
        max_strategy_signals = module.safe_int(cfg.get("max_strategy_signals", 50), 50)

        out: List[Dict[str, Any]] = []
        crowded_longs = 0
        crowded_shorts = 0
        short_squeeze_watch = 0
        long_liq_watch = 0
        setup_rows: List[Tuple[str, float, str]] = []

        for entity, payload in entity_inputs.items():
            avg_funding = module.safe_float(payload.get("avg_funding"), 0.0)
            avg_oi = module.safe_float(payload.get("avg_oi"), 0.0)
            oi_rank_pct = module.safe_float(payload.get("oi_rank_pct"), 0.0)
            has_divergence = bool(payload.get("has_divergence", False))

            if avg_oi <= 0.0:
                continue

            if oi_rank_pct < min_oi_rank_pct:
                continue

            confidence = module.confidence_for_entity(
                oi_rank_pct=oi_rank_pct,
                has_divergence=has_divergence,
                cfg=cfg,
            )

            if avg_funding >= long_crowding_threshold:
                crowded_longs += 1
                out.append(signal_to_dict(module.build_crowded_longs_signal(
                    entity=entity,
                    avg_funding=avg_funding,
                    avg_oi=avg_oi,
                    oi_rank_pct=oi_rank_pct,
                    has_divergence=has_divergence,
                    confidence=confidence,
                )))

                if has_divergence or oi_rank_pct >= strong_oi_rank_pct:
                    long_liq_watch += 1
                    out.append(signal_to_dict(module.build_long_liquidation_watch_signal(
                        entity=entity,
                        avg_funding=avg_funding,
                        avg_oi=avg_oi,
                        oi_rank_pct=oi_rank_pct,
                        has_divergence=has_divergence,
                        confidence=confidence,
                    )))
                    setup_rows.append((entity, confidence, "long_liquidation_watch"))

            elif avg_funding <= short_crowding_threshold:
                crowded_shorts += 1
                out.append(signal_to_dict(module.build_crowded_shorts_signal(
                    entity=entity,
                    avg_funding=avg_funding,
                    avg_oi=avg_oi,
                    oi_rank_pct=oi_rank_pct,
                    has_divergence=has_divergence,
                    confidence=confidence,
                )))

                if has_divergence or oi_rank_pct >= strong_oi_rank_pct:
                    short_squeeze_watch += 1
                    out.append(signal_to_dict(module.build_short_squeeze_watch_signal(
                        entity=entity,
                        avg_funding=avg_funding,
                        avg_oi=avg_oi,
                        oi_rank_pct=oi_rank_pct,
                        has_divergence=has_divergence,
                        confidence=confidence,
                    )))
                    setup_rows.append((entity, confidence, "short_squeeze_watch"))

        if bool(cfg.get("emit_broadcast_setup", True)):
            ranked_setups = sorted(setup_rows, key=lambda x: x[1], reverse=True)[:max_broadcast]

            for entity, confidence, setup_type in ranked_setups:
                payload = entity_inputs.get(entity, {})
                out.append(signal_to_dict(module.build_broadcast_setup_signal(
                    entity=entity,
                    setup_type=setup_type,
                    avg_funding=module.safe_float(payload.get("avg_funding"), 0.0),
                    avg_oi=module.safe_float(payload.get("avg_oi"), 0.0),
                    oi_rank_pct=module.safe_float(payload.get("oi_rank_pct"), 0.0),
                    has_divergence=bool(payload.get("has_divergence", False)),
                    confidence=confidence,
                )))

        ranked_top = [
            f"{entity}:{setup_type}:{confidence:.2f}"
            for entity, confidence, setup_type in sorted(setup_rows, key=lambda x: x[1], reverse=True)[:5]
        ]

        out.append(signal_to_dict(module.build_summary_signal(
            total_entities=len(entity_inputs),
            crowded_longs=crowded_longs,
            crowded_shorts=crowded_shorts,
            short_squeeze_watch=short_squeeze_watch,
            long_liq_watch=long_liq_watch,
            top_setups=ranked_top,
        )))

        return out[:max_strategy_signals]

    except Exception as exc:
        debug_log(runner_cfg, f"funding_oi_strategy adapter failed error={exc}")
        return []

# ---------------------------------------------------
# MARKET CONTEXT / TRANSLATOR PAYLOAD
# ---------------------------------------------------

def build_market_context(
    snapshot: Dict[str, Any],
    universe_cfg: Dict[str, Any],
    tradable_assets: set[str],
    paper_only_assets: set[str],
) -> Dict[str, Any]:
    signals = safe_list(snapshot.get("signals"))
    trade_signals = safe_dict(snapshot.get("trade_signals"))
    trade_rows = safe_list(trade_signals.get("rows"))

    signal_counts_by_type: Dict[str, int] = {}
    signal_counts_by_entity: Dict[str, int] = {}

    for row in signals:
        if not isinstance(row, dict):
            continue

        st = clean_text(row.get("signal_type"))
        entity = clean_upper(row.get("entity"))

        signal_counts_by_type[st] = signal_counts_by_type.get(st, 0) + 1
        signal_counts_by_entity[entity] = signal_counts_by_entity.get(entity, 0) + 1

    top_trade_rows = sorted(
        [r for r in trade_rows if isinstance(r, dict)],
        key=lambda x: safe_float(x.get("confidence"), 0.0),
        reverse=True,
    )[:10]

    return {
        "timestamp": snapshot.get("timestamp"),
        "tradable_assets": sorted(tradable_assets),
        "paper_trade_only_assets": sorted(paper_only_assets),
        "signal_counts_by_type": signal_counts_by_type,
        "signal_counts_by_entity": signal_counts_by_entity,
        "top_trade_rows": top_trade_rows,
        "trade_signal_summary": safe_dict(trade_signals.get("summary")),
        "paper_trading_summary": safe_dict(safe_dict(snapshot.get("paper_trading")).get("summary")),
        "universe": {
            "enabled_tiers": safe_list(universe_cfg.get("enabled_tiers")),
            "paper_trade_only_tiers": safe_list(universe_cfg.get("paper_trade_only_tiers")),
            "tiers": safe_dict(universe_cfg.get("tiers")),
        },
    }


def build_translator_payload(snapshot: Dict[str, Any], market_context: Dict[str, Any]) -> Dict[str, Any]:
    trade_signals = safe_dict(snapshot.get("trade_signals"))
    paper_trading = safe_dict(snapshot.get("paper_trading"))

    return {
        "timestamp": snapshot.get("timestamp"),
        "source_snapshot_path": clean_text(snapshot.get("_snapshot_path")),
        "market_context": market_context,
        "trade_signals": {
            "summary": safe_dict(trade_signals.get("summary")),
            "rows": safe_list(trade_signals.get("rows"))[:25],
        },
        "paper_trading": {
            "engine_status": safe_dict(paper_trading.get("engine_status")),
            "portfolio": safe_dict(paper_trading.get("portfolio")),
            "summary": safe_dict(paper_trading.get("summary")),
        },
    }

# ---------------------------------------------------
# MODULE EXECUTION
# ---------------------------------------------------

def run_market_modules(runner_cfg: Dict[str, Any], tradable_assets: set[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    collected_rows: List[Dict[str, Any]] = []
    module_runs: List[Dict[str, Any]] = []

    for entry in safe_list(runner_cfg.get("market_modules")):
        entry = safe_dict(entry)

        if not safe_bool(entry.get("enabled", False), False):
            continue

        name = clean_text(entry.get("name"))
        module_path = clean_text(entry.get("module"))
        function_names = [clean_text(x) for x in safe_list(entry.get("functions")) if clean_text(x)]

        fn, status = resolve_callable(module_path, function_names)
        if fn is None:
            module_runs.append({
                "name": name,
                "module": module_path,
                "status": status,
                "count": 0,
                "runtime_sec": 0.0,
            })
            debug_log(runner_cfg, f"module_skip name={name} status={status}")
            continue

        started = time.time()

        try:
            raw = fn()
            rows = [signal_to_dict(x) for x in normalize_callable_result(raw)]
            rows = [x for x in rows if x]
            rows = filter_signal_rows_to_universe(rows, tradable_assets)

            collected_rows.extend(rows)

            runtime = round(time.time() - started, 2)
            module_runs.append({
                "name": name,
                "module": module_path,
                "status": "ok",
                "count": len(rows),
                "runtime_sec": runtime,
            })
            debug_log(runner_cfg, f"module_ok name={name} count={len(rows)} runtime={runtime}s")

        except Exception as exc:
            runtime = round(time.time() - started, 2)
            module_runs.append({
                "name": name,
                "module": module_path,
                "status": f"error:{exc}",
                "count": 0,
                "runtime_sec": runtime,
            })
            debug_log(runner_cfg, f"module_error name={name} runtime={runtime}s error={exc}")

    return collected_rows, module_runs


def run_strategy_modules(
    runner_cfg: Dict[str, Any],
    raw_signals: List[Dict[str, Any]],
    tradable_assets: set[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    out: List[Dict[str, Any]] = []
    module_runs: List[Dict[str, Any]] = []

    for entry in safe_list(runner_cfg.get("strategy_modules")):
        entry = safe_dict(entry)

        if not safe_bool(entry.get("enabled", False), False):
            continue

        name = clean_text(entry.get("name"))
        started = time.time()

        try:
            adapter = clean_text(entry.get("adapter"))

            if adapter == "funding_oi_from_raw_signals":
                rows = build_funding_oi_strategy_from_raw_signals(
                    raw_signals=raw_signals,
                    tradable_assets=tradable_assets,
                    runner_cfg=runner_cfg,
                )
                rows = [x for x in rows if isinstance(x, dict)]
                out.extend(rows)

                runtime = round(time.time() - started, 2)
                module_runs.append({
                    "name": name,
                    "status": "ok",
                    "count": len(rows),
                    "runtime_sec": runtime,
                })
                debug_log(runner_cfg, f"strategy_ok name={name} count={len(rows)} runtime={runtime}s")
                continue

            module_path = clean_text(entry.get("module"))
            function_names = [clean_text(x) for x in safe_list(entry.get("functions")) if clean_text(x)]
            fn, status = resolve_callable(module_path, function_names)

            if fn is None:
                runtime = round(time.time() - started, 2)
                module_runs.append({
                    "name": name,
                    "status": status,
                    "count": 0,
                    "runtime_sec": runtime,
                })
                debug_log(runner_cfg, f"strategy_skip name={name} status={status}")
                continue

            if name == "liquidation_engine":
                raw = fn(signals_override=raw_signals)
            else:
                raw = fn()
            rows = [signal_to_dict(x) for x in normalize_callable_result(raw)]
            rows = [x for x in rows if x]
            rows = filter_signal_rows_to_universe(rows, tradable_assets)

            out.extend(rows)

            runtime = round(time.time() - started, 2)
            module_runs.append({
                "name": name,
                "status": "ok",
                "count": len(rows),
                "runtime_sec": runtime,
            })
            debug_log(runner_cfg, f"strategy_ok name={name} count={len(rows)} runtime={runtime}s")

        except Exception as exc:
            runtime = round(time.time() - started, 2)
            module_runs.append({
                "name": name,
                "status": f"error:{exc}",
                "count": 0,
                "runtime_sec": runtime,
            })
            debug_log(runner_cfg, f"strategy_error name={name} runtime={runtime}s error={exc}")

    return out, module_runs

# ---------------------------------------------------
# SNAPSHOT PERSISTENCE
# ---------------------------------------------------

def persist_trading_snapshot(snapshot: Dict[str, Any], runner_cfg: Dict[str, Any]) -> None:
    snapshot_path = Path(clean_text(runner_cfg.get("snapshot_path")))
    snapshot_tmp_path = Path(clean_text(runner_cfg.get("snapshot_tmp_path")))

    write_json_atomic(snapshot_path, snapshot_tmp_path, snapshot)

    if safe_bool(runner_cfg.get("persist_versioned_snapshots", False), False):
        versioned_dir = Path(clean_text(runner_cfg.get("versioned_snapshot_dir")))
        versioned_dir.mkdir(parents=True, exist_ok=True)

        stamp = clean_text(snapshot.get("timestamp")).replace(":", "-")
        versioned_path = versioned_dir / f"trading_snapshot_{stamp}.json"

        with open(versioned_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, default=_json_default)


def persist_translator_payload(payload: Dict[str, Any], runner_cfg: Dict[str, Any]) -> None:
    output_path = Path(clean_text(runner_cfg.get("translator_output_path")))
    tmp_path = output_path.with_suffix(".tmp")

    write_json_atomic(output_path, tmp_path, payload)

# ---------------------------------------------------
# CORE CYCLE
# ---------------------------------------------------

def build_trading_snapshot(runner_cfg: Dict[str, Any], universe_cfg: Dict[str, Any]) -> Dict[str, Any]:
    tradable_assets = enabled_universe_assets(universe_cfg)
    paper_only_assets = paper_trade_only_assets(universe_cfg)

    cycle_started = time.time()

    raw_signals, market_module_runs = run_market_modules(runner_cfg, tradable_assets)
    strategy_signals, strategy_module_runs = run_strategy_modules(runner_cfg, raw_signals, tradable_assets)

    all_signals = raw_signals + strategy_signals

    snapshot: Dict[str, Any] = {
        "timestamp": now_iso(),
        "mode": "trading",
        "signals": all_signals,
        "collector_health": {
            "market_modules": market_module_runs,
            "strategy_modules": strategy_module_runs,
        },
        "universe": deepcopy(universe_cfg),
        "meta": {
            "runner": "run_trading_pipeline.py",
            "raw_signal_count": len(raw_signals),
            "strategy_signal_count": len(strategy_signals),
            "signal_count": len(all_signals),
            "tradable_asset_count": len(tradable_assets),
            "paper_trade_only_asset_count": len(paper_only_assets),
        },
    }

    try:
        update_price_history(snapshot)
        snapshot["meta"]["price_engine"] = {"status": "ok"}
    except Exception as exc:
        snapshot["meta"]["price_engine"] = {"status": f"error:{exc}"}
        debug_log(runner_cfg, f"price_engine error={exc}")

    try:
        trade_signals = build_trade_signals(snapshot)
    except Exception as exc:
        trade_signals = {
            "rows": [],
            "summary": {
                "error": str(exc)
            }
        }
        debug_log(runner_cfg, f"trade_signal_engine error={exc}")

    snapshot["trade_signals"] = filter_trade_signal_rows(
        trade_signals=trade_signals,
        tradable_assets=tradable_assets,
        paper_only_assets=paper_only_assets,
        universe_cfg=universe_cfg,
        runner_cfg=runner_cfg,
    )

    # ---------------------------------------------------
    # 🔴 MARKET REGIME REFRESH
    # ---------------------------------------------------

    try:
        market_regime = build_regime(snapshot)
        snapshot["market_regime"] = market_regime
        debug_log(
            runner_cfg,
            f"market_regime_built regime={safe_dict(market_regime).get('regime')}"
        )
    except Exception as exc:
        snapshot["market_regime"] = {}
        debug_log(runner_cfg, f"market_regime_error error={exc}")

    # ---------------------------------------------------
    # 🔴 TRADE SIZING REFRESH
    # ---------------------------------------------------

    try:
        trade_sizing = build_trade_sizing(write_output=True)
        snapshot["trade_sizing"] = trade_sizing
        debug_log(
            runner_cfg,
            "trade_sizing_built "
            + f"rows={safe_int(safe_dict(trade_sizing.get('summary')).get('sized_row_count'), 0)} "
            + f"avg_size={safe_float(safe_dict(trade_sizing.get('summary')).get('avg_recommended_position_usd'), 0.0)}"
        )
    except Exception as exc:
        snapshot["trade_sizing"] = {}
        debug_log(runner_cfg, f"trade_sizing_error error={exc}")

    # ---------------------------------------------------
    # 🔴 PAPER TRADING BUILD
    # ---------------------------------------------------

    try:
        snapshot["paper_trading"] = build_paper_trading(snapshot)

    except Exception as exc:
        snapshot["paper_trading"] = {
            "engine_status": {
                "status": "error",
                "last_run_at": now_iso(),
                "last_error": str(exc),
            }
        }
        debug_log(runner_cfg, f"paper_trading_engine error={exc}")


    # ---------------------------------------------------
    # 🔴 TRADE LEVERAGE REFRESH
    # ---------------------------------------------------

    try:
        trade_leverage = build_trade_leverage(write_output=True)
        snapshot["trade_leverage"] = trade_leverage
        debug_log(
            runner_cfg,
            "trade_leverage_built "
            + f"candidates={safe_int(safe_dict(trade_leverage.get('summary')).get('candidate_count'), 0)} "
            + f"allowed={safe_int(safe_dict(trade_leverage.get('summary')).get('leverage_allowed_count'), 0)}"
        )
    except Exception as exc:
        snapshot["trade_leverage"] = {}
        debug_log(runner_cfg, f"trade_leverage_error error={exc}")

    # ---------------------------------------------------
    # 🔴 BUILD CANONICAL TRADING STATE (PRIMARY OUTPUT)
    # ---------------------------------------------------

    try:
        trading_state = build_trading_state(snapshot, write_output=True)
        snapshot["trading_state"] = trading_state
        debug_log(runner_cfg, "trading_state_built")
    except Exception as exc:
        debug_log(runner_cfg, f"trading_state_error error={exc}")
        snapshot["trading_state"] = {}

    market_context = {}
    if safe_bool(runner_cfg.get("include_market_context", True), True):
        market_context = build_market_context(
            snapshot=snapshot,
            universe_cfg=universe_cfg,
            tradable_assets=tradable_assets,
            paper_only_assets=paper_only_assets,
        )

    snapshot["market_context"] = market_context

    snapshot_path = clean_text(runner_cfg.get("snapshot_path"))
    snapshot["_snapshot_path"] = snapshot_path
    snapshot["meta"]["runtime_sec"] = round(time.time() - cycle_started, 2)

    return snapshot


def run_cycle(runner_cfg: Dict[str, Any], universe_cfg: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = build_trading_snapshot(runner_cfg, universe_cfg)

    persist_trading_snapshot(snapshot, runner_cfg)

    if safe_bool(runner_cfg.get("include_translator_payload", True), True):
        payload = build_translator_payload(snapshot, safe_dict(snapshot.get("market_context")))
        persist_translator_payload(payload, runner_cfg)

    debug_log(
        runner_cfg,
        "cycle_complete "
        + f"signals={safe_int(safe_dict(snapshot.get('meta')).get('signal_count', 0), 0)} "
        + f"trade_rows={len(safe_list(safe_dict(snapshot.get('trade_signals')).get('rows')))} "
        + f"runtime={safe_float(safe_dict(snapshot.get('meta')).get('runtime_sec', 0.0), 0.0)}s"
    )

    return snapshot

# ---------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="ToknClaw isolated trading pipeline")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one trading cycle and exit",
    )
    parser.add_argument(
        "--sleep",
        type=int,
        help="Override loop interval seconds for this process",
    )

    args = parser.parse_args()

    runner_cfg = load_runner_config()
    universe_cfg = load_universe_config()

    if not safe_bool(runner_cfg.get("enabled", True), True):
        print("[TRADING RUNNER] disabled by config")
        return

    loop_interval = safe_int(args.sleep, runner_cfg.get("loop_interval_sec", 5)) if args.sleep is not None else safe_int(runner_cfg.get("loop_interval_sec", 5), 5)

    print("\n============================================================")
    print(" 🦞 TOKNCLAW TRADING PIPELINE")
    print("============================================================\n")

    if args.once:
        run_cycle(runner_cfg, universe_cfg)
        return

    while True:
        try:
            run_cycle(runner_cfg, universe_cfg)
        except Exception:
            print("[TRADING RUNNER] cycle failed")
            traceback.print_exc()

        time.sleep(loop_interval)


if __name__ == "__main__":
    main()
