#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — HYPERLIQUID EXECUTION ADAPTER
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
# MODULE: hyperliquid_execution_adapter
# PURPOSE:
# - Consume approved execution-risk decisions
# - Refuse rejected or unsafe intents
# - Support dry-run validation before live trading
# - Write durable exchange-result audit files
# - Keep real order placement disabled until explicitly wired
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

RISK_DECISION_PATH = Path("/opt/toknclaw/data/execution/latest_risk_decision.json")
LATEST_RESULT_PATH = Path("/opt/toknclaw/data/execution/latest_exchange_result.json")
RESULT_LOG_PATH = Path("/opt/toknclaw/data/execution/exchange_result_log.json")

MAX_RESULT_LOG_ROWS = 1000


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

def append_result_log(result: Dict[str, Any]) -> None:
    rows = read_json(RESULT_LOG_PATH, [])

    if not isinstance(rows, list):
        rows = []

    rows.append(result)
    rows = rows[-MAX_RESULT_LOG_ROWS:]

    write_json_atomic(RESULT_LOG_PATH, rows)


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_str(value: Any) -> str:
    return str(value or "").strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def env_status() -> Dict[str, bool]:
    return {
        "HYPERLIQUID_PRIVATE_KEY": bool(os.getenv("HYPERLIQUID_PRIVATE_KEY")),
        "HYPERLIQUID_WALLET_ADDRESS": bool(os.getenv("HYPERLIQUID_WALLET_ADDRESS")),
        "HYPERLIQUID_API_URL": bool(os.getenv("HYPERLIQUID_API_URL")),
    }


# ---------------------------------------------------
# CORE ADAPTER
# ---------------------------------------------------

def build_rejection_result(decision: Dict[str, Any], reason: str) -> Dict[str, Any]:
    intent = safe_dict(decision.get("intent"))

    return {
        "schema_version": 1,
        "created_at": utc_now(),
        "status": "skipped",
        "reason": reason,
        "exchange": "hyperliquid",
        "trade_id": safe_str(decision.get("trade_id") or intent.get("trade_id")),
        "entity": safe_str(decision.get("entity") or intent.get("entity")).upper(),
        "side": safe_str(decision.get("side") or intent.get("side")).lower(),
        "execution_mode": safe_str(decision.get("execution_mode") or intent.get("execution_mode")),
        "risk_status": safe_str(decision.get("status")),
        "risk_reasons": decision.get("reasons", []),
        "env": env_status(),
        "intent": intent,
    }


def dry_run_order(decision: Dict[str, Any]) -> Dict[str, Any]:
    intent = safe_dict(decision.get("intent"))

    entity = safe_str(decision.get("entity") or intent.get("entity")).upper()
    side = safe_str(decision.get("side") or intent.get("side")).lower()
    size_usd = safe_float(decision.get("size_usd") or intent.get("size_usd"), 0.0)
    trade_id = safe_str(decision.get("trade_id") or intent.get("trade_id"))

    return {
        "schema_version": 1,
        "created_at": utc_now(),
        "status": "dry_run_success",
        "exchange": "hyperliquid",
        "trade_id": trade_id,
        "entity": entity,
        "side": side,
        "size_usd": round(size_usd, 4),
        "execution_mode": safe_str(decision.get("execution_mode") or intent.get("execution_mode")),
        "message": "Dry-run only. No live order placed.",
        "env": env_status(),
        "intent": intent,
    }


def live_order_placeholder(decision: Dict[str, Any]) -> Dict[str, Any]:
    intent = safe_dict(decision.get("intent"))

    missing = [
        key for key, is_set in env_status().items()
        if key in {"HYPERLIQUID_PRIVATE_KEY", "HYPERLIQUID_WALLET_ADDRESS"} and not is_set
    ]

    if missing:
        return {
            "schema_version": 1,
            "created_at": utc_now(),
            "status": "blocked_missing_credentials",
            "exchange": "hyperliquid",
            "missing": missing,
            "message": "Live order blocked because credentials are not configured.",
            "env": env_status(),
            "intent": intent,
        }

    return {
        "schema_version": 1,
        "created_at": utc_now(),
        "status": "live_not_implemented",
        "exchange": "hyperliquid",
        "message": "Live adapter shell reached, but real order placement is intentionally not implemented yet.",
        "env": env_status(),
        "intent": intent,
    }


def process_latest_risk_decision() -> Dict[str, Any]:
    decision = safe_dict(read_json(RISK_DECISION_PATH, {}))

    if not decision:
        result = {
            "schema_version": 1,
            "created_at": utc_now(),
            "status": "skipped",
            "reason": "missing_latest_risk_decision",
            "exchange": "hyperliquid",
            "env": env_status(),
        }

    elif safe_str(decision.get("status")) != "approved":
        result = build_rejection_result(decision, "risk_decision_not_approved")

    else:
        execution_mode = safe_str(decision.get("execution_mode")).lower()

        if execution_mode in {"paper", ""}:
            result = build_rejection_result(decision, "paper_mode_no_exchange_order")

        elif execution_mode == "dry_run":
            result = dry_run_order(decision)

        elif execution_mode == "live":
            result = live_order_placeholder(decision)

        else:
            result = build_rejection_result(decision, f"unknown_execution_mode:{execution_mode}")

    write_json_atomic(LATEST_RESULT_PATH, result)
    append_result_log(result)

    print(
        f"[HYPERLIQUID ADAPTER] status={result.get('status')} "
        f"entity={result.get('entity')} "
        f"side={result.get('side')} "
        f"reason={result.get('reason') or result.get('message')}",
        flush=True,
    )

    return result


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    output = process_latest_risk_decision()
    print(json.dumps(output, indent=2))
