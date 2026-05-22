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
# MODULE: snapshot_schema
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from datetime import datetime, UTC
from typing import Any, Dict, List


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def empty_snapshot() -> Dict[str, Any]:
    return {
        "timestamp": utc_now_iso(),
        "signals": [],
        "metrics": {},
        "analysis": {},
        "memory": {},
        "deltas": {},
        "verticals": {
            "markets": {},
            "onchain": {},
            "macro": {},
            "defi": {},
            "culture": {},
            "policy": {},
            "ai": {},
        },
        "retail_pulse": {
            "reddit_top_tokens": [],
            "x_trending": [],
            "memecoin_rotation": False,
            "retail_sentiment": "unknown",
            "notes": [],
        },
        "watchlists": {},
        "entities": {},
        "risks": {
            "primary": [],
            "contradictions": [],
        },
        "calendar": {
            "upcoming_events": [],
        },
        "source_health": {
            "collectors": {},
            "overall_status": "unknown",
        },
    }


def signal_to_dict(signal: Any) -> Dict[str, Any]:
    if hasattr(signal, "__dict__"):
        data = dict(signal.__dict__)
    elif isinstance(signal, dict):
        data = dict(signal)
    else:
        data = {"value": str(signal)}

    ts = data.get("timestamp")
    if hasattr(ts, "isoformat"):
        data["timestamp"] = ts.isoformat()

    return data


def normalize_signals(signals: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in signals or []:
        out.append(signal_to_dict(s))
    return out
