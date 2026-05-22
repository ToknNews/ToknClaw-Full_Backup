#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — STRATEGY MUTATION EXECUTOR
# ============================================================

████████╗ ██████╗ ██╗  ██╗███╗   ██╗ ██████╗██╗      █████╗ ██╗    ██╗
╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║██╔════╝██║     ██╔══██╗██║    ██║
   ██║   ██║   ██║█████╔╝ ██╔██╗ ██║██║     ██║     ███████║██║ █╗ ██║
   ██║   ██║   ██║██╔═██╗ ██║╚██╗██║██║     ██║     ██╔══██║██║███╗██║
   ██║   ╚██████╔╝██║  ██╗██║ ╚████║╚██████╗███████╗██║  ██║╚███╔███╔╝
   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝

SYSTEM: Adaptive Strategy Controller
MODULE: strategy_mutation_executor
PURPOSE:
- Apply agent-driven strategy mutations
- Downweight underperforming strategies
- Upweight outperforming strategies
- Reactivate dormant strategies with controlled probes
- Normalize strategy weights
- Maintain mutation audit history

# ============================================================
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

DECISIONS_PATH = Path("/opt/toknclaw/data/analytics/strategy_decisions.json")
WEIGHTS_PATH = Path("/opt/toknclaw/config/trade_signal_weights.json")
STATE_PATH = Path("/opt/toknclaw/data/analytics/strategy_mutation_state.json")
LOG_PATH = Path("/opt/toknclaw/data/analytics/strategy_mutation_log.json")

MIN_WEIGHT_FLOOR = 0.02
PROBE_WEIGHT = 0.05
MAX_WEIGHT = 2.5
DOWNWEIGHT_MULTIPLIER = 0.85
UPWEIGHT_MULTIPLIER = 1.15
MIN_SAMPLE_FOR_MUTATION = 20
PROBE_COOLDOWN_SEC = 6 * 60 * 60
MAX_LOG_ROWS = 500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    tmp_path.replace(path)


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def clamp_weight(value: float) -> float:
    return round(max(0.0, min(MAX_WEIGHT, value)), 4)


def load_mutation_state() -> Dict[str, Any]:
    state = load_json(STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}

    state.setdefault("schema_version", 1)
    state.setdefault("updated_at", utc_now())
    state.setdefault("strategies", {})

    if not isinstance(state["strategies"], dict):
        state["strategies"] = {}

    return state


def load_mutation_log() -> List[Dict[str, Any]]:
    log = load_json(LOG_PATH, [])
    if not isinstance(log, list):
        return []
    return log[-MAX_LOG_ROWS:]


def append_log(entry: Dict[str, Any]) -> None:
    log = load_mutation_log()
    log.append(entry)
    save_json(LOG_PATH, log[-MAX_LOG_ROWS:])


