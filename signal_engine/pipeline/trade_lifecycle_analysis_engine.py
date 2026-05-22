#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — TRADE LIFECYCLE ANALYSIS ENGINE
# ============================================================
#
# SYSTEM: ToknClaw Research Intelligence Layer
# MODULE: trade_lifecycle_analysis_engine
# PURPOSE:
# - Analyze why paper trades entered
# - Measure realized result
# - Reconstruct what happened during the trade
# - Reconstruct what happened after exit
# - Label whether exits were early, late, good, or inconclusive
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path("/opt/toknclaw")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CONFIG_PATH = Path("/opt/toknclaw/config/trade_lifecycle_analysis_engine.json")
STATE_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")
PRICE_PATH = Path("/opt/toknclaw/data/token_price_history.json")
OUT_PATH = Path("/opt/toknclaw/data/analytics/trade_lifecycle_analysis.json")
OUT_TMP_PATH = Path("/opt/toknclaw/data/analytics/trade_lifecycle_analysis.tmp")


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "checkpoint_path": "/opt/toknclaw/data/analytics/performance_checkpoint.json",
    "post_exit_windows_minutes": [15, 30, 60, 120],
    "minimum_price_points_required": 5,
    "max_closed_trades_to_analyze": 1000,
    "exit_quality_thresholds": {
        "missed_upside_usd": 1.0,
        "saved_loss_usd": 1.0,
        "bad_hold_extra_loss_usd": 1.0,
        "mfe_large_usd": 2.0,
        "mae_large_usd": 2.0
    }
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def safe_str(value: Any) -> str:
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

    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False

    if isinstance(value, (int, float)):
        return bool(value)

    return default


def parse_dt(value: Any) -> Optional[datetime]:
    text = safe_str(value)
    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)

        return dt.astimezone(UTC)

    except Exception:
        return None


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    raw = read_json(CONFIG_PATH, {})

    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                merged = dict(cfg[key])
                merged.update(value)
                cfg[key] = merged
            else:
                cfg[key] = value

    return cfg


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if safe_bool(cfg.get("debug"), True):
        print(f"[TRADE LIFECYCLE] {message}", flush=True)


def normalize_price_rows(rows: Any) -> List[Tuple[datetime, float]]:
    out: List[Tuple[datetime, float]] = []

    for raw in safe_list(rows):
        row = safe_dict(raw)
        ts = parse_dt(row.get("timestamp"))
        price = safe_float(row.get("price_usd"), 0.0)

        if ts is not None and price > 0:
            out.append((ts, price))

    out.sort(key=lambda item: item[0])
    return out


def pnl_for(side: str, entry_price: float, mark_price: float, quantity: float) -> float:
    side = safe_str(side).lower()

    if side == "long":
        return (mark_price - entry_price) * quantity

    if side == "short":
        return (entry_price - mark_price) * quantity

    return 0.0


def price_at_or_after(rows: List[Tuple[datetime, float]], target: datetime) -> Tuple[Optional[datetime], Optional[float]]:
    for ts, price in rows:
        if ts >= target:
            return ts, price

    return None, None


def prices_between(rows: List[Tuple[datetime, float]], start: datetime, end: datetime) -> List[Tuple[datetime, float]]:
    return [
        (ts, price)
        for ts, price in rows
        if start <= ts <= end
    ]


def rank_bucket(value: Any) -> str:
    score = safe_float(value, 0.0)

    if score >= 0.75:
        return "rank>=0.75"

    if score >= 0.50:
        return "rank_0.50_0.75"

    if score >= 0.25:
        return "rank_0.25_0.50"

    if score > 0:
        return "rank_0_0.25"

    return "unranked"


def duration_bucket(seconds: Any) -> str:
    sec = safe_float(seconds, 0.0)

    if sec < 300:
        return "<5m"

    if sec < 900:
        return "5_15m"

    if sec < 1800:
        return "15_30m"

    if sec < 3600:
        return "30_60m"

    if sec < 7200:
        return "1_2h"

    return "2h+"


