#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — RELATIVE STRENGTH TREND ENGINE
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
# MODULE: relative_strength_trend_engine
# PURPOSE:
# - Detect higher-timeframe relative strength / weakness across tradable assets
# - Capture intraday trend moves that short-cycle OI/funding logic may miss
# - Emit trend-compatible signals consumed by trade_signal_engine
# - Keep the strategy paper/live safe through existing regime, sizing, and risk gates
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from signal_engine.runtime_config import load_config


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

CONFIG_FILE = "relative_strength_trend_engine.json"

PRICE_HISTORY_PATH = Path("/opt/toknclaw/data/token_price_history.json")
SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")
UNIVERSE_PATH = Path("/opt/toknclaw/config/trading_universe.json")


# ---------------------------------------------------
# DEFAULT CONFIG
# ---------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,

    "lookback_minutes_fast": 60,
    "lookback_minutes_slow": 240,
    "lookback_minutes_day": 1440,

    "min_fast_move_pct": 0.75,
    "min_slow_move_pct": 1.25,
    "min_relative_rank_pct": 0.70,

    "max_long_funding_rate": 0.00015,
    "max_short_funding_rate": 0.00015,

    "max_outputs": 6,
    "min_confidence": 0.62,
    "max_confidence": 0.90,

    "emit_bearish": True,
    "emit_bullish": True,
}


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def safe_str(value: Any) -> str:
    return str(value or "").strip()


def safe_upper(value: Any) -> str:
    return safe_str(value).upper()


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
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
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


def load_engine_config() -> Dict[str, Any]:
    raw = load_config(CONFIG_FILE)
    cfg = dict(DEFAULT_CONFIG)

    if isinstance(raw, dict):
        cfg.update(raw)

    return cfg


def debug_log(cfg: Dict[str, Any], message: str) -> None:
    if safe_bool(cfg.get("debug"), True):
        print(f"[RELATIVE STRENGTH] {message}", flush=True)


def pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return ((current / previous) - 1.0) * 100.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------
# UNIVERSE
# ---------------------------------------------------

def enabled_assets() -> List[str]:
    cfg = safe_dict(read_json(UNIVERSE_PATH, {}))
    tiers = safe_dict(cfg.get("tiers"))
    enabled_tiers = safe_list(cfg.get("enabled_tiers"))

    assets = set()

    for tier in enabled_tiers:
        for asset in safe_list(tiers.get(tier)):
            asset = safe_upper(asset)
            if asset:
                assets.add(asset)

    return sorted(assets)


# ---------------------------------------------------
# PRICE HISTORY
# ---------------------------------------------------

