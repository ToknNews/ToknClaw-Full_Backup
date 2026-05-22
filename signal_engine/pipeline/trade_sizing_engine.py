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
# MODULE: trade_sizing_engine
# PURPOSE: Compute portfolio-scaled position sizing, exposure caps, and
#          leverage eligibility using confidence, strategy quality, regime,
#          drawdown, and volatility-aware multipliers.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• read live trade rows and portfolio state
• produce recommended position sizes as % of portfolio
• apply confidence / strategy / regime / drawdown / volatility multipliers
• enforce hard caps on single-position and total exposure
• determine whether leverage is allowed
• emit a clean artifact for paper trading, Reef, and future API users

Primary Inputs
--------------
/opt/toknclaw/data/snapshots/latest_snapshot_trading.json
/opt/toknclaw/data/paper_trading_state.json
/opt/toknclaw/data/analytics/strategy_performance.json
/opt/toknclaw/data/analytics/strategy_decisions.json
/opt/toknclaw/config/trade_sizing_engine.json

Primary Output
--------------
/opt/toknclaw/data/analytics/trade_sizing.json
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
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from signal_engine.runtime_config import load_config

# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

CONFIG_FILE = "trade_sizing_engine.json"

TRADING_SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")
PAPER_TRADING_STATE_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")
STRATEGY_PERFORMANCE_PATH = Path("/opt/toknclaw/data/analytics/strategy_performance.json")
STRATEGY_DECISIONS_PATH = Path("/opt/toknclaw/data/analytics/strategy_decisions.json")

OUTPUT_PATH = Path("/opt/toknclaw/data/analytics/trade_sizing.json")
TMP_OUTPUT_PATH = Path("/opt/toknclaw/data/analytics/trade_sizing.tmp")

# ---------------------------------------------------
# DEFAULT CONFIG
# ---------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,

    "base_risk_pct_of_equity": 0.02,
    "min_position_pct_of_equity": 0.005,
    "max_position_pct_of_equity": 0.07,
    "max_total_exposure_pct_of_equity": 0.35,

    "max_long_exposure_pct_of_equity": 0.25,
    "max_short_exposure_pct_of_equity": 0.25,

    "confidence_bands": [
        {"min": 0.00, "max": 0.39, "multiplier": 0.75},
        {"min": 0.40, "max": 0.54, "multiplier": 1.00},
        {"min": 0.55, "max": 0.69, "multiplier": 1.35},
        {"min": 0.70, "max": 1.00, "multiplier": 1.75}
    ],

    "strategy_health_multipliers": {
        "healthy": 1.10,
        "fragile_positive": 1.00,
        "neutral": 0.95,
        "weak": 0.75,
        "underperforming": 0.50,
        "insufficient_sample": 0.85,
        "unknown": 0.90
    },

    "regime_multipliers": {
        "aligned": 1.10,
        "neutral": 1.00,
        "conflict": 0.70,
        "unknown": 1.00
    },

    "drawdown_bands": [
        {"min": 0.00, "max": 1.99, "multiplier": 1.00},
        {"min": 2.00, "max": 4.99, "multiplier": 0.80},
        {"min": 5.00, "max": 100.0, "multiplier": 0.60}
    ],

    "volatility_bands": [
        {"max_abs_price_change_pct": 0.25, "multiplier": 1.10},
        {"max_abs_price_change_pct": 1.00, "multiplier": 1.00},
        {"max_abs_price_change_pct": 100.0, "multiplier": 0.75}
    ],

    "leverage": {
        "enabled": True,
        "default": 1.0,
        "max_allowed": 2.0,
        "min_profit_factor": 1.20,
        "min_closed_trades": 50,
        "max_drawdown_pct": 3.0,
        "healthy_only": True,
        "approved_multipliers": [
            {"min_confidence": 0.55, "leverage": 1.25},
            {"min_confidence": 0.70, "leverage": 1.50}
        ]
    }
}

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


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


def debug_enabled(cfg: Dict[str, Any]) -> bool:
    return safe_bool(cfg.get("debug", True), True)


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if debug_enabled(cfg):
        print(f"[TRADE SIZING] {message}")


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)
    merged = dict(DEFAULT_CONFIG)

    if isinstance(cfg, dict):
        for key, value in cfg.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                new_dict = dict(merged[key])
                new_dict.update(value)
                merged[key] = new_dict
            else:
                merged[key] = value

    return merged

