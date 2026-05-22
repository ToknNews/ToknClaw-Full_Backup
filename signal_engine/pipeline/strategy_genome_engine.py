#!/usr/bin/env python3

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
# MODULE: strategy_genome_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
████████╗ ██████╗ ██╗  ██╗███╗   ██╗
╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║
   ██║   ██║   ██║█████╔╝ ██╔██╗ ██║
   ██║   ██║   ██║██╔═██╗ ██║╚██╗██║
   ██║   ╚██████╔╝██║  ██╗██║ ╚████║
   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝

TOKNCLAW SIGNAL ENGINE
Autonomous Market Intelligence Platform

Strategy Genome Engine
----------------------
Stores and manages ToknClaw strategy genomes for:

• strategy persistence
• mutation lineage
• strategy activation / retirement
• strategy parameter state
• future reinforcement learning loops
• future agent-driven strategy generation

This module orchestrates durable strategy state in ToknClaw.

Author: TOKN Systems
"""

from __future__ import annotations

import json
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List


GENOME_DIR = Path("/opt/toknclaw/data/strategy_genome")
GENOME_DIR.mkdir(parents=True, exist_ok=True)

GENOME_FILE = GENOME_DIR / "strategy_genome.json"


# ---------------------------------------------------
# Helpers
# ---------------------------------------------------

def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _now_ts() -> int:
    return int(time.time())


def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _hash_strategy(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------
# Base storage
# ---------------------------------------------------

def _load_genome_store() -> Dict[str, Any]:
    return _load_json(
        GENOME_FILE,
        {
            "meta": {
                "created_at": _now_ts(),
                "updated_at": _now_ts(),
                "version": 1,
            },
            "strategies": {},
        },
    )


# ---------------------------------------------------
# Record builders
# ---------------------------------------------------

def _base_strategy_record(strategy: Dict[str, Any]) -> Dict[str, Any]:
    strategy = _safe_dict(strategy)

    strategy_id = _safe_str(strategy.get("strategy_id")) or _hash_strategy(strategy)

    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy.get("strategy_name") or strategy.get("name") or strategy_id,
        "mode": strategy.get("mode"),
        "status": "active",
        "generation": int(strategy.get("generation") or 1),
        "lineage_parent": strategy.get("mutation_origin"),
        "created_at": _now_ts(),
        "last_updated": _now_ts(),
        "retired_at": None,
        "parameters": {
            "min_trade_confidence": strategy.get("min_trade_confidence"),
            "min_composite_factor": strategy.get("min_composite_factor"),
            "direction_set": sorted(list(strategy.get("direction_set", []))) if isinstance(strategy.get("direction_set"), set) else strategy.get("direction_set"),
            "mode": strategy.get("mode"),
            "factor_weight_shift": strategy.get("factor_weight_shift"),
            "signal_filter": strategy.get("signal_filter"),
            "regime_focus": strategy.get("regime_focus"),
        },
        "performance": {
            "trade_count": 0,
            "hit_rate": 0.0,
            "avg_pnl_proxy": 0.0,
            "sharpe_proxy": 0.0,
            "performance_score": 0.0,
        },
        "reinforcement": {
            "score": 0.0,
            "weight": 0.0,
            "state": "neutral",
        },
        "evolution": {
            "mutation_count": 0,
            "selected_count": 0,
            "rejected_count": 0,
        },
        "tags": strategy.get("tags") or [],
        "notes": strategy.get("notes") or [],
    }


def _merge_performance(record: Dict[str, Any], perf_row: Dict[str, Any]) -> Dict[str, Any]:
    record = _safe_dict(record)
    perf_row = _safe_dict(perf_row)

    record["performance"] = {
        "trade_count": int(_safe_float(perf_row.get("trade_count"), 0)),
        "hit_rate": round(_safe_float(perf_row.get("hit_rate"), 0.0), 4),
        "avg_pnl_proxy": round(_safe_float(perf_row.get("avg_pnl_proxy"), 0.0), 6),
        "sharpe_proxy": round(_safe_float(perf_row.get("sharpe_proxy"), 0.0), 6),
        "performance_score": round(_safe_float(perf_row.get("performance_score"), 0.0), 6),
    }
    record["last_updated"] = _now_ts()
    return record


def _apply_mutations(store: Dict[str, Any], mutations: List[Dict[str, Any]]) -> Dict[str, Any]:
    strategies = _safe_dict(store.get("strategies"))

    for mutation_row in mutations:
        mutation_row = _safe_dict(mutation_row)

        parent_strategy = _safe_str(mutation_row.get("parent_strategy"))
        mutation = _safe_dict(mutation_row.get("mutation"))

        if not mutation:
            continue

        child_id = _safe_str(mutation.get("strategy_id"))
        if not child_id:
            child_id = _hash_strategy(mutation)
            mutation["strategy_id"] = child_id

        base = _base_strategy_record(mutation)
        base["lineage_parent"] = parent_strategy or mutation.get("mutation_origin")
        base["generation"] = int(_safe_float(_safe_dict(strategies.get(parent_strategy)).get("generation"), 1)) + 1 if parent_strategy in strategies else 2
        base["notes"] = _safe_list(base.get("notes")) + [f"Generated by mutation from {parent_strategy}"]

        existing = _safe_dict(strategies.get(child_id))
        if existing:
            existing["last_updated"] = _now_ts()
            existing["status"] = "candidate"
            existing["parameters"] = base["parameters"]
            existing["lineage_parent"] = base["lineage_parent"]
            existing["generation"] = base["generation"]
            existing["notes"] = _safe_list(existing.get("notes")) + [f"Mutation refresh from {parent_strategy}"]
            strategies[child_id] = existing
        else:
            base["status"] = "candidate"
            strategies[child_id] = base

        if parent_strategy in strategies:
            strategies[parent_strategy]["evolution"]["mutation_count"] = int(
                _safe_float(_safe_dict(strategies[parent_strategy]).get("evolution", {}).get("mutation_count"), 0)
            ) + 1
            strategies[parent_strategy]["last_updated"] = _now_ts()

    store["strategies"] = strategies
    return store


def _apply_retirements(store: Dict[str, Any], retirements: List[Dict[str, Any]]) -> Dict[str, Any]:
    strategies = _safe_dict(store.get("strategies"))

    for retirement in retirements:
        retirement = _safe_dict(retirement)
        strategy_id = _safe_str(retirement.get("strategy_id"))
        if strategy_id not in strategies:
            continue

        strategies[strategy_id]["status"] = "retired"
        strategies[strategy_id]["retired_at"] = _now_ts()
        strategies[strategy_id]["last_updated"] = _now_ts()
        strategies[strategy_id]["notes"] = _safe_list(strategies[strategy_id].get("notes")) + [
            f"Retired due to {_safe_str(retirement.get('reason')) or 'unknown_reason'}"
        ]

    store["strategies"] = strategies
    return store


# ---------------------------------------------------
# Main engine
# ---------------------------------------------------

def build_strategy_genome(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _safe_dict(snapshot)

    store = _load_genome_store()
    strategies = _safe_dict(store.get("strategies"))

    # seed from simulation
    sim_rows = _safe_list(_safe_dict(snapshot.get("strategy_simulation")).get("strategies"))
    for sim_row in sim_rows:
        sim_row = _safe_dict(sim_row)
        strategy_id = _safe_str(sim_row.get("strategy_id"))
        if not strategy_id:
            continue
        if strategy_id not in strategies:
            strategies[strategy_id] = _base_strategy_record(sim_row)

    # attach performance
    perf_rows = _safe_list(snapshot.get("strategy_performance"))
    perf_map = {
        _safe_str(_safe_dict(row).get("strategy_id")): _safe_dict(row)
        for row in perf_rows
        if _safe_str(_safe_dict(row).get("strategy_id"))
    }

    for strategy_id, perf_row in perf_map.items():
        if strategy_id not in strategies:
            strategies[strategy_id] = _base_strategy_record(perf_row)
        strategies[strategy_id] = _merge_performance(strategies[strategy_id], perf_row)

    store["strategies"] = strategies

    # evolution integration
    evolution = _safe_dict(snapshot.get("strategy_evolution"))
    mutations = _safe_list(evolution.get("mutations"))
    retirements = _safe_list(evolution.get("retirements"))

    store = _apply_mutations(store, mutations)
    store = _apply_retirements(store, retirements)

    store["meta"] = {
        **_safe_dict(store.get("meta")),
        "updated_at": _now_ts(),
        "strategy_count": len(_safe_dict(store.get("strategies"))),
    }

    _save_json(GENOME_FILE, store)

    rows = list(_safe_dict(store.get("strategies")).values())
    rows.sort(
        key=lambda x: (
            _safe_float(_safe_dict(x.get("performance")).get("performance_score"), 0.0),
            _safe_float(_safe_dict(x.get("performance")).get("sharpe_proxy"), 0.0),
            _safe_str(x.get("strategy_id")),
        ),
        reverse=True,
    )

    summary = {
        "strategy_count": len(rows),
        "active_count": sum(1 for r in rows if _safe_str(r.get("status")) == "active"),
        "candidate_count": sum(1 for r in rows if _safe_str(r.get("status")) == "candidate"),
        "retired_count": sum(1 for r in rows if _safe_str(r.get("status")) == "retired"),
        "top_strategy": rows[0].get("strategy_id") if rows else None,
    }

    alerts = []

    if summary["candidate_count"] > 0:
        alerts.append({
            "type": "strategy_candidates_available",
            "severity": "medium",
            "title": "New candidate strategies are available in the genome",
        })

    if summary["retired_count"] > 0:
        alerts.append({
            "type": "strategies_retired",
            "severity": "low",
            "title": "One or more strategies have been retired",
        })

    return {
        "strategy_genome": rows,
        "strategy_genome_summary": summary,
        "strategy_genome_alerts": alerts,
        "strategy_genome_endpoints": {
            "strategy_genome": "/api/toknclaw/strategy-genome",
            "strategy_genome_summary": "/api/toknclaw/strategy-genome/summary",
            "strategy_genome_alerts": "/api/toknclaw/strategy-genome/alerts",
        },
    }