def normalize_price_rows(rows: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for raw in safe_list(rows):
        row = safe_dict(raw)
        ts = parse_dt(row.get("timestamp") or row.get("ts") or row.get("time"))
        price = safe_float(row.get("price_usd") or row.get("price") or row.get("mark_price"), 0.0)

        if ts is None or price <= 0:
            continue

        out.append({
            "timestamp": ts,
            "price": price,
        })

    out.sort(key=lambda x: x["timestamp"])
    return out


def price_at_or_before(rows: List[Dict[str, Any]], target: datetime) -> Optional[float]:
    selected = None

    for row in rows:
        if row["timestamp"] <= target:
            selected = row

    if selected is None and rows:
        selected = rows[0]

    return safe_float(selected.get("price"), 0.0) if selected else None


def build_price_features(
    entity: str,
    rows: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if len(rows) < 2:
        return None

    latest = rows[-1]
    latest_price = safe_float(latest.get("price"), 0.0)
    latest_ts = latest.get("timestamp")

    if latest_price <= 0 or not isinstance(latest_ts, datetime):
        return None

    fast_minutes = safe_int(cfg.get("lookback_minutes_fast"), 60)
    slow_minutes = safe_int(cfg.get("lookback_minutes_slow"), 240)
    day_minutes = safe_int(cfg.get("lookback_minutes_day"), 1440)

    fast_price = price_at_or_before(rows, latest_ts - timedelta(minutes=fast_minutes))
    slow_price = price_at_or_before(rows, latest_ts - timedelta(minutes=slow_minutes))
    day_price = price_at_or_before(rows, latest_ts - timedelta(minutes=day_minutes))

    if not fast_price or not slow_price:
        return None

    change_fast = pct_change(latest_price, fast_price)
    change_slow = pct_change(latest_price, slow_price)
    change_day = pct_change(latest_price, day_price) if day_price else 0.0

    weighted_score = (
        change_fast * 0.50
        + change_slow * 0.35
        + change_day * 0.15
    )

    return {
        "entity": entity,
        "latest_price": round(latest_price, 12),
        "latest_timestamp": latest_ts.isoformat(),
        "change_fast_pct": round(change_fast, 6),
        "change_slow_pct": round(change_slow, 6),
        "change_day_pct": round(change_day, 6),
        "weighted_score": round(weighted_score, 6),
        "history_points": len(rows),
    }


# ---------------------------------------------------
# MARKET CONTEXT
# ---------------------------------------------------

def parse_summary_float(summary: Any, key: str, default: float = 0.0) -> float:
    text = safe_str(summary)
    if not text:
        return default

    marker = f"{key}="
    if marker not in text:
        return default

    try:
        part = text.split(marker, 1)[1]
        token = part.split()[0].strip("|,")
        return safe_float(token, default)
    except Exception:
        return default


def build_signal_context(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}

    for raw in safe_list(snapshot.get("signals")):
        row = safe_dict(raw)
        entity = safe_upper(row.get("entity"))
        st = safe_str(row.get("signal_type"))
        summary = safe_str(row.get("summary"))

        if not entity:
            continue

        bucket = out.setdefault(entity, {
            "funding_values": [],
            "oi_accel_values": [],
            "signal_types": [],
        })

        bucket["signal_types"].append(st)

        if st == "perp_funding_rate":
            avg = parse_summary_float(summary, "avg", 0.0)
            bucket["funding_values"].append(avg)

        if st == "perp_open_interest_acceleration":
            current_change = parse_summary_float(summary, "current_change_pct", 0.0)
            acceleration = parse_summary_float(summary, "acceleration_pct", 0.0)
            bucket["oi_accel_values"].append(current_change + acceleration)

    for entity, bucket in out.items():
        funding_values = bucket.get("funding_values", [])
        oi_values = bucket.get("oi_accel_values", [])

        bucket["avg_funding"] = (
            sum(funding_values) / len(funding_values)
            if funding_values else 0.0
        )

        bucket["avg_oi_accel"] = (
            sum(oi_values) / len(oi_values)
            if oi_values else 0.0
        )

    return out


# ---------------------------------------------------
# SIGNAL BUILDING
# ---------------------------------------------------

def relative_rank(value: float, values: List[float], bullish: bool) -> float:
    if not values:
        return 0.0

    if bullish:
        count = sum(1 for x in values if x <= value)
    else:
        count = sum(1 for x in values if x >= value)

    return count / len(values)


def confidence_from_rank(rank: float, abs_score: float, cfg: Dict[str, Any]) -> float:
    min_conf = safe_float(cfg.get("min_confidence"), 0.62)
    max_conf = safe_float(cfg.get("max_confidence"), 0.90)

    score_component = clamp(abs_score / 6.0, 0.0, 1.0)
    confidence = min_conf + ((rank * 0.60 + score_component * 0.40) * (max_conf - min_conf))

    return round(clamp(confidence, min_conf, max_conf), 6)

def recent_position_context(
    entity: str,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    price_history = safe_dict(read_json(PRICE_HISTORY_PATH, {}))
    tokens = safe_dict(price_history.get("tokens"))
    rows = normalize_price_rows(tokens.get(entity))

    if not rows:
        return {
            "ok": False,
            "reason": "no_recent_price_rows",
        }

    latest = rows[-1]
    latest_ts = latest.get("timestamp")
    latest_price = safe_float(latest.get("price"), 0.0)

    if not isinstance(latest_ts, datetime) or latest_price <= 0:
        return {
            "ok": False,
            "reason": "invalid_latest_price",
        }

    window_minutes = safe_int(cfg.get("continuation_window_minutes"), 30)
    recent = [
        row for row in rows
        if row["timestamp"] >= latest_ts - timedelta(minutes=window_minutes)
    ]

    if len(recent) < 2:
        return {
            "ok": False,
            "reason": "insufficient_recent_window",
        }

    first_price = safe_float(recent[0].get("price"), 0.0)
    high_price = max(safe_float(row.get("price"), 0.0) for row in recent)
    low_price = min(safe_float(row.get("price"), 0.0) for row in recent)

    change_pct = pct_change(latest_price, first_price)
    from_high_pct = pct_change(latest_price, high_price)
    from_low_pct = pct_change(latest_price, low_price)

    return {
        "ok": True,
        "window_minutes": window_minutes,
        "latest_price": round(latest_price, 12),
        "change_pct": round(change_pct, 6),
        "from_high_pct": round(from_high_pct, 6),
        "from_low_pct": round(from_low_pct, 6),
        "high_price": round(high_price, 12),
        "low_price": round(low_price, 12),
    }

def build_signal(
    feature: Dict[str, Any],
    context: Dict[str, Any],
    rank: float,
    direction: str,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    entity = safe_upper(feature.get("entity"))
    score = safe_float(feature.get("weighted_score"), 0.0)
    abs_score = abs(score)

    confidence = confidence_from_rank(rank, abs_score, cfg)

    if direction == "bullish":
        signal_type = "perp_trend_bullish"
        title = f"{entity} relative strength trend bullish"
    else:
        signal_type = "perp_trend_bearish"
        title = f"{entity} relative weakness trend bearish"

    avg_funding = safe_float(context.get("avg_funding"), 0.0)
    avg_oi_accel = safe_float(context.get("avg_oi_accel"), 0.0)

    summary = (
        f"source=relative_strength_trend "
        f"rank={rank:.4f} "
        f"weighted_score={score:.4f} "
        f"fast_change_pct={safe_float(feature.get('change_fast_pct'), 0.0):.4f} "
        f"slow_change_pct={safe_float(feature.get('change_slow_pct'), 0.0):.4f} "
        f"day_change_pct={safe_float(feature.get('change_day_pct'), 0.0):.4f} "
        f"avg_funding={avg_funding:.8f} "
        f"avg_oi_accel={avg_oi_accel:.4f}"
    )

    return {
        "timestamp": utc_now_iso(),
        "source": "relative_strength_trend_engine",
        "signal_type": signal_type,
        "entity": entity,
        "title": title,
        "summary": summary,
        "confidence": confidence,
        "metadata": {
            "strategy_family": "relative_strength_trend",
            "relative_rank": round(rank, 6),
            "weighted_score": round(score, 6),
            "change_fast_pct": feature.get("change_fast_pct"),
            "change_slow_pct": feature.get("change_slow_pct"),
            "change_day_pct": feature.get("change_day_pct"),
            "latest_price": feature.get("latest_price"),
            "latest_timestamp": feature.get("latest_timestamp"),
            "avg_funding": avg_funding,
            "avg_oi_accel": avg_oi_accel,
        },
    }


# ---------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------

def build_relative_strength_trend() -> List[Dict[str, Any]]:
    cfg = load_engine_config()

    if not safe_bool(cfg.get("enabled"), True):
        return []

    price_history = safe_dict(read_json(PRICE_HISTORY_PATH, {}))
    tokens = safe_dict(price_history.get("tokens"))
    snapshot = safe_dict(read_json(SNAPSHOT_PATH, {}))
    context_map = build_signal_context(snapshot)

    assets = enabled_assets()

    features: List[Dict[str, Any]] = []

    for entity in assets:
        rows = normalize_price_rows(tokens.get(entity))

        feature = build_price_features(entity, rows, cfg)
        if feature:
            features.append(feature)

    if not features:
        debug_log(cfg, "no usable price features")
        return []

    scores = [safe_float(x.get("weighted_score"), 0.0) for x in features]

    min_fast_move = safe_float(cfg.get("min_fast_move_pct"), 0.75)
    min_slow_move = safe_float(cfg.get("min_slow_move_pct"), 1.25)
    min_rank = safe_float(cfg.get("min_relative_rank_pct"), 0.70)
    max_long_funding = safe_float(cfg.get("max_long_funding_rate"), 0.00015)
    max_short_funding = safe_float(cfg.get("max_short_funding_rate"), 0.00015)
    max_outputs = safe_int(cfg.get("max_outputs"), 6)

    candidates: List[Dict[str, Any]] = []

    for feature in features:
        entity = safe_upper(feature.get("entity"))
        score = safe_float(feature.get("weighted_score"), 0.0)
        fast = safe_float(feature.get("change_fast_pct"), 0.0)
        slow = safe_float(feature.get("change_slow_pct"), 0.0)

        context = safe_dict(context_map.get(entity))
        avg_funding = safe_float(context.get("avg_funding"), 0.0)

        bull_rank = relative_rank(score, scores, bullish=True)
        bear_rank = relative_rank(score, scores, bullish=False)

        recent_context = recent_position_context(entity, cfg)

        bullish_recent_ok = False
        if recent_context.get("ok"):
            max_pullback = safe_float(cfg.get("max_bullish_pullback_from_high_pct"), 0.35)
            min_from_low = safe_float(cfg.get("min_bullish_position_from_low_pct"), 0.15)

            from_high_pct = safe_float(recent_context.get("from_high_pct"), 0.0)
            from_low_pct = safe_float(recent_context.get("from_low_pct"), 0.0)

            bullish_recent_ok = (
                from_high_pct >= -abs(max_pullback)
                and from_low_pct >= min_from_low
            )

        if (
            safe_bool(cfg.get("emit_bullish"), True)
            and fast >= min_fast_move
            and slow >= min_slow_move
            and bull_rank >= min_rank
            and avg_funding <= max_long_funding
            and bullish_recent_ok
        ):
            signal = build_signal(
                feature=feature,
                context=context,
                rank=bull_rank,
                direction="bullish",
                cfg=cfg,
            )
            signal.setdefault("metadata", {})["recent_position_context"] = recent_context
            candidates.append(signal)

        if (
            safe_bool(cfg.get("emit_bearish"), True)
            and fast <= -min_fast_move
            and slow <= -min_slow_move
            and bear_rank >= min_rank
            and abs(avg_funding) <= max_short_funding
        ):
            candidates.append(build_signal(
                feature=feature,
                context=context,
                rank=bear_rank,
                direction="bearish",
                cfg=cfg,
            ))

    candidates.sort(
        key=lambda row: (
            safe_float(row.get("confidence"), 0.0),
            abs(parse_summary_float(row.get("summary"), "weighted_score", 0.0)),
        ),
        reverse=True,
    )

    out = candidates[:max_outputs]

    debug_log(
        cfg,
        f"assets={len(assets)} features={len(features)} candidates={len(out)}"
    )

    return out


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    rows = build_relative_strength_trend()
    print(json.dumps(rows, indent=2))
