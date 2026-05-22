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
# MODULE: trading_view_engine
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
Trading View Engine

Purpose
-------
Build a trading-only API-ready view from the unified ToknClaw brain.

This module is designed to:
• read the central snapshot without mutating it
• expose trading-relevant state only
• support website dashboards and bot monitoring
• remain additive and OpenClaw-ready
• preserve separation between trading, intelligence, and media layers

Primary Input
-------------
/opt/toknclaw/data/snapshots/latest_snapshot.json

Primary Output
--------------
/opt/toknclaw/data/views/trading_view.json

Design Notes
------------
• no direct RPC calls
• no collector execution
• pure derived view
• future-safe for richer memecoin metrics

Author: TOKN Systems
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot.json")
OUTPUT_PATH = Path("/opt/toknclaw/data/views/trading_view.json")
TMP_OUTPUT_PATH = Path("/opt/toknclaw/data/views/trading_view.tmp")


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


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path: Path, tmp_path: Path, payload: Dict[str, Any]) -> None:
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def load_snapshot() -> Dict[str, Any]:
    data = read_json_file(SNAPSHOT_PATH, {})
    if isinstance(data, dict):
        return data
    return {}


def object_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    out: List[Dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
    return out


def top_n(rows: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    return rows[:max(0, n)]


def index_signals_by_entity(signals: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}

    for row in signals:
        entity = clean_text(row.get("entity"))
        if not entity:
            continue

        out.setdefault(entity, []).append(row)

    return out


def signal_types_for_entity(rows: List[Dict[str, Any]]) -> List[str]:
    return sorted(set(clean_text(x.get("signal_type")) for x in rows if clean_text(x.get("signal_type"))))


def first_signal(rows: List[Dict[str, Any]], signal_type: str) -> Dict[str, Any]:
    for row in rows:
        if clean_text(row.get("signal_type")) == signal_type:
            return row
    return {}


# ---------------------------------------------------
# MARKET OVERVIEW
# ---------------------------------------------------

def build_market_overview(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    metrics = snapshot.get("metrics", {})
    solana_summary = metrics.get("solana_summary", {})
    signal_types = metrics.get("signal_types", {})

    return {
        "updated_at": utc_now_iso(),
        "signals_processed": safe_int(metrics.get("total_signals", 0)),
        "unique_entities": safe_int(metrics.get("unique_entities", 0)),
        "launch_activity": safe_int(solana_summary.get("launch_activity", 0)),
        "liquidity_events": safe_int(solana_summary.get("liquidity_events", 0)),
        "swap_activity": safe_int(solana_summary.get("swap_activity", 0)),
        "alpha_signal_count": safe_int(metrics.get("alpha_signal_count", 0)),
        "memecoin_trending_count": safe_int(signal_types.get("solana_memecoin_trending", 0)),
        "trade_decision_count": safe_int(signal_types.get("solana_trade_decision", 0)),
        "trade_candidate_count": safe_int(signal_types.get("solana_trade_candidate", 0)),
        "trade_avoid_count": safe_int(signal_types.get("solana_trade_avoid", 0)),
    }


# ---------------------------------------------------
# TRADE BOARD
# ---------------------------------------------------

def build_trade_board(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    signals = object_rows(snapshot.get("signals", []))
    by_entity = index_signals_by_entity(signals)

    decisions = [s for s in signals if clean_text(s.get("signal_type")) == "solana_trade_decision"]
    candidates = [s for s in signals if clean_text(s.get("signal_type")) == "solana_trade_candidate"]
    avoids = [s for s in signals if clean_text(s.get("signal_type")) == "solana_trade_avoid"]

    def enrich_trade_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []

        for row in rows:
            entity = clean_text(row.get("entity"))
            entity_signals = by_entity.get(entity, [])

            enriched.append(
                {
                    "entity": entity,
                    "title": clean_text(row.get("title")),
                    "summary": clean_text(row.get("summary")),
                    "confidence": safe_float(row.get("confidence", 0.0)),
                    "sentiment_score": safe_float(row.get("sentiment_score", 0.0)),
                    "signal_types_seen": signal_types_for_entity(entity_signals),
                    "alpha_signal": bool(first_signal(entity_signals, "solana_alpha_entry_signal")),
                    "memecoin_trending": bool(first_signal(entity_signals, "solana_memecoin_trending")),
                    "memecoin_of_the_day": bool(first_signal(entity_signals, "solana_memecoin_of_the_day")),
                    "thin_liquidity_alert": bool(first_signal(entity_signals, "solana_thin_liquidity_alert")),
                    "allocator_rank_title": clean_text(row.get("title")),
                }
            )

        return enriched

    return {
        "updated_at": utc_now_iso(),
        "decisions": enrich_trade_rows(decisions),
        "candidates": enrich_trade_rows(candidates),
        "avoids": enrich_trade_rows(avoids),
        "summary": {
            "decision_count": len(decisions),
            "candidate_count": len(candidates),
            "avoid_count": len(avoids),
        },
    }


# ---------------------------------------------------
# MEMECOIN BOARD
# ---------------------------------------------------

def build_memecoin_board(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    signals = object_rows(snapshot.get("signals", []))
    by_entity = index_signals_by_entity(signals)

    trending = [s for s in signals if clean_text(s.get("signal_type")) == "solana_memecoin_trending"]
    watchlist = [s for s in signals if clean_text(s.get("signal_type")) == "solana_bitsy_watchlist"]
    narratives = [s for s in signals if clean_text(s.get("signal_type")) == "solana_memecoin_narrative_candidate"]

    trending_cards: List[Dict[str, Any]] = []

    for row in trending[:25]:
        entity = clean_text(row.get("entity"))
        entity_signals = by_entity.get(entity, [])

        trending_cards.append(
            {
                "entity": entity,
                "title": clean_text(row.get("title")),
                "summary": clean_text(row.get("summary")),
                "confidence": safe_float(row.get("confidence", 0.0)),
                "signal_types_seen": signal_types_for_entity(entity_signals),
                "funny_name_candidate": bool(first_signal(entity_signals, "solana_funny_name_candidate")),
                "metadata_resolved": bool(first_signal(entity_signals, "solana_token_metadata_resolved")),
                "name_detected": bool(first_signal(entity_signals, "solana_token_name_detected")),
                "symbol_detected": bool(first_signal(entity_signals, "solana_token_symbol_detected")),
                "pumpfun_launch": bool(first_signal(entity_signals, "solana_pumpfun_launch")),
                "raydium_pool_init": bool(first_signal(entity_signals, "solana_raydium_pool_init")),
                "volume_velocity": bool(first_signal(entity_signals, "solana_volume_velocity")),
                "liquidity_depth": bool(first_signal(entity_signals, "solana_liquidity_depth")),
                "thin_liquidity_alert": bool(first_signal(entity_signals, "solana_thin_liquidity_alert")),
            }
        )

    return {
        "updated_at": utc_now_iso(),
        "trending": trending_cards,
        "watchlist": top_n(watchlist, 10),
        "narrative_candidates": top_n(narratives, 10),
        "summary": {
            "trending_count": len(trending),
            "watchlist_count": len(watchlist),
            "narrative_candidate_count": len(narratives),
        },
    }


# ---------------------------------------------------
# STRATEGY HEALTH
# ---------------------------------------------------

def build_strategy_health(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    adaptive_summary = snapshot.get("adaptive_strategy_weight_summary", {})
    adaptive_weights = object_rows(snapshot.get("adaptive_strategy_weights", []))
    adaptive_family_weights = object_rows(snapshot.get("adaptive_strategy_family_weights", []))
    strategy_performance = object_rows(snapshot.get("strategy_performance", []))

    return {
        "updated_at": utc_now_iso(),
        "adaptive_weight_summary": adaptive_summary,
        "adaptive_strategy_weights": adaptive_weights,
        "adaptive_family_weights": adaptive_family_weights,
        "strategy_performance": strategy_performance,
    }


# ---------------------------------------------------
# PAPER TRADING + PORTFOLIO
# ---------------------------------------------------

def build_portfolio_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    paper = snapshot.get("paper_trading", {})
    execution_plan = snapshot.get("execution_plan", {})
    order_lifecycle = object_rows(snapshot.get("order_lifecycle", []))
    position_risk = object_rows(snapshot.get("position_risk", []))

    orders = object_rows(execution_plan.get("orders", []))
    open_orders = [o for o in orders if clean_text(o.get("status")).lower() not in {"closed", "filled", "cancelled"}]
    closed_orders = [o for o in orders if clean_text(o.get("status")).lower() in {"closed", "filled"}]

    return {
        "updated_at": utc_now_iso(),
        "paper_trading": paper,
        "execution_plan_summary": execution_plan.get("summary", {}),
        "open_orders": open_orders,
        "closed_orders": closed_orders,
        "order_lifecycle": order_lifecycle,
        "position_risk": position_risk,
        "summary": {
            "open_order_count": len(open_orders),
            "closed_order_count": len(closed_orders),
            "position_risk_count": len(position_risk),
        },
    }


# ---------------------------------------------------
# RISK BOARD
# ---------------------------------------------------

def build_risk_board(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    kill_switch = snapshot.get("kill_switch", {})
    risks = object_rows(snapshot.get("risks", []))
    market_stress = snapshot.get("market_stress", {})
    market_structure = snapshot.get("market_structure", {})

    return {
        "updated_at": utc_now_iso(),
        "kill_switch": kill_switch,
        "risks": risks,
        "market_stress": market_stress,
        "market_structure": market_structure,
        "summary": {
            "risk_count": len(risks),
            "kill_switch_active": bool(kill_switch.get("is_active", False)) if isinstance(kill_switch, dict) else False,
        },
    }


# ---------------------------------------------------
# TOP ENTITY TABLE
# ---------------------------------------------------

def build_top_entity_table(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    metrics = snapshot.get("metrics", {})
    top_entities = metrics.get("top_entities", [])

    out: List[Dict[str, Any]] = []

    if isinstance(top_entities, list):
        for row in top_entities:
            if not isinstance(row, list) or len(row) < 2:
                continue

            out.append(
                {
                    "entity": clean_text(row[0]),
                    "signal_count": safe_int(row[1], 0),
                }
            )

    return out


# ---------------------------------------------------
# MASTER VIEW
# ---------------------------------------------------

def build_trading_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "view_name": "trading",
        "updated_at": utc_now_iso(),
        "market_overview": build_market_overview(snapshot),
        "trade_board": build_trade_board(snapshot),
        "memecoin_board": build_memecoin_board(snapshot),
        "strategy_health": build_strategy_health(snapshot),
        "portfolio": build_portfolio_view(snapshot),
        "risk_board": build_risk_board(snapshot),
        "top_entities": build_top_entity_table(snapshot),
    }


def run_trading_view_engine() -> Dict[str, Any]:
    snapshot = load_snapshot()
    view = build_trading_view(snapshot)
    write_json_atomic(OUTPUT_PATH, TMP_OUTPUT_PATH, view)
    return view


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    payload = run_trading_view_engine()
    print(json.dumps(payload, indent=2))
