#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — ASSET ROTATION RANKER
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
# MODULE: asset_rotation_ranker
# PURPOSE:
# - Rank all enabled Hyperliquid assets by current opportunity quality
# - Compare open positions against new candidates
# - Identify paper-only discovery candidates without automatically trading them live
# - Produce a durable ranking artifact for paper trading, OpenClaw, and future live gating
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

PROJECT_ROOT = Path("/opt/toknclaw")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from signal_engine.runtime_config import load_config


CONFIG_FILE = "asset_rotation_ranker.json"

PRICE_PATH = Path("/opt/toknclaw/data/token_price_history.json")
SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot_trading.json")
STATE_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")
UNIVERSE_PATH = Path("/opt/toknclaw/config/trading_universe.json")
MARKET_QUALITY_PATH = Path("/opt/toknclaw/data/analytics/hyperliquid_market_quality.json")
STRATEGY_POLICY_PATH = Path("/opt/toknclaw/config/strategy_policy.json")

OUTPUT_PATH = Path("/opt/toknclaw/data/analytics/asset_rotation_ranker.json")
TMP_OUTPUT_PATH = Path("/opt/toknclaw/data/analytics/asset_rotation_ranker.tmp")


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "debug": True,
    "lookback_minutes": 30,
    "max_ranked_assets": 50,
    "weights": {
        "price_momentum": 0.35,
        "near_high": 0.15,
        "trade_signal": 0.25,
        "universe_tier": 0.10,
        "market_quality": 0.15
    },
    "tier_scores": {
        "majors": 1.0,
        "midcaps": 0.85,
        "paper_candidates": 0.65,
        "unknown": 0.35
    },
    "minimum_paper_candidate_30m_change_pct": 2.5,
    "minimum_live_candidate_30m_change_pct": 0.5,
    "maximum_pullback_from_high_pct": 0.5,
    "minimum_market_quality_score": 0.35,
    "block_unavailable_market_quality": True,
    "penalize_thin_markets": True,
    "rotation": {
        "enabled": True,
        "minimum_rank_improvement": 0.25,
        "minimum_unrealized_pnl_to_replace": -1.0,
        "protect_profitable_positions": True
    }
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


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


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def load_engine_config() -> Dict[str, Any]:
    raw = load_config(CONFIG_FILE)
    cfg = dict(DEFAULT_CONFIG)

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
        print(f"[ASSET ROTATION] {message}", flush=True)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return ((current / previous) - 1.0) * 100.0


