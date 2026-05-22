#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — EXECUTION RISK GATE
# ============================================================
#
# ████████╗ ██████╗ ██╗  ██╗███╗   ██╗ ██████╗██╗      █████╗ ██╗    ██╗
# ╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║██╔════╝██║     ██╔══██╗██║    ██║
#    ██║   ██║   ██║█████╔╝ ██╔██╗ ██║██║     ██║     ███████║██║ █╗ ██║
#    ██║   ██║   ██║██╔═██╗ ██║╚██╗██║██║     ██║     ██╔══██║██║███╗██║
#    ██║   ╚██████╔╝██║  ██╗██║ ╚████║╚██████╗███████╗██║  ██║╚███╔███╔╝
#    ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
#
# SYSTEM: ToknClaw Execution Layer
# MODULE: execution_risk_gate
# PURPOSE:
# - Validate execution intents before live exchange routing
# - Enforce manual kill switch
# - Enforce order size, exposure, confidence, regime, and asset limits
# - Write durable risk decisions for audit and future live adapters
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

INTENT_PATH = Path("/opt/toknclaw/data/execution/latest_execution_intents.json")
STATE_PATH = Path("/opt/toknclaw/data/paper_trading_state.json")
REGIME_PATH = Path("/opt/toknclaw/data/analytics/market_regime.json")
STRATEGY_DECISIONS_PATH = Path("/opt/toknclaw/data/analytics/strategy_decisions.json")

RISK_CONFIG_PATH = Path("/opt/toknclaw/config/execution_risk_config.json")
KILL_SWITCH_PATH = Path("/opt/toknclaw/config/kill_switch.json")

LATEST_DECISION_PATH = Path("/opt/toknclaw/data/execution/latest_risk_decision.json")
DECISION_LOG_PATH = Path("/opt/toknclaw/data/execution/risk_decision_log.json")

MAX_DECISION_LOG_ROWS = 1000


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_name(
        f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)

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


def safe_str(value: Any) -> str:
    return str(value or "").strip()


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def append_decision_log(decision: Dict[str, Any]) -> None:
    rows = read_json(DECISION_LOG_PATH, [])

    if not isinstance(rows, list):
        rows = []

    rows.append(decision)
    rows = rows[-MAX_DECISION_LOG_ROWS:]

    write_json_atomic(DECISION_LOG_PATH, rows)


def latest_intent() -> Dict[str, Any]:
    payload = read_json(INTENT_PATH, {})
    return safe_dict(payload.get("latest_intent"))


def current_open_positions(state: Dict[str, Any]) -> Dict[str, Any]:
    return safe_dict(state.get("open_positions"))


def portfolio(state: Dict[str, Any]) -> Dict[str, Any]:
    return safe_dict(state.get("portfolio"))


def total_open_exposure_usd(state: Dict[str, Any]) -> float:
    total = 0.0

    for position in current_open_positions(state).values():
        position = safe_dict(position)
        total += safe_float(position.get("position_size_usd"), 0.0)

    return round(total, 4)


def positions_for_entity(state: Dict[str, Any], entity: str) -> int:
    entity = safe_str(entity).upper()
    count = 0

    for position in current_open_positions(state).values():
        position = safe_dict(position)
        if safe_str(position.get("entity")).upper() == entity:
            count += 1

    return count


def daily_realized_pnl_usd(state: Dict[str, Any]) -> float:
    """
    Uses today's UTC closed positions as a simple daily PnL guard.
    """

    today = datetime.now(UTC).date().isoformat()
    pnl = 0.0

    for row in safe_list(state.get("closed_positions")):
        row = safe_dict(row)
        closed_at = safe_str(row.get("closed_at"))

        if closed_at.startswith(today):
            pnl += safe_float(row.get("realized_pnl_usd"), 0.0)

    return round(pnl, 4)