# ---------------------------------------------------
# LOADERS
# ---------------------------------------------------

def load_trading_snapshot() -> Dict[str, Any]:
    return safe_dict(read_json_file(TRADING_SNAPSHOT_PATH, {}))


def load_paper_state() -> Dict[str, Any]:
    return safe_dict(read_json_file(PAPER_TRADING_STATE_PATH, {}))


def load_strategy_performance() -> Dict[str, Any]:
    return safe_dict(read_json_file(STRATEGY_PERFORMANCE_PATH, {}))


def load_strategy_decisions() -> Dict[str, Any]:
    return safe_dict(read_json_file(STRATEGY_DECISIONS_PATH, {}))

# ---------------------------------------------------
# CONTEXT EXTRACTION
# ---------------------------------------------------

def get_portfolio_context(paper_state: Dict[str, Any]) -> Dict[str, Any]:
    portfolio = safe_dict(paper_state.get("portfolio"))

    equity_usd = safe_float(portfolio.get("equity_usd"), 0.0)
    cash_usd = safe_float(portfolio.get("cash_usd"), 0.0)
    gross_exposure_usd = safe_float(portfolio.get("gross_exposure_usd"), 0.0)
    closed_count = safe_int(portfolio.get("closed_position_count"), 0)

    open_positions = safe_dict(paper_state.get("open_positions"))

    long_exposure = 0.0
    short_exposure = 0.0

    for _, pos in open_positions.items():
        pos = safe_dict(pos)
        side = clean_text(pos.get("side"))
        market_value_usd = safe_float(pos.get("market_value_usd"), 0.0)

        if side == "long":
            long_exposure += market_value_usd
        elif side == "short":
            short_exposure += market_value_usd

    return {
        "equity_usd": equity_usd,
        "cash_usd": cash_usd,
        "gross_exposure_usd": gross_exposure_usd,
        "closed_position_count": closed_count,
        "long_exposure_usd": round(long_exposure, 4),
        "short_exposure_usd": round(short_exposure, 4),
        "open_positions": open_positions,
    }


def get_backtest_quality(strategy_performance: Dict[str, Any]) -> Dict[str, Any]:
    backtest_snapshot = safe_dict(strategy_performance.get("backtest_snapshot"))
    portfolio = safe_dict(backtest_snapshot.get("portfolio"))
    closed_summary = safe_dict(backtest_snapshot.get("closed_position_summary"))

    return {
        "equity_usd": safe_float(portfolio.get("equity_usd"), 0.0),
        "realized_pnl_usd": safe_float(portfolio.get("realized_pnl_usd"), 0.0),
        "profit_factor": safe_float(closed_summary.get("profit_factor"), 0.0),
        "closed_trade_count": safe_int(closed_summary.get("total_closed_positions"), 0),
        "max_drawdown_pct": safe_float(backtest_snapshot.get("max_drawdown_pct"), 0.0),
    }


