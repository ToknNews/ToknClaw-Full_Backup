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
# MODULE: trade_leverage_engine
# PURPOSE: Compute leverage eligibility and recommended leverage for each
#          trade candidate using portfolio state, strategy health,
#          confidence, profitability, drawdown, and exposure controls.
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

from signal_engine.runtime_config import load_config

# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

CONFIG_FILE = "trade_leverage_engine.json"

SIZING_PATH = Path("/opt/toknclaw/data/analytics/trade_sizing.json")
PERFORMANCE_PATH = Path("/opt/toknclaw/data/analytics/strategy_performance.json")
DECISIONS_PATH = Path("/opt/toknclaw/data/analytics/strategy_decisions.json")
PAPER_STATE_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")

OUTPUT_PATH = Path("/opt/toknclaw/data/analytics/trade_leverage.json")
TMP_OUTPUT_PATH = Path("/opt/toknclaw/data/analytics/trade_leverage.tmp")

# ---------------------------------------------------
# DEFAULT CONFIG
# ---------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,

    "default_leverage": 1.0,
    "baseline_unlocked_leverage": 1.2,
    "max_leverage": 2.0,

    "eligibility": {
        "min_profit_factor": 1.20,
        "min_closed_trades": 50,
        "max_drawdown_pct": 3.00,
        "healthy_only": True,
        "allowed_health": ["healthy", "fragile_positive"]
    },

    "confidence_bands": [
        {"min": 0.00, "max": 0.54, "leverage": 1.00},
        {"min": 0.55, "max": 0.69, "leverage": 1.25},
        {"min": 0.70, "max": 1.00, "leverage": 1.50}
    ],

    "strategy_health_caps": {
        "healthy": 1.50,
        "fragile_positive": 1.25,
        "neutral": 1.00,
        "weak": 1.00,
        "underperforming": 1.00,
        "insufficient_sample": 1.00,
        "unknown": 1.00
    },

    "regime_caps": {
        "aligned": 1.50,
        "neutral": 1.25,
        "conflict": 1.00,
        "unknown": 1.00
    },

    "exposure": {
        "max_total_effective_exposure_pct_of_equity": 0.50,
        "max_long_effective_exposure_pct_of_equity": 0.35,
        "max_short_effective_exposure_pct_of_equity": 0.35
    },

    "openclaw_controls": {
        "adjustable_fields": [
            "baseline_unlocked_leverage",
            "max_leverage",
            "eligibility.min_profit_factor",
            "eligibility.min_closed_trades",
            "eligibility.max_drawdown_pct",
            "confidence_bands",
            "strategy_health_caps",
            "regime_caps",
            "exposure.max_total_effective_exposure_pct_of_equity",
            "exposure.max_long_effective_exposure_pct_of_equity",
            "exposure.max_short_effective_exposure_pct_of_equity"
        ],
        "mutation_policy": "config_only_with_approval"
    }
}

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def clean_text(value: Any) -> str:
    return str(value or "").strip()


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
        print(f"[TRADE LEVERAGE] {message}")


def load_engine_config() -> Dict[str, Any]:
    cfg = load_config(CONFIG_FILE)
    merged = dict(DEFAULT_CONFIG)

    if isinstance(cfg, dict):
        for key, value in cfg.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                tmp = dict(merged[key])
                tmp.update(value)
                merged[key] = tmp
            else:
                merged[key] = value

    return merged

# ---------------------------------------------------
# LOADERS
# ---------------------------------------------------

def load_trade_sizing() -> Dict[str, Any]:
    return safe_dict(read_json_file(SIZING_PATH, {}))


def load_strategy_performance() -> Dict[str, Any]:
    return safe_dict(read_json_file(PERFORMANCE_PATH, {}))


def load_strategy_decisions() -> Dict[str, Any]:
    return safe_dict(read_json_file(DECISIONS_PATH, {}))


def load_paper_state() -> Dict[str, Any]:
    return safe_dict(read_json_file(PAPER_STATE_PATH, {}))