def daily_trade_count(state: Dict[str, Any]) -> int:
    today = datetime.now(UTC).date().isoformat()
    count = 0

    for row in safe_list(state.get("closed_positions")):
        row = safe_dict(row)
        closed_at = safe_str(row.get("closed_at"))

        if closed_at.startswith(today):
            count += 1

    return count


def priority_rank(priority: str) -> int:
    priority = safe_str(priority).lower()

    if priority == "high":
        return 3

    if priority == "medium":
        return 2

    if priority == "low":
        return 1

    return 0

def strategy_health_for(strategy_key: str) -> str:
    decisions = safe_dict(read_json(STRATEGY_DECISIONS_PATH, {}))
    target = safe_str(strategy_key)

    for row in safe_list(decisions.get("strategy_decisions")):
        row = safe_dict(row)
        current = safe_str(row.get("strategy_key"))

        if current != target:
            continue

        realized = safe_dict(row.get("realized"))
        return safe_str(realized.get("health")) or "unknown"

    return "unknown"

# ---------------------------------------------------
# CORE RISK EVALUATION
# ---------------------------------------------------

def evaluate_execution_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    cfg = safe_dict(read_json(RISK_CONFIG_PATH, {}))
    kill = safe_dict(read_json(KILL_SWITCH_PATH, {}))
    state = safe_dict(read_json(STATE_PATH, {}))
    regime = safe_dict(read_json(REGIME_PATH, {}))

    reasons: List[str] = []
    warnings: List[str] = []

    entity = safe_str(intent.get("entity")).upper()
    side = safe_str(intent.get("side")).lower()
    venue = safe_str(intent.get("venue")).lower()
    execution_mode = safe_str(intent.get("execution_mode")).lower()
    status = safe_str(intent.get("status"))
    size_usd = safe_float(intent.get("size_usd"), 0.0)
    confidence = safe_float(intent.get("confidence"), 0.0)
    priority = safe_str(intent.get("priority")).lower()
    trade_id = safe_str(intent.get("trade_id"))

    if not cfg.get("enabled", True):
        reasons.append("execution_risk_gate_disabled")

    if kill.get("manual_kill_switch", True):
        reasons.append(f"manual_kill_switch_active:{safe_str(kill.get('reason'))}")

    if not trade_id:
        reasons.append("missing_trade_id")

    if status.startswith("rejected"):
        reasons.append(f"intent_already_rejected:{status}")

    if execution_mode == "live" and not bool(cfg.get("live_trading_enabled", False)):
        reasons.append("live_trading_not_enabled")

    if execution_mode == "paper":
        warnings.append("paper_mode_intent")

    if execution_mode == "dry_run" and not bool(cfg.get("dry_run_enabled", True)):
        reasons.append("dry_run_not_enabled")

    allowed_venues = set(safe_list(cfg.get("allowed_venues")))
    if venue not in allowed_venues:
        reasons.append(f"venue_not_allowed:{venue}")

    allowed_entities = {safe_str(x).upper() for x in safe_list(cfg.get("allowed_entities"))}
    if entity not in allowed_entities:
        reasons.append(f"entity_not_allowed:{entity}")

    allowed_sides = {safe_str(x).lower() for x in safe_list(cfg.get("allowed_sides"))}
    if side not in allowed_sides:
        reasons.append(f"side_not_allowed:{side}")

    max_single_order_usd = safe_float(cfg.get("max_single_order_usd"), 0.0)
    if max_single_order_usd > 0 and size_usd > max_single_order_usd:
        reasons.append(f"order_size_exceeds_limit:{size_usd}>{max_single_order_usd}")

    if size_usd <= 0:
        reasons.append("invalid_order_size")

    minimum_confidence = safe_float(cfg.get("minimum_confidence"), 0.0)
    if confidence < minimum_confidence:
        reasons.append(f"confidence_below_minimum:{confidence}<{minimum_confidence}")

    minimum_priority = safe_str(cfg.get("minimum_priority")).lower()
    if priority_rank(priority) < priority_rank(minimum_priority):
        reasons.append(f"priority_below_minimum:{priority}<{minimum_priority}")

    intent = safe_dict(intent)
    strategy_key = safe_str(intent.get("strategy") or intent.get("setup_family"))
    strategy_health = strategy_health_for(strategy_key)

    blocked_strategy_health = {
        "underperforming",
        "weak",
    }

    if strategy_health in blocked_strategy_health:
        reasons.append(f"strategy_health_blocked:{strategy_key}:{strategy_health}")

    max_open_positions = safe_int(cfg.get("max_open_positions"), 0)
    if max_open_positions > 0 and len(current_open_positions(state)) >= max_open_positions:
        reasons.append("max_open_positions_reached")

    max_positions_per_entity = safe_int(cfg.get("max_positions_per_entity"), 0)
    if max_positions_per_entity > 0 and positions_for_entity(state, entity) >= max_positions_per_entity:
        reasons.append(f"max_positions_per_entity_reached:{entity}")

    max_total_open_exposure_usd = safe_float(cfg.get("max_total_open_exposure_usd"), 0.0)
    projected_exposure = total_open_exposure_usd(state) + size_usd
    if max_total_open_exposure_usd > 0 and projected_exposure > max_total_open_exposure_usd:
        reasons.append(f"projected_exposure_exceeds_limit:{projected_exposure}>{max_total_open_exposure_usd}")

    max_daily_loss = safe_float(cfg.get("max_daily_realized_loss_usd"), 0.0)
    today_pnl = daily_realized_pnl_usd(state)
    if max_daily_loss > 0 and today_pnl <= -abs(max_daily_loss):
        reasons.append(f"daily_loss_limit_hit:{today_pnl}")

    max_daily_count = safe_int(cfg.get("max_daily_trade_count"), 0)
    today_count = daily_trade_count(state)
    if max_daily_count > 0 and today_count >= max_daily_count:
        reasons.append(f"daily_trade_count_limit_hit:{today_count}")

    current_regime = safe_str(regime.get("regime")) or "unknown"
    if cfg.get("require_regime_file", True) and not REGIME_PATH.exists():
        reasons.append("missing_market_regime_file")

    if cfg.get("block_live_orders_in_chop", True) and current_regime == "chop" and execution_mode == "live":
        reasons.append("live_order_blocked_in_chop")

    decision_status = "approved" if not reasons else "rejected"

    decision = {
        "schema_version": 1,
        "evaluated_at": utc_now(),
        "status": decision_status,
        "reasons": reasons,
        "warnings": warnings,
        "trade_id": trade_id,
        "entity": entity,
        "side": side,
        "venue": venue,
        "execution_mode": execution_mode,
        "size_usd": size_usd,
        "confidence": confidence,
        "priority": priority,
        "strategy_key": strategy_key,
        "strategy_health": strategy_health,
        "market_regime": current_regime,
        "risk_snapshot": {
            "open_positions": len(current_open_positions(state)),
            "open_exposure_usd": total_open_exposure_usd(state),
            "projected_exposure_usd": round(projected_exposure, 4),
            "daily_realized_pnl_usd": today_pnl,
            "daily_trade_count": today_count,
        },
        "intent": intent,
    }

    return decision


def evaluate_latest_intent() -> Dict[str, Any]:
    intent = latest_intent()

    if not intent:
        decision = {
            "schema_version": 1,
            "evaluated_at": utc_now(),
            "status": "rejected",
            "reasons": ["missing_latest_execution_intent"],
            "warnings": [],
            "intent": {},
        }
    else:
        decision = evaluate_execution_intent(intent)

    write_json_atomic(LATEST_DECISION_PATH, decision)
    append_decision_log(decision)

    print(
        f"[EXECUTION RISK] status={decision.get('status')} "
        f"entity={decision.get('entity')} "
        f"side={decision.get('side')} "
        f"reasons={decision.get('reasons')}",
        flush=True,
    )

    return decision


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    result = evaluate_latest_intent()
    print(json.dumps(result, indent=2))
