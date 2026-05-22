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
# MODULE: solana_shared
# PURPOSE: Shared Solana RPC and parsing utilities for ToknClaw collectors.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

Responsibilities
----------------
• load Solana RPC configuration deterministically
• provide shared Solana JSON-RPC request helpers
• provide shared Solana transaction parsing helpers
• avoid silent RPC misconfiguration across collectors
• keep collector-side Solana access centralized and reusable

Author: TOKN Systems
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests
from dotenv import load_dotenv


# ---------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------

ENV_PATH = Path("/opt/toknclaw/signal_engine/.env")
load_dotenv(ENV_PATH)

REQUEST_TIMEOUT = int(os.getenv("TOKN_SOL_RPC_TIMEOUT", "12"))
DEBUG = os.getenv("TOKN_DEBUG_COLLECTORS", "1") == "1"


# ---------------------------------------------------
# LOGGING
# ---------------------------------------------------

def debug_log(prefix: str, message: str) -> None:
    if DEBUG:
        print(f"[{prefix}] {message}")


# ---------------------------------------------------
# RPC RESOLUTION
# ---------------------------------------------------

def get_sol_rpc() -> Optional[str]:
    """
    Resolve Solana RPC dynamically so env loading order does not
    permanently poison the module with a None value.

    Resolution order:
    1. SOL_RPC
    2. SOLANA_RPC_URL
    """
    rpc_url = (
        os.getenv("SOL_RPC")
        or os.getenv("SOLANA_RPC_URL")
    )

    rpc_url = str(rpc_url or "").strip()

    if not rpc_url:
        return None

    return rpc_url


def require_sol_rpc(prefix: str = "SOLANA RPC") -> Optional[str]:
    rpc_url = get_sol_rpc()

    if not rpc_url:
        debug_log(prefix, "missing Solana RPC env (checked SOL_RPC, SOLANA_RPC_URL)")
        return None

    debug_log(prefix, f"using rpc host={rpc_url}")
    return rpc_url


# ---------------------------------------------------
# GENERIC HELPERS
# ---------------------------------------------------

def short_addr(value: str | None, head: int = 6, tail: int = 4) -> str:
    if not value:
        return "unknown"
    if len(value) <= head + tail + 3:
        return value
    return f"{value[:head]}...{value[-tail:]}"


def parse_csv_env(value: str | None) -> List[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def dedupe_keep_order(values: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)

    return out


# ---------------------------------------------------
# SOLANA RPC
# ---------------------------------------------------
import time
time.sleep(0.05)

def rpc(method: str, params: List[Any], prefix: str = "SOLANA RPC") -> Dict[str, Any] | None:
    rpc_url = require_sol_rpc(prefix=prefix)
    if not rpc_url:
        return None

    try:
        response = requests.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params,
            },
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            debug_log(prefix, f"HTTP {response.status_code} method={method}")
            return None

        data = response.json()

        if data.get("error"):
            debug_log(prefix, f"RPC error method={method} error={data['error']}")
            return None

        return data
    except Exception as exc:
        debug_log(prefix, f"RPC exception method={method} exc={exc}")
        return None


def get_signatures_for_address(
    address: str,
    limit: int,
    prefix: str = "SOLANA RPC",
) -> List[Dict[str, Any]]:
    data = rpc(
        "getSignaturesForAddress",
        [
            address,
            {"limit": limit},
        ],
        prefix=prefix,
    )

    if not data:
        return []

    result = data.get("result") or []
    if not isinstance(result, list):
        return []

    out: List[Dict[str, Any]] = []

    for item in result:
        if not isinstance(item, dict):
            continue
        if item.get("err") is not None:
            continue
        out.append(item)

    return out


def get_transaction(signature: str, prefix: str = "SOLANA RPC") -> Dict[str, Any] | None:
    data = rpc(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
            },
        ],
        prefix=prefix,
    )

    if not data:
        return None

    result = data.get("result")
    if not isinstance(result, dict):
        return None

    return result


def get_token_supply(mint: str, prefix: str = "SOLANA RPC") -> Dict[str, Any] | None:
    data = rpc("getTokenSupply", [mint], prefix=prefix)
    if not data:
        return None

    result = data.get("result") or {}
    value = result.get("value")
    if not isinstance(value, dict):
        return None

    return value


def get_token_largest_accounts(mint: str, prefix: str = "SOLANA RPC") -> List[Dict[str, Any]]:
    data = rpc("getTokenLargestAccounts", [mint], prefix=prefix)
    if not data:
        return []

    result = data.get("result") or {}
    value = result.get("value") or []
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


# ---------------------------------------------------
# TRANSACTION HELPERS
# ---------------------------------------------------

def get_log_messages(tx: Dict[str, Any]) -> List[str]:
    meta = tx.get("meta") or {}
    logs = meta.get("logMessages") or []
    if not isinstance(logs, list):
        return []
    return [x for x in logs if isinstance(x, str)]


def flatten_instructions(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    transaction = tx.get("transaction") or {}
    message = transaction.get("message") or {}
    meta = tx.get("meta") or {}

    top_level = message.get("instructions") or []
    if isinstance(top_level, list):
        for ix in top_level:
            if isinstance(ix, dict):
                out.append(ix)

    inner_groups = meta.get("innerInstructions") or []
    if isinstance(inner_groups, list):
        for group in inner_groups:
            if not isinstance(group, dict):
                continue
            inner = group.get("instructions") or []
            if not isinstance(inner, list):
                continue
            for ix in inner:
                if isinstance(ix, dict):
                    out.append(ix)

    return out


def token_balance_deltas(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    meta = tx.get("meta") or {}
    pre = meta.get("preTokenBalances") or []
    post = meta.get("postTokenBalances") or []

    if not isinstance(pre, list):
        pre = []

    if not isinstance(post, list):
        post = []

    by_key: Dict[tuple, Dict[str, Any]] = {}

    for item in pre:
        if not isinstance(item, dict):
            continue
        key = (
            item.get("accountIndex"),
            item.get("mint"),
            item.get("owner"),
        )
        by_key[key] = {
            "accountIndex": item.get("accountIndex"),
            "mint": item.get("mint"),
            "owner": item.get("owner"),
            "pre": _ui_amount(item),
            "post": 0.0,
            "decimals": _decimals(item),
        }

    for item in post:
        if not isinstance(item, dict):
            continue
        key = (
            item.get("accountIndex"),
            item.get("mint"),
            item.get("owner"),
        )
        row = by_key.get(
            key,
            {
                "accountIndex": item.get("accountIndex"),
                "mint": item.get("mint"),
                "owner": item.get("owner"),
                "pre": 0.0,
                "post": 0.0,
                "decimals": _decimals(item),
            },
        )
        row["post"] = _ui_amount(item)
        row["decimals"] = _decimals(item)
        by_key[key] = row

    rows: List[Dict[str, Any]] = []

    for row in by_key.values():
        row["delta"] = float(row["post"]) - float(row["pre"])
        rows.append(row)

    return rows


def _ui_amount(item: Dict[str, Any]) -> float:
    ui = (item.get("uiTokenAmount") or {}).get("uiAmount")
    if ui is None:
        return 0.0
    try:
        return float(ui)
    except Exception:
        return 0.0


def _decimals(item: Dict[str, Any]) -> int:
    decimals = (item.get("uiTokenAmount") or {}).get("decimals")
    try:
        return int(decimals)
    except Exception:
        return 0
