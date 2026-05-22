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
# MODULE: signal_lake
# PURPOSE: Central storage utility for rolling signal ingestion
#
# AUTHOR: TOKN SYSTEM
# ============================================================


Responsibilities
----------------
• append newly collected signals
• normalize Signal objects for JSON storage
• trim stale signals by time window
• cap total signal count
• track collector run metadata
• support collector daemon and streaming daemons
• support snapshot ingestion

Primary Output
--------------
/opt/toknclaw/data/signal_lake.json

Author: TOKN Systems
"""

from __future__ import annotations

# ---------------------------------------------------
# BOOTSTRAP (CRITICAL FIX)
# ---------------------------------------------------

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------
# IMPORTS
# ---------------------------------------------------

import json
import os
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from dotenv import load_dotenv
from signal_engine.schema.snapshot_schema import signal_to_dict

# ---------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------

ENV_PATH = "/opt/toknclaw/signal_engine/.env"
load_dotenv(ENV_PATH)

SIGNAL_LAKE_PATH = Path("/opt/toknclaw/data/signal_lake.json")
SIGNAL_LAKE_PATH.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_MAX_SIGNALS = int(os.getenv("TOKN_SIGNAL_LAKE_MAX_SIGNALS", "10000"))
DEFAULT_RETENTION_MINUTES = int(os.getenv("TOKN_SIGNAL_LAKE_RETENTION_MINUTES", "30"))

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _utc_now_iso() -> str:
    return _utc_now().isoformat()

def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if not isinstance(value, str):
        return None

    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _hash_signal(row: Dict[str, Any]) -> str:
    key = f"{row.get('entity')}|{row.get('signal_type')}|{row.get('timestamp')}"
    return hashlib.sha256(key.encode()).hexdigest()

def _dedupe(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []

    for row in signals:
        h = _hash_signal(row)
        if h in seen:
            continue
        seen.add(h)
        out.append(row)

    return out

def _ensure_lake_shape(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"updated_at": None, "signals": [], "collector_runs": {}}

    data.setdefault("updated_at", None)
    data.setdefault("signals", [])
    data.setdefault("collector_runs", {})

    return data

def _trim_by_time(signals: List[Dict[str, Any]], minutes: int) -> List[Dict[str, Any]]:
    cutoff = _utc_now() - timedelta(minutes=minutes)
    return [s for s in signals if (_parse_ts(s.get("timestamp")) or cutoff) >= cutoff]

def _trim_by_count(signals: List[Dict[str, Any]], max_signals: int) -> List[Dict[str, Any]]:
    return signals[-max_signals:] if len(signals) > max_signals else signals

def _normalize(signals: List[Any]) -> List[Dict[str, Any]]:
    out = []

    for s in signals or []:
        try:
            row = signal_to_dict(s)
        except Exception:
            row = {"value": str(s)}

        if not row.get("timestamp"):
            row["timestamp"] = _utc_now_iso()

        out.append(row)

    return out

# ---------------------------------------------------
# PUBLIC API
# ---------------------------------------------------

def load_signal_lake() -> Dict[str, Any]:
    if not SIGNAL_LAKE_PATH.exists():
        return {"updated_at": None, "signals": [], "collector_runs": {}}

    try:
        return _ensure_lake_shape(json.load(open(SIGNAL_LAKE_PATH)))
    except:
        return {"updated_at": None, "signals": [], "collector_runs": {}}

def save_signal_lake(data: Dict[str, Any]) -> None:
    tmp = SIGNAL_LAKE_PATH.with_suffix(".tmp")

    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)

    tmp.replace(SIGNAL_LAKE_PATH)

def append_signals(
    new_signals: List[Any],
    collector_name: str,
    max_signals: int = DEFAULT_MAX_SIGNALS,
    retention_minutes: int = DEFAULT_RETENTION_MINUTES,
) -> Dict[str, Any]:

    lake = load_signal_lake()

    normalized = _normalize(new_signals)
    existing = lake.get("signals", [])

    combined = existing + normalized

    # 🔥 NEW: DEDUPE
    combined = _dedupe(combined)

    combined = _trim_by_time(combined, retention_minutes)
    combined = _trim_by_count(combined, max_signals)

    lake["signals"] = combined
    lake["updated_at"] = _utc_now_iso()

    lake.setdefault("collector_runs", {})[collector_name] = {
        "last_run_at": _utc_now_iso(),
        "count": len(normalized),
    }

    save_signal_lake(lake)

    return lake

def compact_signal_lake() -> Dict[str, Any]:
    return append_signals([], "compaction")