# ---------------------------------------------------
# CONTEXT
# ---------------------------------------------------

def get_backtest_quality(strategy_performance: Dict[str, Any]) -> Dict[str, Any]:
    snap = safe_dict(strategy_performance.get("backtest_snapshot"))
    portfolio = safe_dict(snap.get("portfolio"))
    closed_summary = safe_dict(snap.get("closed_position_summary"))

    return {
        "equity_usd": safe_float(portfolio.get("equity_usd"), 0.0),
        "realized_pnl_usd": safe_float(portfolio.get("realized_pnl_usd"), 0.0),
        "profit_factor": safe_float(closed_summary.get("profit_factor"), 0.0),
        "closed_trade_count": safe_int(closed_summary.get("total_closed_positions"), 0),
        "max_drawdown_pct": safe_float(snap.get("max_drawdown_pct"), 0.0),
    }


def get_portfolio_context(paper_state: Dict[str, Any]) -> Dict[str, Any]:
    portfolio = safe_dict(paper_state.get("portfolio"))
    open_positions = safe_dict(paper_state.get("open_positions"))

    gross_exposure = safe_float(portfolio.get("gross_exposure_usd"), 0.0)
    equity = safe_float(portfolio.get("equity_usd"), 0.0)

    long_exposure = 0.0
    short_exposure = 0.0

    for _, pos in open_positions.items():
        pos = safe_dict(pos)
        side = clean_text(pos.get("side"))
        market_value = safe_float(pos.get("market_value_usd"), 0.0)

        if side == "long":
            long_exposure += market_value
        elif side == "short":
            short_exposure += market_value

    return {
        "equity_usd": equity,
        "gross_exposure_usd": gross_exposure,
        "long_exposure_usd": long_exposure,
        "short_exposure_usd": short_exposure,
    }


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
# LEVERAGE LOGIC
# ---------------------------------------------------

def get_confidence_leverage(cfg: Dict[str, Any], confidence: float) -> float:
    for band in safe_list(cfg.get("confidence_bands")):
        band = safe_dict(band)
        lo = safe_float(band.get("min"), 0.0)
        hi = safe_float(band.get("max"), 1.0)
        lev = safe_float(band.get("leverage"), 1.0)

        if confidence >= lo and confidence <= hi:
            return lev

    return safe_float(cfg.get("default_leverage"), 1.0)


def get_strategy_health_cap(cfg: Dict[str, Any], health: str) -> float:
    caps = safe_dict(cfg.get("strategy_health_caps"))
    return safe_float(caps.get(health), safe_float(caps.get("unknown"), 1.0))


def get_regime_cap(cfg: Dict[str, Any], regime_alignment: str) -> float:
    caps = safe_dict(cfg.get("regime_caps"))
    return safe_float(caps.get(regime_alignment), safe_float(caps.get("unknown"), 1.0))


def evaluate_global_eligibility(cfg: Dict[str, Any], backtest_quality: Dict[str, Any]) -> Dict[str, Any]:
    rules = safe_dict(cfg.get("eligibility"))

    pf = safe_float(backtest_quality.get("profit_factor"), 0.0)
    closed = safe_int(backtest_quality.get("closed_trade_count"), 0)
    dd = safe_float(backtest_quality.get("max_drawdown_pct"), 0.0)

    if pf < safe_float(rules.get("min_profit_factor"), 1.20):
        return {"allowed": False, "reason": "profit_factor_too_low"}

    if closed < safe_int(rules.get("min_closed_trades"), 50):
        return {"allowed": False, "reason": "insufficient_closed_trades"}

    if dd > safe_float(rules.get("max_drawdown_pct"), 3.0):
        return {"allowed": False, "reason": "drawdown_too_high"}

    return {"allowed": True, "reason": "globally_eligible"}


