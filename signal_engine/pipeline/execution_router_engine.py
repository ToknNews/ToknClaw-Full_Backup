#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — EXECUTION ROUTER ENGINE
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
# MODULE: execution_router_engine
# PURPOSE:
# - Accept execution intents from paper_trading_engine
# - Select execution venue
# - Write durable execution intent records
# - Keep live execution disabled until explicitly enabled
# - Preserve dashboard execution-router output compatibility
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------
# PATHS / CONFIG
# ---------------------------------------------------

EXECUTION_MODE = "paper"  # paper | dry_run | live


EXECUTION_DIR = Path("/opt/toknclaw/data/execution")
LATEST_INTENTS_PATH = EXECUTION_DIR / "latest_execution_intents.json"
INTENT_LOG_PATH = EXECUTION_DIR / "execution_intent_log.json"

TRADING_UNIVERSE_PATH = Path("/opt/toknclaw/config/trading_universe.json")
HYPERLIQUID_UNIVERSE_PATH = Path("/opt/toknclaw/data/analytics/hyperliquid_universe.json")

MAX_INTENT_LOG_ROWS = 1000

HYPERLIQUID_SUPPORTED_ENTITIES = {
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "DOGE",
    "LINK",
    "AVAX",
    "ARB",
    "OP",
    "INJ",
    "PYTH",
    "JUP",
    "RNDR",
}


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _safe_str(v: Any) -> str:
    return str(v or "").strip()


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_path.replace(path)


def _hyperliquid_entities_from_trading_universe() -> set:
    cfg = _safe_dict(_read_json(TRADING_UNIVERSE_PATH, {}))
    tiers = _safe_dict(cfg.get("tiers"))

    entities = set()

    for _, rows in tiers.items():
        if not isinstance(rows, list):
            continue

        for asset in rows:
            asset = _safe_str(asset).upper()
            if asset:
                entities.add(asset)

    return entities


def _hyperliquid_entities_from_discovery() -> set:
    payload = _safe_dict(_read_json(HYPERLIQUID_UNIVERSE_PATH, {}))

    entities = set()

    for row in _safe_list(payload.get("markets")):
        row = _safe_dict(row)

        if bool(row.get("is_delisted", False)):
            continue

        name = _safe_str(row.get("name")).upper()
        mid = _safe_float(row.get("mid"), 0.0)

        if name and mid > 0:
            entities.add(name)

    for asset in _safe_list(payload.get("new_assets")):
        asset = _safe_str(asset).upper()
        if asset:
            entities.add(asset)

    return entities


def _hyperliquid_supported_entities() -> set:
    entities = set()

    try:
        entities.update(HYPERLIQUID_SUPPORTED_ENTITIES)
    except Exception:
        pass

    entities.update(_hyperliquid_entities_from_trading_universe())
    entities.update(_hyperliquid_entities_from_discovery())

    return {
        _safe_str(asset).upper()
        for asset in entities
        if _safe_str(asset)
    }


def _venue_for_entity(entity: str) -> str:
    entity = _safe_str(entity).upper()

    if not entity:
        return "unsupported"

    if entity in _hyperliquid_supported_entities():
        return "hyperliquid"

    return "unsupported"

def _priority_for_order(size_usd: float, confidence: float) -> str:
    if size_usd >= 500 or confidence >= 0.85:
        return "high"

    if size_usd >= 250 or confidence >= 0.70:
        return "medium"

    return "low"


def _normalize_side(side: str) -> str:
    side = _safe_str(side).lower()

    if side in {"long", "buy"}:
        return "long"

    if side in {"short", "sell"}:
        return "short"

    return "unknown"


def _intent_status_for_mode(mode: str, venue: str) -> str:
    if venue == "unsupported":
        return "rejected_unsupported_venue"

    if mode == "paper":
        return "paper_recorded"

    if mode == "dry_run":
        return "dry_run_ready"

    if mode == "live":
        return "live_pending_adapter"

    return "unknown_mode"