def market_quality_bucket(value: Any) -> str:
    text = safe_str(value)
    return text if text else "missing"


def shadow_bucket(position: Dict[str, Any]) -> str:
    return "shadow" if safe_bool(position.get("research_shadow"), False) else "eligible"


def analyze_trade(
    trade: Dict[str, Any],
    price_rows: List[Tuple[datetime, float]],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    opened_at = parse_dt(trade.get("opened_at"))
    closed_at = parse_dt(trade.get("closed_at"))

    entity = safe_str(trade.get("entity")).upper()
    side = safe_str(trade.get("side")).lower()
    strategy = safe_str(trade.get("strategy") or trade.get("setup_family"))
    entry_price = safe_float(trade.get("entry_price_usd"), 0.0)
    exit_price = safe_float(trade.get("exit_price_usd"), 0.0)
    quantity = safe_float(trade.get("quantity"), 0.0)
    realized_pnl = safe_float(trade.get("realized_pnl_usd"), 0.0)

    base = {
        "trade_id": trade.get("trade_id"),
        "entity": entity,
        "side": side,
        "strategy": strategy,
        "setup_family": trade.get("setup_family"),
        "opened_at": trade.get("opened_at"),
        "closed_at": trade.get("closed_at"),
        "duration_sec": safe_float(trade.get("duration_sec"), 0.0),
        "duration_bucket": duration_bucket(trade.get("duration_sec")),
        "entry_price_usd": entry_price,
        "exit_price_usd": exit_price,
        "quantity": quantity,
        "realized_pnl_usd": round(realized_pnl, 4),
        "close_reason": trade.get("close_reason"),

        "paper_trade_only": safe_bool(trade.get("paper_trade_only"), False),
        "research_shadow": safe_bool(trade.get("research_shadow"), False),
        "shadow_bucket": shadow_bucket(trade),

        "asset_rotation_rank_score": safe_float(trade.get("asset_rotation_rank_score"), 0.0),
        "asset_rotation_eligibility": trade.get("asset_rotation_eligibility"),
        "rank_bucket": rank_bucket(trade.get("asset_rotation_rank_score")),

        "market_quality_status": market_quality_bucket(trade.get("market_quality_status")),
        "market_quality_score": safe_float(trade.get("market_quality_score"), 0.0),

        "entry_reasons": safe_list(trade.get("entry_reasons")),
        "entry_score_breakdown": safe_dict(trade.get("entry_score_breakdown")),
        "entry_family_breakdown": safe_dict(trade.get("entry_family_breakdown")),
    }

    if opened_at is None or closed_at is None:
        base["analysis_status"] = "missing_open_or_close_time"
        base["exit_quality"] = "insufficient_data"
        return base

    if entry_price <= 0 or quantity <= 0:
        base["analysis_status"] = "missing_entry_or_quantity"
        base["exit_quality"] = "insufficient_data"
        return base

    min_points = safe_int(cfg.get("minimum_price_points_required"), 5)

    in_trade_prices = prices_between(price_rows, opened_at, closed_at)

    if len(in_trade_prices) < min_points:
        base["analysis_status"] = "insufficient_in_trade_price_data"
        base["exit_quality"] = "insufficient_data"
        base["in_trade_price_points"] = len(in_trade_prices)
        return base

    pnl_path = [
        {
            "timestamp": ts.isoformat(),
            "price": price,
            "pnl_usd": pnl_for(side, entry_price, price, quantity),
        }
        for ts, price in in_trade_prices
    ]

    best_point = max(pnl_path, key=lambda row: row["pnl_usd"])
    worst_point = min(pnl_path, key=lambda row: row["pnl_usd"])

    mfe_usd = safe_float(best_point.get("pnl_usd"), 0.0)
    mae_usd = safe_float(worst_point.get("pnl_usd"), 0.0)

    base["analysis_status"] = "ok"
    base["in_trade_price_points"] = len(in_trade_prices)
    base["mfe_usd"] = round(mfe_usd, 4)
    base["mae_usd"] = round(mae_usd, 4)
    base["mfe_price"] = round(safe_float(best_point.get("price"), 0.0), 12)
    base["mae_price"] = round(safe_float(worst_point.get("price"), 0.0), 12)
    base["time_to_mfe_sec"] = round((parse_dt(best_point.get("timestamp")) - opened_at).total_seconds(), 4) if parse_dt(best_point.get("timestamp")) else None
    base["time_to_mae_sec"] = round((parse_dt(worst_point.get("timestamp")) - opened_at).total_seconds(), 4) if parse_dt(worst_point.get("timestamp")) else None

    post_exit: Dict[str, Any] = {}

    for minutes in safe_list(cfg.get("post_exit_windows_minutes")):
        window = safe_int(minutes, 0)
        if window <= 0:
            continue

        target = closed_at + timedelta(minutes=window)
        post_ts, post_price = price_at_or_after(price_rows, target)

        key = f"post_exit_{window}m"

        if post_ts is None or post_price is None:
            post_exit[key] = {
                "available": False,
                "reason": "no_price_after_target",
            }
            continue

        hypothetical_pnl = pnl_for(side, entry_price, post_price, quantity)

        post_exit[key] = {
            "available": True,
            "timestamp": post_ts.isoformat(),
            "price": round(post_price, 12),
            "hypothetical_pnl_usd": round(hypothetical_pnl, 4),
            "delta_vs_actual_usd": round(hypothetical_pnl - realized_pnl, 4),
        }

    base["post_exit"] = post_exit
    base["exit_quality"] = classify_exit_quality(base, cfg)

    return base


def classify_exit_quality(row: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    thresholds = safe_dict(cfg.get("exit_quality_thresholds"))

    missed_upside = safe_float(thresholds.get("missed_upside_usd"), 1.0)
    saved_loss = safe_float(thresholds.get("saved_loss_usd"), 1.0)
    bad_hold_extra_loss = safe_float(thresholds.get("bad_hold_extra_loss_usd"), 1.0)
    mfe_large = safe_float(thresholds.get("mfe_large_usd"), 2.0)

    realized = safe_float(row.get("realized_pnl_usd"), 0.0)
    mfe = safe_float(row.get("mfe_usd"), 0.0)
    mae = safe_float(row.get("mae_usd"), 0.0)
    close_reason = safe_str(row.get("close_reason"))

    post_values = []

    for _, payload in safe_dict(row.get("post_exit")).items():
        payload = safe_dict(payload)
        if not safe_bool(payload.get("available"), False):
            continue
        post_values.append(safe_float(payload.get("delta_vs_actual_usd"), 0.0))

    best_post_delta = max(post_values) if post_values else 0.0
    worst_post_delta = min(post_values) if post_values else 0.0

    if close_reason == "take_profit" and best_post_delta > missed_upside:
        return "take_profit_too_early"

    if close_reason in {"neutral_signal", "direction_flip"} and best_post_delta > missed_upside:
        return "exited_too_early"

    if close_reason == "stop_loss" and worst_post_delta < -bad_hold_extra_loss:
        return "stop_saved_larger_loss"

    if close_reason == "stop_loss" and best_post_delta > missed_upside:
        return "stop_too_tight"

    if realized < 0 and mfe >= mfe_large:
        return "gave_back_winner"

    if realized > 0 and worst_post_delta < -saved_loss:
        return "good_exit_saved_profit"

    if realized < 0 and mae < -abs(safe_float(row.get("market_quality_score"), 0.0)) and best_post_delta <= 0:
        return "bad_entry_or_bad_direction"

    return "neutral_or_inconclusive"


def summarize_rows(rows: List[Dict[str, Any]], key_fields: List[str]) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[float]] = defaultdict(list)

    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        buckets[str(key)].append(safe_float(row.get("realized_pnl_usd"), 0.0))

    out = []

    for key, pnls in buckets.items():
        count = len(pnls)
        total = sum(pnls)
        wins = sum(1 for value in pnls if value > 0)
        losses = sum(1 for value in pnls if value < 0)

        out.append({
            "key": key,
            "count": count,
            "total_pnl_usd": round(total, 4),
            "avg_pnl_usd": round(total / count, 4) if count else 0.0,
            "win_rate": round(wins / count, 4) if count else 0.0,
            "avg_win_usd": round(sum(value for value in pnls if value > 0) / wins, 4) if wins else 0.0,
            "avg_loss_usd": round(sum(value for value in pnls if value < 0) / losses, 4) if losses else 0.0,
        })

    out.sort(key=lambda row: (row["total_pnl_usd"], row["count"]), reverse=True)

    return out


def build_trade_lifecycle_analysis() -> Dict[str, Any]:
    cfg = load_config()

    state = safe_dict(read_json(STATE_PATH, {}))
    price_data = safe_dict(read_json(PRICE_PATH, {}))
    prices = safe_dict(price_data.get("tokens"))

    checkpoint = safe_dict(read_json(Path(safe_str(cfg.get("checkpoint_path"))), {}))
    checkpoint_at = parse_dt(checkpoint.get("created_at"))

    max_closed = safe_int(cfg.get("max_closed_trades_to_analyze"), 1000)

    closed_positions = safe_list(state.get("closed_positions"))[-max_closed:]

    analyzed = []

    for trade in closed_positions:
        trade = safe_dict(trade)

        opened_at = parse_dt(trade.get("opened_at"))
        closed_at = parse_dt(trade.get("closed_at"))

        if checkpoint_at is not None:
            if opened_at is None or closed_at is None:
                continue

            if opened_at < checkpoint_at or closed_at < checkpoint_at:
                continue

        entity = safe_str(trade.get("entity")).upper()
        price_rows = normalize_price_rows(prices.get(entity))

        analyzed.append(analyze_trade(trade, price_rows, cfg))

    ok_rows = [
        row for row in analyzed
        if safe_str(row.get("analysis_status")) == "ok"
    ]

    payload = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "system": "ToknClaw",
        "module": "trade_lifecycle_analysis_engine",
        "checkpoint": checkpoint,
        "summary": {
            "closed_considered": len(analyzed),
            "analysis_ok": len(ok_rows),
            "insufficient_data": len(analyzed) - len(ok_rows),
        },
        "grouped": {
            "by_exit_quality": summarize_rows(ok_rows, ["exit_quality"]),
            "by_shadow": summarize_rows(ok_rows, ["shadow_bucket"]),
            "by_side": summarize_rows(ok_rows, ["side"]),
            "by_market_quality": summarize_rows(ok_rows, ["market_quality_status"]),
            "by_rank_bucket": summarize_rows(ok_rows, ["rank_bucket"]),
            "by_close_reason": summarize_rows(ok_rows, ["close_reason"]),
            "by_duration_bucket": summarize_rows(ok_rows, ["duration_bucket"]),
            "by_entity_side": summarize_rows(ok_rows, ["entity", "side"]),
            "by_shadow_mq_side": summarize_rows(ok_rows, ["shadow_bucket", "market_quality_status", "side"]),
        },
        "rows": analyzed,
    }

    write_json_atomic(OUT_PATH, OUT_TMP_PATH, payload)

    debug_log(
        cfg,
        f"closed={len(analyzed)} ok={len(ok_rows)} output={OUT_PATH}"
    )

    return payload


def main() -> None:
    payload = build_trade_lifecycle_analysis()

    print(json.dumps({
        "generated_at": payload.get("generated_at"),
        "summary": payload.get("summary"),
        "grouped": {
            "by_exit_quality": safe_list(safe_dict(payload.get("grouped")).get("by_exit_quality"))[:20],
            "by_shadow": safe_list(safe_dict(payload.get("grouped")).get("by_shadow"))[:20],
            "by_side": safe_list(safe_dict(payload.get("grouped")).get("by_side"))[:20],
            "by_market_quality": safe_list(safe_dict(payload.get("grouped")).get("by_market_quality"))[:20],
            "by_entity_side": safe_list(safe_dict(payload.get("grouped")).get("by_entity_side"))[:30],
        },
        "output": str(OUT_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