def get_current_trade_rows(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return safe_list(safe_dict(snapshot.get("trade_signals")).get("rows"))


def get_strategy_health_map(strategy_decisions: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}

    for row in safe_list(strategy_decisions.get("strategy_decisions")):
        row = safe_dict(row)
        key = clean_text(row.get("strategy_key"))
        health = clean_text(safe_dict(row.get("realized")).get("health")) or "unknown"
        if key:
            out[key] = health

    return out

# ---------------------------------------------------
# MULTIPLIER LOGIC
# ---------------------------------------------------

def get_confidence_multiplier(cfg: Dict[str, Any], confidence: float) -> float:
    for band in safe_list(cfg.get("confidence_bands")):
        band = safe_dict(band)
        lo = safe_float(band.get("min"), 0.0)
        hi = safe_float(band.get("max"), 1.0)
        mult = safe_float(band.get("multiplier"), 1.0)

        if confidence >= lo and confidence <= hi:
            return mult

    return 1.0


def get_drawdown_multiplier(cfg: Dict[str, Any], max_drawdown_pct: float) -> float:
    for band in safe_list(cfg.get("drawdown_bands")):
        band = safe_dict(band)
        lo = safe_float(band.get("min"), 0.0)
        hi = safe_float(band.get("max"), 100.0)
        mult = safe_float(band.get("multiplier"), 1.0)

        if max_drawdown_pct >= lo and max_drawdown_pct <= hi:
            return mult

    return 1.0


def get_volatility_multiplier(cfg: Dict[str, Any], abs_price_change_pct: float) -> float:
    for band in safe_list(cfg.get("volatility_bands")):
        band = safe_dict(band)
        max_abs = safe_float(band.get("max_abs_price_change_pct"), 100.0)
        mult = safe_float(band.get("multiplier"), 1.0)

        if abs_price_change_pct <= max_abs:
            return mult

    return 1.0


def infer_regime_alignment(direction: str, market_state: Dict[str, Any]) -> str:
    regime = clean_text(market_state.get("regime")).lower()
    risk_state = clean_text(market_state.get("risk_state")).lower()

    bullish = direction in {"bullish", "strong_bullish"}
    bearish = direction in {"bearish", "strong_bearish"}

    if bullish:
        if "risk_on" in regime or "bull" in regime or "risk_on" in risk_state:
            return "aligned"
        if "risk_off" in regime or "bear" in regime or "risk_off" in risk_state:
            return "conflict"
        return "neutral"

    if bearish:
        if "risk_off" in regime or "bear" in regime or "risk_off" in risk_state:
            return "aligned"
        if "risk_on" in regime or "bull" in regime or "risk_on" in risk_state:
            return "conflict"
        return "neutral"

    return "unknown"


def get_regime_multiplier(cfg: Dict[str, Any], alignment: str) -> float:
    return safe_float(
        safe_dict(cfg.get("regime_multipliers")).get(alignment),
        safe_float(safe_dict(cfg.get("regime_multipliers")).get("unknown"), 1.0),
    )


def get_strategy_health_multiplier(cfg: Dict[str, Any], health: str) -> float:
    mapping = safe_dict(cfg.get("strategy_health_multipliers"))
    return safe_float(mapping.get(health), safe_float(mapping.get("unknown"), 0.90))

# ---------------------------------------------------
# LEVERAGE LOGIC
# ---------------------------------------------------

def get_leverage_allowed(
    cfg: Dict[str, Any],
    strategy_health: str,
    confidence: float,
    backtest_quality: Dict[str, Any],
) -> Dict[str, Any]:
    leverage_cfg = safe_dict(cfg.get("leverage"))

    if not safe_bool(leverage_cfg.get("enabled", True), True):
        return {"allowed": False, "leverage": 1.0, "reason": "disabled"}

    profit_factor = safe_float(backtest_quality.get("profit_factor"), 0.0)
    closed_trades = safe_int(backtest_quality.get("closed_trade_count"), 0)
    max_drawdown_pct = safe_float(backtest_quality.get("max_drawdown_pct"), 0.0)

    if profit_factor < safe_float(leverage_cfg.get("min_profit_factor"), 1.20):
        return {"allowed": False, "leverage": 1.0, "reason": "profit_factor_too_low"}

    if closed_trades < safe_int(leverage_cfg.get("min_closed_trades"), 50):
        return {"allowed": False, "leverage": 1.0, "reason": "insufficient_closed_trades"}

    if max_drawdown_pct > safe_float(leverage_cfg.get("max_drawdown_pct"), 3.0):
        return {"allowed": False, "leverage": 1.0, "reason": "drawdown_too_high"}

    if safe_bool(leverage_cfg.get("healthy_only", True), True):
        if strategy_health not in {"healthy", "fragile_positive"}:
            return {"allowed": False, "leverage": 1.0, "reason": "strategy_health_not_approved"}

    selected = safe_float(leverage_cfg.get("default"), 1.0)

    for row in safe_list(leverage_cfg.get("approved_multipliers")):
        row = safe_dict(row)
        min_confidence = safe_float(row.get("min_confidence"), 1.0)
        lev = safe_float(row.get("leverage"), 1.0)

        if confidence >= min_confidence:
            selected = max(selected, lev)

    max_allowed = safe_float(leverage_cfg.get("max_allowed"), 2.0)
    selected = clamp(selected, 1.0, max_allowed)

    return {"allowed": True, "leverage": round(selected, 4), "reason": "approved"}

# ---------------------------------------------------
# PRICE / VOLATILITY EXTRACTION
# ---------------------------------------------------

def parse_price_change_pct_from_reasons(row: Dict[str, Any]) -> float:
    for reason in safe_list(row.get("reasons")):
        reason_text = clean_text(reason)
        if "price_change_pct=" in reason_text:
            try:
                return safe_float(reason_text.split("price_change_pct=")[1].split()[0].strip("|,"))
            except Exception:
                pass
    return 0.0

# ---------------------------------------------------
# EXPOSURE CHECKS
# ---------------------------------------------------

def get_side_from_direction(direction: str) -> str:
    if direction in {"bullish", "strong_bullish"}:
        return "long"
    if direction in {"bearish", "strong_bearish"}:
        return "short"
    return "flat"


def can_fit_exposure(
    cfg: Dict[str, Any],
    portfolio_ctx: Dict[str, Any],
    side: str,
    proposed_position_usd: float,
) -> Dict[str, Any]:
    equity = safe_float(portfolio_ctx.get("equity_usd"), 0.0)
    gross_exposure_usd = safe_float(portfolio_ctx.get("gross_exposure_usd"), 0.0)
    long_exposure_usd = safe_float(portfolio_ctx.get("long_exposure_usd"), 0.0)
    short_exposure_usd = safe_float(portfolio_ctx.get("short_exposure_usd"), 0.0)

    max_total = equity * safe_float(cfg.get("max_total_exposure_pct_of_equity"), 0.35)
    max_long = equity * safe_float(cfg.get("max_long_exposure_pct_of_equity"), 0.25)
    max_short = equity * safe_float(cfg.get("max_short_exposure_pct_of_equity"), 0.25)

    if gross_exposure_usd + proposed_position_usd > max_total:
        return {"allowed": False, "reason": "max_total_exposure_exceeded"}

    if side == "long" and long_exposure_usd + proposed_position_usd > max_long:
        return {"allowed": False, "reason": "max_long_exposure_exceeded"}

    if side == "short" and short_exposure_usd + proposed_position_usd > max_short:
        return {"allowed": False, "reason": "max_short_exposure_exceeded"}

    return {"allowed": True, "reason": "ok"}

# ---------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------

def build_trade_sizing(write_output: bool = True) -> Dict[str, Any]:
    cfg = load_engine_config()

    if not safe_bool(cfg.get("enabled", True), True):
        payload = {
            "schema_version": 1,
            "generated_at": utc_now_iso(),
            "system": "ToknClaw",
            "module": "trade_sizing_engine",
            "enabled": False,
            "rows": [],
        }
        if write_output:
            write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)
        return payload

    snapshot = load_trading_snapshot()
    paper_state = load_paper_state()
    strategy_performance = load_strategy_performance()
    strategy_decisions = load_strategy_decisions()

    portfolio_ctx = get_portfolio_context(paper_state)
    backtest_quality = get_backtest_quality(strategy_performance)
    market_state = safe_dict(snapshot.get("market_state"))
    trade_rows = get_current_trade_rows(snapshot)
    strategy_health_map = get_strategy_health_map(strategy_decisions)

    equity_usd = safe_float(portfolio_ctx.get("equity_usd"), 0.0)
    base_risk_pct = safe_float(cfg.get("base_risk_pct_of_equity"), 0.02)

    rows: List[Dict[str, Any]] = []

    for row in trade_rows:
        row = safe_dict(row)

        entity = clean_upper(row.get("entity"))
        direction = clean_text(row.get("direction"))
        confidence = safe_float(row.get("confidence"), 0.0)
        strategy_key = clean_text(row.get("setup_family")) or "unknown"

        side = get_side_from_direction(direction)
        if side == "flat":
            continue

        strategy_health = strategy_health_map.get(strategy_key, "unknown")
        regime_alignment = infer_regime_alignment(direction, market_state)
        abs_price_change_pct = abs(parse_price_change_pct_from_reasons(row))

        confidence_mult = get_confidence_multiplier(cfg, confidence)
        strategy_mult = get_strategy_health_multiplier(cfg, strategy_health)
        regime_mult = get_regime_multiplier(cfg, regime_alignment)
        drawdown_mult = get_drawdown_multiplier(cfg, safe_float(backtest_quality.get("max_drawdown_pct"), 0.0))
        volatility_mult = get_volatility_multiplier(cfg, abs_price_change_pct)

        raw_position_usd = equity_usd * base_risk_pct
        adjusted_position_usd = raw_position_usd
        adjusted_position_usd *= confidence_mult
        adjusted_position_usd *= strategy_mult
        adjusted_position_usd *= regime_mult
        adjusted_position_usd *= drawdown_mult
        adjusted_position_usd *= volatility_mult

        min_position_pct = safe_float(cfg.get("min_position_pct_of_equity"), 0.005)
        max_position_pct = safe_float(cfg.get("max_position_pct_of_equity"), 0.07)

        min_position_usd = equity_usd * min_position_pct
        max_position_usd = equity_usd * max_position_pct

        capped_position_usd = clamp(adjusted_position_usd, min_position_usd, max_position_usd)

        exposure_check = can_fit_exposure(cfg, portfolio_ctx, side, capped_position_usd)
        leverage_info = get_leverage_allowed(cfg, strategy_health, confidence, backtest_quality)

        if not exposure_check["allowed"]:
            final_position_usd = 0.0
            recommendation = "skip"
        else:
            final_position_usd = round(capped_position_usd, 4)
            recommendation = "size_position"

        rows.append({
            "entity": entity,
            "direction": direction,
            "side": side,
            "strategy_key": strategy_key,
            "strategy_health": strategy_health,
            "confidence": round(confidence, 4),
            "regime_alignment": regime_alignment,

            "base_position_usd": round(raw_position_usd, 4),
            "adjusted_position_usd": round(adjusted_position_usd, 4),
            "recommended_position_usd": round(final_position_usd, 4),

            "recommended_position_pct_of_equity": round(
                (final_position_usd / equity_usd) if equity_usd > 0 else 0.0,
                6,
            ),

            "multipliers": {
                "confidence": round(confidence_mult, 4),
                "strategy_health": round(strategy_mult, 4),
                "regime": round(regime_mult, 4),
                "drawdown": round(drawdown_mult, 4),
                "volatility": round(volatility_mult, 4),
            },

            "volatility_context": {
                "abs_price_change_pct": round(abs_price_change_pct, 6),
            },

            "leverage": leverage_info,
            "exposure_check": exposure_check,
            "recommendation": recommendation,
        })

    rows.sort(
        key=lambda x: (
            safe_float(x.get("recommended_position_usd"), 0.0),
            safe_float(x.get("confidence"), 0.0),
        ),
        reverse=True,
    )

    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "system": "ToknClaw",
        "module": "trade_sizing_engine",
        "enabled": True,
        "portfolio_context": {
            "equity_usd": round(safe_float(portfolio_ctx.get("equity_usd"), 0.0), 4),
            "cash_usd": round(safe_float(portfolio_ctx.get("cash_usd"), 0.0), 4),
            "gross_exposure_usd": round(safe_float(portfolio_ctx.get("gross_exposure_usd"), 0.0), 4),
            "long_exposure_usd": round(safe_float(portfolio_ctx.get("long_exposure_usd"), 0.0), 4),
            "short_exposure_usd": round(safe_float(portfolio_ctx.get("short_exposure_usd"), 0.0), 4),
            "closed_position_count": safe_int(portfolio_ctx.get("closed_position_count"), 0),
        },
        "backtest_quality": backtest_quality,
        "rows": rows,
        "summary": {
            "trade_row_count": len(trade_rows),
            "sized_row_count": sum(1 for r in rows if r.get("recommendation") == "size_position"),
            "skipped_row_count": sum(1 for r in rows if r.get("recommendation") == "skip"),
            "avg_recommended_position_usd": round(
                sum(safe_float(r.get("recommended_position_usd"), 0.0) for r in rows) / len(rows),
                4,
            ) if rows else 0.0,
            "leverage_allowed_count": sum(
                1 for r in rows if safe_bool(safe_dict(r.get("leverage")).get("allowed"), False)
            ),
        },
    }

    debug_log(
        cfg,
        f"trade_rows={len(trade_rows)} "
        f"sized={payload['summary']['sized_row_count']} "
        f"skipped={payload['summary']['skipped_row_count']} "
        f"avg_position_usd={payload['summary']['avg_recommended_position_usd']}"
    )

    if write_output:
        write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)

    return payload

# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main() -> None:
    payload = build_trade_sizing(write_output=True)

    summary = {
        "generated_at": payload.get("generated_at"),
        "equity_usd": safe_dict(payload.get("portfolio_context")).get("equity_usd"),
        "trade_row_count": safe_dict(payload.get("summary")).get("trade_row_count"),
        "sized_row_count": safe_dict(payload.get("summary")).get("sized_row_count"),
        "leverage_allowed_count": safe_dict(payload.get("summary")).get("leverage_allowed_count"),
        "avg_recommended_position_usd": safe_dict(payload.get("summary")).get("avg_recommended_position_usd"),
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