def evaluate_strategy_eligibility(cfg: Dict[str, Any], strategy_health: str) -> Dict[str, Any]:
    rules = safe_dict(cfg.get("eligibility"))

    if not safe_bool(rules.get("healthy_only", True), True):
        return {"allowed": True, "reason": "health_check_disabled"}

    allowed = safe_list(rules.get("allowed_health"))
    if strategy_health not in allowed:
        return {"allowed": False, "reason": "strategy_health_not_approved"}

    return {"allowed": True, "reason": "strategy_health_approved"}


def check_effective_exposure_fit(
    cfg: Dict[str, Any],
    portfolio_ctx: Dict[str, Any],
    side: str,
    recommended_position_usd: float,
    leverage: float,
) -> Dict[str, Any]:
    exposure_cfg = safe_dict(cfg.get("exposure"))

    equity = safe_float(portfolio_ctx.get("equity_usd"), 0.0)
    gross = safe_float(portfolio_ctx.get("gross_exposure_usd"), 0.0)
    long_exp = safe_float(portfolio_ctx.get("long_exposure_usd"), 0.0)
    short_exp = safe_float(portfolio_ctx.get("short_exposure_usd"), 0.0)

    added_effective = recommended_position_usd * leverage

    max_total = equity * safe_float(exposure_cfg.get("max_total_effective_exposure_pct_of_equity"), 0.50)
    max_long = equity * safe_float(exposure_cfg.get("max_long_effective_exposure_pct_of_equity"), 0.35)
    max_short = equity * safe_float(exposure_cfg.get("max_short_effective_exposure_pct_of_equity"), 0.35)

    if gross + added_effective > max_total:
        return {"allowed": False, "reason": "max_total_effective_exposure_exceeded"}

    if side == "long" and long_exp + added_effective > max_long:
        return {"allowed": False, "reason": "max_long_effective_exposure_exceeded"}

    if side == "short" and short_exp + added_effective > max_short:
        return {"allowed": False, "reason": "max_short_effective_exposure_exceeded"}

    return {"allowed": True, "reason": "effective_exposure_ok"}

# ---------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------