def normalize_price_rows(rows: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for raw in safe_list(rows):
        row = safe_dict(raw)
        ts = parse_dt(row.get("timestamp"))
        price = safe_float(row.get("price_usd"), 0.0)

        if ts is None or price <= 0:
            continue

        out.append({
            "timestamp": ts,
            "price": price,
            "source": safe_str(row.get("source")),
        })

    out.sort(key=lambda x: x["timestamp"])
    return out


def universe_context() -> Dict[str, Dict[str, Any]]:
    cfg = safe_dict(read_json(UNIVERSE_PATH, {}))
    tiers = safe_dict(cfg.get("tiers"))
    paper_tiers = set(safe_list(cfg.get("paper_trade_only_tiers")))

    out: Dict[str, Dict[str, Any]] = {}

    for tier_name, assets in tiers.items():
        tier_name = safe_str(tier_name)
        for asset in safe_list(assets):
            entity = safe_upper(asset)
            if not entity:
                continue

            out[entity] = {
                "tier": tier_name,
                "paper_trade_only": tier_name in paper_tiers,
            }

    return out

def load_strategy_policy() -> Dict[str, Any]:
    policy = safe_dict(read_json(STRATEGY_POLICY_PATH, {}))

    if not policy:
        return {
            "enabled": False,
            "default_mode": "allow",
            "strategies": {},
            "paper_candidate_policy": {},
        }

    return policy


def strategy_policy_for(strategy: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    strategy = safe_str(strategy) or "unknown"

    strategies = safe_dict(policy.get("strategies"))
    default_mode = safe_str(policy.get("default_mode")) or "observe_only"

    row = safe_dict(strategies.get(strategy))

    if row:
        return row

    return {
        "mode": default_mode,
        "reason": "No explicit strategy policy found.",
    }


def side_from_signal_direction(signal_direction: str) -> str:
    signal_direction = safe_str(signal_direction).lower()

    if signal_direction == "bullish":
        return "long"

    if signal_direction == "bearish":
        return "short"

    return "unknown"

def market_quality_map() -> Dict[str, Dict[str, Any]]:
    payload = safe_dict(read_json(MARKET_QUALITY_PATH, {}))
    out: Dict[str, Dict[str, Any]] = {}

    for row in safe_list(payload.get("rows")):
        row = safe_dict(row)
        entity = safe_upper(row.get("entity"))

        if entity:
            out[entity] = row

    return out

def latest_trade_signal_map(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}

    for row in safe_list(safe_dict(snapshot.get("trade_signals")).get("rows")):
        row = safe_dict(row)
        entity = safe_upper(row.get("entity"))
        if not entity:
            continue

        current = out.get(entity)
        if current is None:
            out[entity] = row
            continue

        if safe_float(row.get("priority_score"), 0.0) > safe_float(current.get("priority_score"), 0.0):
            out[entity] = row

    return out


def price_context(entity: str, rows: List[Dict[str, Any]], lookback_minutes: int) -> Dict[str, Any]:
    if len(rows) < 2:
        return {
            "ok": False,
            "reason": "insufficient_price_rows",
        }

    latest = rows[-1]
    latest_ts = latest.get("timestamp")
    latest_price = safe_float(latest.get("price"), 0.0)

    if not isinstance(latest_ts, datetime) or latest_price <= 0:
        return {
            "ok": False,
            "reason": "invalid_latest_price",
        }

    recent = [
        row for row in rows
        if row["timestamp"] >= latest_ts - timedelta(minutes=lookback_minutes)
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
        "entity": entity,
        "latest_timestamp": latest_ts.isoformat(),
        "latest_price": round(latest_price, 12),
        "change_pct": round(change_pct, 6),
        "from_high_pct": round(from_high_pct, 6),
        "from_low_pct": round(from_low_pct, 6),
        "high_price": round(high_price, 12),
        "low_price": round(low_price, 12),
        "history_points": len(rows),
        "recent_points": len(recent),
    }

def score_asset(
    entity: str,
    price_ctx: Dict[str, Any],
    trade_row: Dict[str, Any],
    universe_row: Dict[str, Any],
    market_quality: Dict[str, Any],
    strategy_policy: Dict[str, Any],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    weights = safe_dict(cfg.get("weights"))
    tier_scores = safe_dict(cfg.get("tier_scores"))

    change_pct = safe_float(price_ctx.get("change_pct"), 0.0)
    from_high_pct = safe_float(price_ctx.get("from_high_pct"), 0.0)
    from_low_pct = safe_float(price_ctx.get("from_low_pct"), 0.0)

    # ---------------------------------------------------
    # PRICE DIRECTION / MOMENTUM
    # ---------------------------------------------------

    price_direction = "bullish" if change_pct >= 0 else "bearish"
    price_momentum_score = clamp(abs(change_pct) / 5.0, 0.0, 1.0)

    if price_direction == "bullish":
        extension_score = clamp(1.0 + (from_high_pct / 2.0), 0.0, 1.0)
    else:
        extension_score = clamp(1.0 - (from_low_pct / 2.0), 0.0, 1.0)

    # ---------------------------------------------------
    # TRADE SIGNAL DIRECTION / SCORE
    # ---------------------------------------------------

    strategy = safe_str(trade_row.get("strategy") or trade_row.get("setup_family")) or "unknown"
    trade_direction = safe_str(trade_row.get("direction")).lower()
    priority = safe_float(trade_row.get("priority_score"), 0.0)
    no_trade = bool(trade_row.get("no_trade", False))

    trade_signal_score = 0.0 if no_trade else clamp(priority, 0.0, 1.0)

    signal_direction = "unknown"

    if trade_direction in {"bullish", "strong_bullish"}:
        signal_direction = "bullish"
    elif trade_direction in {"bearish", "strong_bearish"}:
        signal_direction = "bearish"

    implied_side = side_from_signal_direction(signal_direction)

    direction_conflict = (
        signal_direction in {"bullish", "bearish"}
        and signal_direction != price_direction
    )

    direction_aligned = (
        signal_direction in {"bullish", "bearish"}
        and signal_direction == price_direction
    )

    risk_flags: List[str] = []
    eligibility = "eligible"

    if no_trade:
        risk_flags.append("no_trade_signal")
        eligibility = "observe_only"

    if direction_conflict:
        risk_flags.append("direction_conflict")
        eligibility = "observe_only"

    if signal_direction == "unknown":
        risk_flags.append("missing_trade_direction")
        eligibility = "observe_only"

    # ---------------------------------------------------
    # UNIVERSE / TIER
    # ---------------------------------------------------

    tier = safe_str(universe_row.get("tier")) or "unknown"
    tier_score = safe_float(
        tier_scores.get(tier),
        safe_float(tier_scores.get("unknown"), 0.35),
    )

    paper_trade_only = safe_bool(universe_row.get("paper_trade_only"), False)

    # ---------------------------------------------------
    # MARKET QUALITY
    # ---------------------------------------------------

    market_quality = safe_dict(market_quality)
    market_quality_status = safe_str(market_quality.get("status")) or "missing"
    market_quality_score = safe_float(market_quality.get("quality_score"), 0.0)
    spread_bps = safe_float(market_quality.get("spread_bps"), 999999.0)
    total_depth_usd = safe_float(market_quality.get("total_depth_usd"), 0.0)
    book_imbalance = safe_float(market_quality.get("book_imbalance"), 0.0)

    minimum_quality = safe_float(cfg.get("minimum_market_quality_score"), 0.35)

    if not market_quality:
        risk_flags.append("missing_market_quality")
        market_quality_score = 0.25

    if market_quality_status in {"unavailable", "wide_or_illiquid"}:
        risk_flags.append(f"market_quality_{market_quality_status}")
        if safe_bool(cfg.get("block_unavailable_market_quality"), True):
            eligibility = "observe_only"

    if market_quality_score < minimum_quality:
        risk_flags.append("market_quality_below_minimum")
        eligibility = "observe_only"

    if market_quality_status == "thin" and safe_bool(cfg.get("penalize_thin_markets"), True):
        risk_flags.append("thin_market")

    market_quality_component = clamp(market_quality_score, 0.0, 1.0)

    # ---------------------------------------------------
    # BASE RANK SCORE
    # ---------------------------------------------------

    rank_score = (
        price_momentum_score * safe_float(weights.get("price_momentum"), 0.45)
        + extension_score * safe_float(weights.get("near_high"), 0.15)
        + trade_signal_score * safe_float(weights.get("trade_signal"), 0.20)
        + tier_score * safe_float(weights.get("universe_tier"), 0.05)
        + market_quality_component * safe_float(weights.get("market_quality"), 0.15)
    )

    if direction_aligned:
        rank_score *= 1.10

    if direction_conflict:
        rank_score *= 0.35

    if no_trade:
        rank_score *= 0.25

    if market_quality_status == "thin":
        rank_score *= 0.75

    if market_quality_status in {"unavailable", "wide_or_illiquid"}:
        rank_score *= 0.25

    # ---------------------------------------------------
    # MINIMUM MOVE GATE
    # ---------------------------------------------------

    if paper_trade_only:
        min_required_move = safe_float(cfg.get("minimum_paper_candidate_30m_change_pct"), 1.25)
        preferred_move = safe_float(cfg.get("preferred_paper_candidate_30m_change_pct"), 2.5)

        if abs(change_pct) < min_required_move:
            rank_score *= 0.20
            risk_flags.append("paper_candidate_move_too_small")
            eligibility = "observe_only"

        elif abs(change_pct) < preferred_move:
            rank_score *= 0.75
            risk_flags.append("paper_candidate_move_below_preferred")

    else:
        min_required_move = safe_float(cfg.get("minimum_live_candidate_30m_change_pct"), 0.35)

        if abs(change_pct) < min_required_move:
            rank_score *= 0.25
            risk_flags.append("controlled_asset_move_too_small")
            eligibility = "observe_only"

    # ---------------------------------------------------
    # STRATEGY POLICY GATE
    # ---------------------------------------------------

    policy_enabled = safe_bool(strategy_policy.get("enabled"), False)
    strategy_policy_row = strategy_policy_for(strategy, strategy_policy)
    strategy_policy_mode = safe_str(strategy_policy_row.get("mode")) or "observe_only"
    allowed_sides = [safe_str(x).lower() for x in safe_list(strategy_policy_row.get("allowed_sides"))]
    strategy_min_rank = safe_float(strategy_policy_row.get("minimum_rank_score"), 0.0)

    if policy_enabled:
        if strategy_policy_mode == "disabled":
            risk_flags.append("strategy_policy_disabled")
            eligibility = "observe_only"
            rank_score *= 0.05

        elif strategy_policy_mode == "observe_only":
            risk_flags.append("strategy_policy_observe_only")
            eligibility = "observe_only"
            rank_score *= 0.35

        elif strategy_policy_mode == "allow":
            if allowed_sides and implied_side not in allowed_sides:
                risk_flags.append(f"strategy_side_not_allowed:{implied_side}")
                eligibility = "observe_only"
                rank_score *= 0.25

            if paper_trade_only and not safe_bool(strategy_policy_row.get("allow_paper_candidates"), False):
                risk_flags.append("strategy_policy_blocks_paper_candidates")
                eligibility = "observe_only"
                rank_score *= 0.25

            if strategy_min_rank > 0 and rank_score < strategy_min_rank:
                risk_flags.append("strategy_policy_min_rank_not_met")
                eligibility = "observe_only"

        else:
            risk_flags.append(f"strategy_policy_unknown_mode:{strategy_policy_mode}")
            eligibility = "observe_only"
            rank_score *= 0.25

    # ---------------------------------------------------
    # FINAL TRADE THRESHOLD
    # ---------------------------------------------------

    minimum_rank_score = safe_float(cfg.get("minimum_rank_score_to_trade"), 0.35)

    if rank_score < minimum_rank_score:
        risk_flags.append("rank_score_below_trade_threshold")
        eligibility = "observe_only"

    return {
        "entity": entity,
        "rank_score": round(rank_score, 6),
        "direction": price_direction,
        "signal_direction": signal_direction,
        "direction_aligned": direction_aligned,
        "direction_conflict": direction_conflict,
        "eligibility": eligibility,
        "risk_flags": risk_flags,
        "strategy_policy": {
            "enabled": policy_enabled,
            "strategy": strategy,
            "mode": strategy_policy_mode,
            "allowed_sides": allowed_sides,
            "minimum_rank_score": strategy_min_rank,
        },
        "price_context": price_ctx,
        "market_quality": {
            "status": market_quality_status,
            "quality_score": round(market_quality_score, 6),
            "spread_bps": round(spread_bps, 6),
            "total_depth_usd": round(total_depth_usd, 4),
            "book_imbalance": round(book_imbalance, 6),
        },
        "trade_signal": {
            "direction": trade_row.get("direction"),
            "strategy": trade_row.get("strategy"),
            "setup_family": trade_row.get("setup_family"),
            "priority_score": trade_row.get("priority_score"),
            "confidence": trade_row.get("confidence"),
            "no_trade": trade_row.get("no_trade"),
            "reasons": trade_row.get("reasons", []),
        },
        "universe": universe_row,
        "components": {
            "price_momentum_score": round(price_momentum_score, 6),
            "extension_score": round(extension_score, 6),
            "trade_signal_score": round(trade_signal_score, 6),
            "tier_score": round(tier_score, 6),
            "market_quality_score": round(market_quality_component, 6),
            "direction_alignment_multiplier": 1.10 if direction_aligned else 1.0,
            "direction_conflict_multiplier": 0.35 if direction_conflict else 1.0,
            "no_trade_multiplier": 0.25 if no_trade else 1.0,
            "thin_market_multiplier": 0.75 if market_quality_status == "thin" else 1.0,
        },
    }


def build_open_position_map(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}

    for trade_id, position in safe_dict(state.get("open_positions")).items():
        position = safe_dict(position)
        entity = safe_upper(position.get("entity"))
        if entity:
            out[entity] = {
                "trade_id": trade_id,
                "side": position.get("side"),
                "strategy": position.get("strategy"),
                "unrealized_pnl_usd": position.get("unrealized_pnl_usd"),
                "duration_sec_live": position.get("duration_sec_live"),
                "position_size_usd": position.get("position_size_usd"),
            }

    return out


def build_rotation_recommendations(
    rows: List[Dict[str, Any]],
    open_map: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    rotation_cfg = safe_dict(cfg.get("rotation"))

    if not safe_bool(rotation_cfg.get("enabled"), True):
        return {
            "enabled": False,
            "recommendations": [],
        }

    protect_profitable = safe_bool(rotation_cfg.get("protect_profitable_positions"), True)
    min_replace_pnl = safe_float(rotation_cfg.get("minimum_unrealized_pnl_to_replace"), -1.0)
    min_improvement = safe_float(rotation_cfg.get("minimum_rank_improvement"), 0.25)

    open_entities = set(open_map.keys())

    candidates = [
        row for row in rows
        if row.get("entity") not in open_entities
    ]

    open_rank = {
        row.get("entity"): row
        for row in rows
        if row.get("entity") in open_entities
    }

    recommendations = []

    for entity, open_pos in open_map.items():
        current = open_rank.get(entity)

        if not current:
            continue

        current_score = safe_float(current.get("rank_score"), 0.0)
        open_pnl = safe_float(open_pos.get("unrealized_pnl_usd"), 0.0)

        if protect_profitable and open_pnl > 0:
            continue

        if open_pnl > min_replace_pnl:
            continue

        for candidate in candidates[:10]:
            candidate_score = safe_float(candidate.get("rank_score"), 0.0)
            improvement = candidate_score - current_score

            if improvement >= min_improvement:
                recommendations.append({
                    "action": "rotation_candidate",
                    "replace_entity": entity,
                    "replace_trade": open_pos,
                    "candidate_entity": candidate.get("entity"),
                    "candidate_score": candidate_score,
                    "current_score": current_score,
                    "score_improvement": round(improvement, 6),
                    "candidate": candidate,
                })
                break

    return {
        "enabled": True,
        "recommendations": recommendations,
    }


def build_asset_rotation_ranker(write_output: bool = True) -> Dict[str, Any]:
    cfg = load_engine_config()

    if not safe_bool(cfg.get("enabled"), True):
        payload = {
            "schema_version": 1,
            "generated_at": utc_now_iso(),
            "enabled": False,
            "rows": [],
        }
        if write_output:
            write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)
        return payload

    price_data = safe_dict(read_json(PRICE_PATH, {}))
    tokens = safe_dict(price_data.get("tokens"))
    snapshot = safe_dict(read_json(SNAPSHOT_PATH, {}))
    state = safe_dict(read_json(STATE_PATH, {}))

    universe = universe_context()
    trade_map = latest_trade_signal_map(snapshot)
    quality_map = market_quality_map()
    strategy_policy = load_strategy_policy()
    open_map = build_open_position_map(state)

    lookback_minutes = safe_int(cfg.get("lookback_minutes"), 30)
    max_ranked_assets = safe_int(cfg.get("max_ranked_assets"), 50)

    rows = []

    for entity, universe_row in universe.items():
        price_rows = normalize_price_rows(tokens.get(entity))
        pc = price_context(entity, price_rows, lookback_minutes)

        if not pc.get("ok"):
            continue

        trade_row = safe_dict(trade_map.get(entity))

        scored = score_asset(
            entity=entity,
            price_ctx=pc,
            trade_row=trade_row,
            universe_row=universe_row,
            market_quality=safe_dict(quality_map.get(entity)),
            strategy_policy=strategy_policy,
            cfg=cfg,
        )

        rows.append(scored)

    rows.sort(key=lambda x: safe_float(x.get("rank_score"), 0.0), reverse=True)

    top_rows = rows[:max_ranked_assets]
    rotation = build_rotation_recommendations(top_rows, open_map, cfg)

    paper_only_count = sum(1 for row in top_rows if safe_bool(safe_dict(row.get("universe")).get("paper_trade_only"), False))

    payload = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "system": "ToknClaw",
        "module": "asset_rotation_ranker",
        "enabled": True,
        "summary": {
            "ranked_asset_count": len(rows),
            "top_asset_count": len(top_rows),
            "paper_only_top_count": paper_only_count,
            "open_position_count": len(open_map),
            "rotation_recommendation_count": len(safe_list(rotation.get("recommendations"))),
        },
        "open_positions": open_map,
        "rotation": rotation,
        "rows": top_rows,
    }

    if write_output:
        write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, payload)

    debug_log(
        cfg,
        f"ranked={len(rows)} top={len(top_rows)} "
        f"paper_top={paper_only_count} rotations={payload['summary']['rotation_recommendation_count']}"
    )

    return payload


def main() -> None:
    payload = build_asset_rotation_ranker(write_output=True)
    print(json.dumps({
        "generated_at": payload.get("generated_at"),
        "summary": payload.get("summary"),
        "top_10": [
            {
                "entity": row.get("entity"),
                "rank_score": row.get("rank_score"),
                "direction": row.get("direction"),
                "tier": safe_dict(row.get("universe")).get("tier"),
                "paper_only": safe_dict(row.get("universe")).get("paper_trade_only"),
                "change_pct": safe_dict(row.get("price_context")).get("change_pct"),
                "trade_strategy": safe_dict(row.get("trade_signal")).get("strategy"),
                "trade_direction": safe_dict(row.get("trade_signal")).get("direction"),
            }
            for row in safe_list(payload.get("rows"))[:10]
        ],
        "rotation_recommendations": safe_list(safe_dict(payload.get("rotation")).get("recommendations"))[:5],
    }, indent=2))


if __name__ == "__main__":
    main()