def _append_intent_log(intent: Dict[str, Any]) -> None:
    rows = _read_json(INTENT_LOG_PATH, [])

    if not isinstance(rows, list):
        rows = []

    rows.append(intent)
    rows = rows[-MAX_INTENT_LOG_ROWS:]

    _write_json_atomic(INTENT_LOG_PATH, rows)


def _write_latest_intent(intent: Dict[str, Any]) -> None:
    payload = {
        "schema_version": 1,
        "updated_at": _now_iso(),
        "execution_mode": EXECUTION_MODE,
        "latest_intent": intent,
    }

    _write_json_atomic(LATEST_INTENTS_PATH, payload)


# ---------------------------------------------------
# EXECUTION ENTRYPOINT
# ---------------------------------------------------

def route_execution(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Primary execution bridge.

    Called by paper_trading_engine when a paper position is opened.

    This function intentionally does NOT place live orders yet.
    It writes a durable intent that the future Hyperliquid adapter can consume.
    """

    order = _safe_dict(order)

    trade_id = _safe_str(order.get("trade_id"))
    entity = _safe_str(order.get("entity")).upper()
    side = _normalize_side(order.get("side"))
    direction = _safe_str(order.get("direction"))
    size_usd = _safe_float(order.get("size_usd"), 0.0)
    confidence = _safe_float(order.get("confidence"), 0.0)
    strategy = _safe_str(order.get("strategy"))
    setup_family = _safe_str(order.get("setup_family"))
    position_key = _safe_str(order.get("position_key"))
    entry_price_usd = _safe_float(order.get("entry_price_usd"), 0.0)
    quantity = _safe_float(order.get("quantity"), 0.0)
    source = _safe_str(order.get("source")) or "unknown"

    venue = _venue_for_entity(entity)
    priority = _priority_for_order(size_usd=size_usd, confidence=confidence)
    status = _intent_status_for_mode(EXECUTION_MODE, venue)

    intent = {
        "schema_version": 1,
        "created_at": _now_iso(),
        "status": status,
        "execution_mode": EXECUTION_MODE,
        "venue": venue,
        "priority": priority,
        "trade_id": trade_id,
        "entity": entity,
        "side": side,
        "direction": direction,
        "size_usd": round(size_usd, 4),
        "confidence": round(confidence, 6),
        "strategy": strategy,
        "setup_family": setup_family,
        "position_key": position_key,
        "entry_price_usd": round(entry_price_usd, 12),
        "quantity": round(quantity, 12),
        "source": source,
        "notes": [],
    }

    if not trade_id:
        intent["notes"].append("missing_trade_id")

    if side == "unknown":
        intent["notes"].append("unknown_side")

    if size_usd <= 0:
        intent["status"] = "rejected_invalid_size"
        intent["notes"].append("size_usd_must_be_positive")

    if venue == "unsupported":
        intent["notes"].append("entity_not_supported_for_hyperliquid")

    print(
        f"[EXECUTION ROUTER] mode={EXECUTION_MODE} "
        f"status={intent['status']} "
        f"{entity} {side} ${round(size_usd, 4)} via {venue}",
        flush=True,
    )

    _write_latest_intent(intent)
    _append_intent_log(intent)

    try:
        from signal_engine.pipeline.execution_risk_gate import evaluate_latest_intent

        risk_decision = evaluate_latest_intent()
        intent["risk_status"] = risk_decision.get("status")
        intent["risk_reasons"] = risk_decision.get("reasons", [])

    except Exception as e:
        risk_decision = {
            "status": "error",
            "reasons": [str(e)],
        }
        intent["risk_status"] = "error"
        intent["risk_reasons"] = [str(e)]
        print(f"[EXECUTION RISK ERROR] {e}", flush=True)

    # ---------------------------------------------------
    # HYPERLIQUID ADAPTER HOOK
    # ---------------------------------------------------
    # Safe by design:
    # - adapter refuses rejected risk decisions
    # - adapter refuses paper mode exchange orders
    # - adapter refuses missing live credentials
    # - live order placement is not implemented yet
    try:
        from signal_engine.pipeline.hyperliquid_execution_adapter import process_latest_risk_decision

        exchange_result = process_latest_risk_decision()
        intent["exchange_status"] = exchange_result.get("status")
        intent["exchange_reason"] = exchange_result.get("reason") or exchange_result.get("message")

    except Exception as e:
        intent["exchange_status"] = "error"
        intent["exchange_reason"] = str(e)
        print(f"[HYPERLIQUID ADAPTER ERROR] {e}", flush=True)


    if EXECUTION_MODE == "paper":
        print("[EXECUTION] Paper mode → intent recorded only", flush=True)

    elif EXECUTION_MODE == "dry_run":
        print("[EXECUTION] Dry-run mode → live adapter not called", flush=True)

    elif EXECUTION_MODE == "live":
        print("[EXECUTION] Live mode requested → waiting for adapter wiring", flush=True)

    return intent


# ---------------------------------------------------
# DASHBOARD / SNAPSHOT ROUTER OUTPUT
# ---------------------------------------------------

def build_execution_router(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Snapshot-facing router output for UI/API.

    This keeps compatibility with existing dashboard/snapshot fields.
    """

    snapshot = _safe_dict(snapshot)

    portfolio_opt = _safe_list(snapshot.get("portfolio_optimization"))
    exec_quality = _safe_list(snapshot.get("execution_quality"))

    quality_map = {
        _safe_str(_safe_dict(row).get("asset") or _safe_dict(row).get("entity")).upper(): _safe_dict(row)
        for row in exec_quality
        if _safe_str(_safe_dict(row).get("asset") or _safe_dict(row).get("entity"))
    }

    orders = []

    for row in portfolio_opt:
        row = _safe_dict(row)

        entity = _safe_str(row.get("entity")).upper()
        if not entity:
            continue

        confidence = _safe_float(row.get("confidence"), 0.0)
        position_size = _safe_float(row.get("position_size"), 0.0)
        quality = _safe_dict(quality_map.get(entity))

        venue = _venue_for_entity(entity)
        priority = _priority_for_order(size_usd=position_size, confidence=confidence)

        orders.append({
            "entity": entity,
            "direction": row.get("direction"),
            "venue": venue,
            "priority": priority,
            "position_size": round(position_size, 4),
            "confidence": round(confidence, 4),
            "expected_slippage": _safe_float(quality.get("expected_slippage"), 0.0015),
            "expected_fill_quality": quality.get("expected_fill_quality", "unknown"),
            "routing_state": "ready" if venue != "unsupported" else "unsupported",
        })

    orders.sort(
        key=lambda x: (
            x.get("priority") == "high",
            _safe_float(x.get("position_size"), 0.0),
            _safe_float(x.get("confidence"), 0.0),
            _safe_str(x.get("entity")),
        ),
        reverse=True,
    )

    summary = {
        "order_count": len(orders),
        "high_priority_count": sum(1 for order in orders if _safe_str(order.get("priority")) == "high"),
        "primary_venue": orders[0].get("venue") if orders else None,
        "execution_mode": EXECUTION_MODE,
    }

    alerts = []

    if summary["high_priority_count"] > 0:
        alerts.append({
            "type": "high_priority_orders",
            "severity": "medium",
            "title": "High priority execution routes are available",
        })

    return {
        "execution_router": orders,
        "execution_router_summary": summary,
        "execution_router_alerts": alerts,
        "execution_router_endpoints": {
            "execution_router": "/api/toknclaw/execution-router",
            "execution_router_summary": "/api/toknclaw/execution-router/summary",
            "execution_router_alerts": "/api/toknclaw/execution-router/alerts",
        },
    }


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    payload = route_execution({
        "trade_id": "manual_test",
        "entity": "BTC",
        "side": "long",
        "direction": "bullish",
        "size_usd": 25,
        "confidence": 0.5,
        "strategy": "manual_test",
        "setup_family": "manual_test",
        "position_key": "BTC::manual_test::long",
        "entry_price_usd": 0,
        "quantity": 0,
        "source": "manual",
    })

    print(json.dumps(payload, indent=2))
