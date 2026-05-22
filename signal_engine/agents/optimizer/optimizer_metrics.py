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
# MODULE: optimizer_metrics
# PURPOSE: Compute bounded performance metrics from paper trading state and
#          latest trading snapshot for optimizer analysis.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

This module is designed to:
• load recent closed paper trades
• compute pnl and win-rate metrics
• bucket results by entity, direction, and signal reason
• derive confidence calibration metrics
• remain additive and OpenClaw agent ready
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List


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


def parse_dt(value: Any) -> datetime | None:
    text = clean_text(value)
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


def _new_bucket() -> Dict[str, Any]:
    return {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "flat": 0,
        "realized_pnl_usd": 0.0,
        "avg_realized_pnl_usd": 0.0,
        "avg_realized_pnl_pct": 0.0,
        "avg_confidence": 0.0,
        "_confidence_total": 0.0,
        "_pnl_pct_total": 0.0,
    }


def _finalize_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
    count = safe_int(bucket.get("count", 0), 0)
    if count > 0:
        bucket["avg_realized_pnl_usd"] = round(
            safe_float(bucket.get("realized_pnl_usd", 0.0), 0.0) / count, 6
        )
        bucket["avg_realized_pnl_pct"] = round(
            safe_float(bucket.get("_pnl_pct_total", 0.0), 0.0) / count, 6
        )
        bucket["avg_confidence"] = round(
            safe_float(bucket.get("_confidence_total", 0.0), 0.0) / count, 6
        )
        bucket["win_rate"] = round(safe_int(bucket.get("wins", 0), 0) / count, 6)
    else:
        bucket["win_rate"] = 0.0

    bucket.pop("_confidence_total", None)
    bucket.pop("_pnl_pct_total", None)
    return bucket


def _update_bucket(
    bucket: Dict[str, Any],
    realized_pnl_usd: float,
    realized_pnl_pct: float,
    confidence: float,
) -> None:
    bucket["count"] = safe_int(bucket.get("count", 0), 0) + 1
    bucket["realized_pnl_usd"] = round(
        safe_float(bucket.get("realized_pnl_usd", 0.0), 0.0) + realized_pnl_usd,
        6,
    )
    bucket["_pnl_pct_total"] = round(
        safe_float(bucket.get("_pnl_pct_total", 0.0), 0.0) + realized_pnl_pct,
        6,
    )
    bucket["_confidence_total"] = round(
        safe_float(bucket.get("_confidence_total", 0.0), 0.0) + confidence,
        6,
    )

    if realized_pnl_usd > 0:
        bucket["wins"] = safe_int(bucket.get("wins", 0), 0) + 1
    elif realized_pnl_usd < 0:
        bucket["losses"] = safe_int(bucket.get("losses", 0), 0) + 1
    else:
        bucket["flat"] = safe_int(bucket.get("flat", 0), 0) + 1


def _confidence_band(confidence: float) -> str:
    if confidence >= 0.75:
        return "0.75-1.00"
    if confidence >= 0.50:
        return "0.50-0.74"
    if confidence >= 0.25:
        return "0.25-0.49"
    return "0.00-0.24"


def select_recent_closed_positions(
    paper_state: Dict[str, Any],
    max_closed_positions: int,
    max_days: int,
) -> List[Dict[str, Any]]:
    rows = [
        x for x in safe_list(paper_state.get("closed_positions"))
        if isinstance(x, dict)
    ]

    if not rows:
        return []

    cutoff = datetime.now(UTC) - timedelta(days=max_days)

    filtered = []
    for row in rows:
        closed_at = parse_dt(row.get("closed_at"))
        if closed_at is None:
            continue
        if closed_at < cutoff:
            continue
        filtered.append(row)

    filtered.sort(key=lambda x: clean_text(x.get("closed_at")))
    return filtered[-max_closed_positions:]


def compute_optimizer_metrics(
    paper_state: Dict[str, Any],
    trading_snapshot: Dict[str, Any],
    optimizer_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    lookback = safe_dict(optimizer_cfg.get("lookback"))
    max_closed_positions = safe_int(lookback.get("max_closed_positions", 200), 200)
    max_days = safe_int(lookback.get("max_days", 14), 14)

    closed_positions = select_recent_closed_positions(
        paper_state=paper_state,
        max_closed_positions=max_closed_positions,
        max_days=max_days,
    )

    overall = _new_bucket()
    by_entity: Dict[str, Dict[str, Any]] = {}
    by_direction: Dict[str, Dict[str, Any]] = {}
    by_reason: Dict[str, Dict[str, Any]] = {}
    by_close_reason: Dict[str, Dict[str, Any]] = {}
    by_confidence_band: Dict[str, Dict[str, Any]] = {}

    for row in closed_positions:
        entity = clean_upper(row.get("entity"))
        direction = clean_text(row.get("direction"))
        close_reason = clean_text(row.get("close_reason"))
        signal_copy = safe_dict(row.get("signal_copy"))
        confidence = safe_float(row.get("confidence", signal_copy.get("confidence", 0.0)), 0.0)
        reasons = [clean_text(x) for x in safe_list(signal_copy.get("reasons")) if clean_text(x)]

        realized_pnl_usd = safe_float(row.get("realized_pnl_usd"), 0.0)
        realized_pnl_pct = safe_float(row.get("realized_pnl_pct"), 0.0)

        _update_bucket(overall, realized_pnl_usd, realized_pnl_pct, confidence)

        bucket = by_entity.setdefault(entity, _new_bucket())
        _update_bucket(bucket, realized_pnl_usd, realized_pnl_pct, confidence)

        bucket = by_direction.setdefault(direction, _new_bucket())
        _update_bucket(bucket, realized_pnl_usd, realized_pnl_pct, confidence)

        bucket = by_close_reason.setdefault(close_reason, _new_bucket())
        _update_bucket(bucket, realized_pnl_usd, realized_pnl_pct, confidence)

        band = _confidence_band(confidence)
        bucket = by_confidence_band.setdefault(band, _new_bucket())
        _update_bucket(bucket, realized_pnl_usd, realized_pnl_pct, confidence)

        for reason in reasons:
            bucket = by_reason.setdefault(reason, _new_bucket())
            _update_bucket(bucket, realized_pnl_usd, realized_pnl_pct, confidence)

    overall = _finalize_bucket(overall)
    by_entity = {k: _finalize_bucket(v) for k, v in by_entity.items()}
    by_direction = {k: _finalize_bucket(v) for k, v in by_direction.items()}
    by_reason = {k: _finalize_bucket(v) for k, v in by_reason.items()}
    by_close_reason = {k: _finalize_bucket(v) for k, v in by_close_reason.items()}
    by_confidence_band = {k: _finalize_bucket(v) for k, v in by_confidence_band.items()}

    latest_trade_rows = safe_list(safe_dict(trading_snapshot.get("trade_signals")).get("rows"))
    latest_open_positions = safe_dict(paper_state.get("open_positions"))

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "sample": {
            "closed_positions_considered": len(closed_positions),
            "open_positions_current": len(latest_open_positions),
        },
        "overall": overall,
        "by_entity": by_entity,
        "by_direction": by_direction,
        "by_reason": by_reason,
        "by_close_reason": by_close_reason,
        "by_confidence_band": by_confidence_band,
        "latest_market_state": {
            "top_trade_rows": latest_trade_rows[:10],
            "trade_signal_summary": safe_dict(safe_dict(trading_snapshot.get("trade_signals")).get("summary")),
            "paper_trading_summary": safe_dict(safe_dict(paper_state.get("summary"))),
        },
    }