def build_trade_leverage(write_output: bool = True) -> Dict[str, Any]:
    cfg = load_engine_config()

    if not safe_bool(cfg.get("enabled", True), True):
        payload = {
            "schema_version": 1,
            "generated_at": utc_now_iso(),
            "system": "ToknClaw",
            "module": "trade_leverage_engine",
            "enabled": False,
            "rows": [],
        }
        if write_output:
            write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)
        return payload

    sizing_payload = load_trade_sizing()
    strategy_performance = load_strategy_performance()
    strategy_decisions = load_strategy_decisions()
    paper_state = load_paper_state()

    sizing_rows = safe_list(sizing_payload.get("rows"))
    backtest_quality = get_backtest_quality(strategy_performance)
    portfolio_ctx = get_portfolio_context(paper_state)
    strategy_health_map = get_strategy_health_map(strategy_decisions)

    global_eligibility = evaluate_global_eligibility(cfg, backtest_quality)
    max_leverage = safe_float(cfg.get("max_leverage"), 2.0)
    default_leverage = safe_float(cfg.get("default_leverage"), 1.0)
    baseline_unlocked_leverage = safe_float(cfg.get("baseline_unlocked_leverage"), 1.2)

    rows: List[Dict[str, Any]] = []

    for row in sizing_rows:
        row = safe_dict(row)

        entity = clean_text(row.get("entity"))
        direction = clean_text(row.get("direction"))
        side = clean_text(row.get("side"))
        confidence = safe_float(row.get("confidence"), 0.0)
        strategy_key = clean_text(row.get("strategy_key")) or "unknown"
        strategy_health = clean_text(row.get("strategy_health")) or strategy_health_map.get(strategy_key, "unknown")
        regime_alignment = clean_text(row.get("regime_alignment")) or "unknown"

        recommended_position_usd = safe_float(row.get("recommended_position_usd"), 0.0)

        confidence_lev = get_confidence_leverage(cfg, confidence)
        strategy_cap = get_strategy_health_cap(cfg, strategy_health)
        regime_cap = get_regime_cap(cfg, regime_alignment)

        prelim_leverage = max(baseline_unlocked_leverage, confidence_lev)
        prelim_leverage = min(prelim_leverage, strategy_cap, regime_cap, max_leverage)
        prelim_leverage = max(prelim_leverage, default_leverage)

        strategy_eligibility = evaluate_strategy_eligibility(cfg, strategy_health)

        final_allowed = True
        reasons: List[str] = []

        if not global_eligibility["allowed"]:
            final_allowed = False
            reasons.append(global_eligibility["reason"])

        if not strategy_eligibility["allowed"]:
            final_allowed = False
            reasons.append(strategy_eligibility["reason"])

        exposure_fit = check_effective_exposure_fit(
            cfg=cfg,
            portfolio_ctx=portfolio_ctx,
            side=side,
            recommended_position_usd=recommended_position_usd,
            leverage=prelim_leverage,
        )

        if not exposure_fit["allowed"]:
            final_allowed = False
            reasons.append(exposure_fit["reason"])

        if recommended_position_usd <= 0:
            final_allowed = False
            reasons.append("zero_position_size")

        if final_allowed:
            recommended_leverage = round(prelim_leverage, 4)
            effective_position_usd = round(recommended_position_usd * recommended_leverage, 4)
            reason = "approved"
        else:
            recommended_leverage = 1.0
            effective_position_usd = round(recommended_position_usd, 4)
            reason = "|".join(reasons) if reasons else "not_approved"

        rows.append({
            "entity": entity,
            "direction": direction,
            "side": side,
            "strategy_key": strategy_key,
            "strategy_health": strategy_health,
            "confidence": round(confidence, 4),
            "regime_alignment": regime_alignment,
            "base_position_usd": round(recommended_position_usd, 4),
            "recommended_leverage": recommended_leverage,
            "effective_position_usd": effective_position_usd,
            "eligibility": {
                "global": global_eligibility,
                "strategy": strategy_eligibility,
                "exposure": exposure_fit,
                "allowed": final_allowed,
                "reason": reason,
            },
            "components": {
                "baseline_unlocked_leverage": round(baseline_unlocked_leverage, 4),
                "confidence_leverage": round(confidence_lev, 4),
                "strategy_health_cap": round(strategy_cap, 4),
                "regime_cap": round(regime_cap, 4),
                "preliminary_leverage": round(prelim_leverage, 4),
            },
        })

    rows.sort(
        key=lambda x: (
            safe_bool(safe_dict(x.get("eligibility")).get("allowed"), False),
            safe_float(x.get("effective_position_usd"), 0.0),
            safe_float(x.get("confidence"), 0.0),
        ),
        reverse=True,
    )

    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "system": "ToknClaw",
        "module": "trade_leverage_engine",
        "enabled": True,
        "portfolio_context": portfolio_ctx,
        "backtest_quality": backtest_quality,
        "summary": {
            "candidate_count": len(rows),
            "leverage_allowed_count": sum(
                1 for r in rows if safe_bool(safe_dict(r.get("eligibility")).get("allowed"), False)
            ),
            "avg_recommended_leverage": round(
                sum(safe_float(r.get("recommended_leverage"), 1.0) for r in rows) / len(rows),
                4,
            ) if rows else 1.0,
        },
        "rows": rows,
    }

    debug_log(
        cfg,
        f"candidates={payload['summary']['candidate_count']} "
        f"allowed={payload['summary']['leverage_allowed_count']} "
        f"avg_leverage={payload['summary']['avg_recommended_leverage']}"
    )

    if write_output:
        write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)

    return payload

# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

def main() -> None:
    payload = build_trade_leverage(write_output=True)

    summary = {
        "generated_at": payload.get("generated_at"),
        "candidate_count": safe_dict(payload.get("summary")).get("candidate_count"),
        "leverage_allowed_count": safe_dict(payload.get("summary")).get("leverage_allowed_count"),
        "avg_recommended_leverage": safe_dict(payload.get("summary")).get("avg_recommended_leverage"),
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