def normalize_weights(weights: Dict[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}

    for key, value in weights.items():
        weight = safe_float(value, 0.0)

        if weight > 0 and weight < MIN_WEIGHT_FLOOR:
            weight = MIN_WEIGHT_FLOOR

        normalized[key] = clamp_weight(weight)

    return normalized


def index_decisions(decisions: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = decisions.get("strategy_decisions", [])
    if not isinstance(rows, list):
        rows = []

    indexed: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        strategy = row.get("strategy_key")
        if not strategy:
            continue

        indexed[strategy] = row

    return indexed


def has_action(row: Dict[str, Any], action_type: str) -> bool:
    actions = row.get("actions", [])
    if not isinstance(actions, list):
        return False

    return any(isinstance(a, dict) and a.get("type") == action_type for a in actions)


def should_reactivate(
    strategy: str,
    row: Dict[str, Any],
    strategy_state: Dict[str, Any],
    now_ts: float,
) -> Tuple[bool, str]:
    realized = row.get("realized", {})
    if not isinstance(realized, dict):
        realized = {}

    health = realized.get("health")
    sample_confidence = safe_float(row.get("sample_confidence"), 0.0)
    count = safe_int(realized.get("count"), 0)
    pnl = safe_float(realized.get("realized_pnl_usd"), 0.0)

    last_probe_ts = safe_float(strategy_state.get("last_probe_ts"), 0.0)
    cooldown_elapsed = now_ts - last_probe_ts >= PROBE_COOLDOWN_SEC

    if health == "outperforming" and cooldown_elapsed:
        return True, "outperforming_reactivation"

    if sample_confidence >= 0.75 and pnl > 0 and count >= 5 and cooldown_elapsed:
        return True, "positive_high_confidence_probe"

    return False, "no_reactivation_signal"


def mutate_strategy(
    strategy: str,
    old_weight: float,
    row: Dict[str, Any],
    strategy_state: Dict[str, Any],
    now_ts: float,
) -> Tuple[float, List[Dict[str, Any]]]:
    mutations: List[Dict[str, Any]] = []

    realized = row.get("realized", {})
    if not isinstance(realized, dict):
        realized = {}

    health = realized.get("health")
    count = safe_int(realized.get("count"), 0)
    pnl = safe_float(realized.get("realized_pnl_usd"), 0.0)
    win_rate_pct = safe_float(realized.get("win_rate_pct"), 0.0)

    if old_weight == 0:
        reactivate, reason = should_reactivate(strategy, row, strategy_state, now_ts)
        if reactivate:
            new_weight = PROBE_WEIGHT
            strategy_state["last_probe_ts"] = now_ts
            strategy_state["status"] = "probing"
            mutations.append({
                "type": "reactivate",
                "strategy": strategy,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "reason": reason,
            })
            return new_weight, mutations

        strategy_state["status"] = "dormant"
        return old_weight, mutations

    new_weight = old_weight

    if has_action(row, "weight_reduction_candidate") and count >= MIN_SAMPLE_FOR_MUTATION:
        reduced = max(MIN_WEIGHT_FLOOR, old_weight * DOWNWEIGHT_MULTIPLIER)
        new_weight = clamp_weight(reduced)
        strategy_state["status"] = "downweighted"
        mutations.append({
            "type": "downweight",
            "strategy": strategy,
            "old_weight": old_weight,
            "new_weight": new_weight,
            "reason": "underperforming_agent_decision",
            "count": count,
            "pnl": pnl,
            "win_rate_pct": win_rate_pct,
        })

    if health == "outperforming" and count >= MIN_SAMPLE_FOR_MUTATION:
        boosted = min(MAX_WEIGHT, new_weight * UPWEIGHT_MULTIPLIER)
        final_weight = clamp_weight(boosted)

        if final_weight != new_weight:
            mutations.append({
                "type": "upweight",
                "strategy": strategy,
                "old_weight": new_weight,
                "new_weight": final_weight,
                "reason": "outperforming_realized_health",
                "count": count,
                "pnl": pnl,
                "win_rate_pct": win_rate_pct,
            })

        new_weight = final_weight
        strategy_state["status"] = "upweighted"

    return new_weight, mutations


def apply_exploration_probe(
    weights: Dict[str, float],
    state: Dict[str, Any],
    now_ts: float,
) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
    mutations: List[Dict[str, Any]] = []
    strategies = state.setdefault("strategies", {})

    dormant_candidates = []

    for strategy, weight in weights.items():
        strategy_state = strategies.setdefault(strategy, {})
        last_probe_ts = safe_float(strategy_state.get("last_probe_ts"), 0.0)

        if weight == 0 and now_ts - last_probe_ts >= PROBE_COOLDOWN_SEC:
            dormant_candidates.append(strategy)

    if not dormant_candidates:
        return weights, mutations

    strategy = sorted(dormant_candidates)[0]
    weights[strategy] = PROBE_WEIGHT
    strategies[strategy]["last_probe_ts"] = now_ts
    strategies[strategy]["status"] = "scheduled_probe"

    mutations.append({
        "type": "exploration_probe",
        "strategy": strategy,
        "old_weight": 0.0,
        "new_weight": PROBE_WEIGHT,
        "reason": "scheduled_dormant_strategy_probe",
    })

    return weights, mutations


def apply_mutations() -> None:
    decisions = load_json(DECISIONS_PATH, {})
    raw_weights = load_json(WEIGHTS_PATH, {})
    state = load_mutation_state()

    if not isinstance(raw_weights, dict):
        print("[MUTATION ERROR] weights config is not a JSON object")
        return

    weights = normalize_weights(raw_weights)
    indexed = index_decisions(decisions)
    now_ts = time.time()

    state["updated_at"] = utc_now()
    state["strategies"].setdefault("_meta", {})
    state["strategies"]["_meta"]["last_run_ts"] = now_ts

    changed = False
    all_mutations: List[Dict[str, Any]] = []

    print(f"[DEBUG] Strategies in weights: {len(weights)}")
    print(f"[DEBUG] Decisions indexed: {len(indexed)}")

    for strategy, old_weight in list(weights.items()):
        if strategy.startswith("_"):
            continue

        strategy_state = state["strategies"].setdefault(strategy, {})
        row = indexed.get(strategy)

        if not row:
            strategy_state.setdefault("status", "active")
            continue

        new_weight, mutations = mutate_strategy(
            strategy=strategy,
            old_weight=old_weight,
            row=row,
            strategy_state=strategy_state,
            now_ts=now_ts,
        )

        if new_weight != old_weight:
            weights[strategy] = new_weight
            changed = True

        all_mutations.extend(mutations)

    weights, probe_mutations = apply_exploration_probe(weights, state, now_ts)
    if probe_mutations:
        changed = True
        all_mutations.extend(probe_mutations)

    weights = normalize_weights(weights)

    if changed:
        save_json(WEIGHTS_PATH, weights)
        save_json(STATE_PATH, state)

        for mutation in all_mutations:
            mutation["ts"] = now_ts
            mutation["generated_at"] = utc_now()
            append_log(mutation)

            print(
                f"[{mutation['type'].upper()}] "
                f"{mutation['strategy']}: "
                f"{mutation.get('old_weight')} → {mutation.get('new_weight')} "
                f"({mutation.get('reason')})"
            )

        print("[MUTATION] Weights updated")
    else:
        save_json(STATE_PATH, state)
        print("[MUTATION] No changes applied")


if __name__ == "__main__":
    apply_mutations()
