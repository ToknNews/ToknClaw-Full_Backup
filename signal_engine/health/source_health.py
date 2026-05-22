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
# MODULE: source_health
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations
from typing import Any, Dict


def ok(name: str, count: int = 0, note: str = "") -> Dict[str, Any]:
    return {
        "name": name,
        "status": "ok",
        "count": count,
        "note": note,
    }


def degraded(name: str, note: str = "") -> Dict[str, Any]:
    return {
        "name": name,
        "status": "degraded",
        "count": 0,
        "note": note,
    }


def failed(name: str, note: str = "") -> Dict[str, Any]:
    return {
        "name": name,
        "status": "failed",
        "count": 0,
        "note": note,
    }


def summarize(collectors: Dict[str, Dict[str, Any]]) -> str:
    statuses = [v.get("status", "unknown") for v in collectors.values()]
    if not statuses:
        return "unknown"
    if all(s == "ok" for s in statuses):
        return "ok"
    if any(s == "failed" for s in statuses):
        return "degraded"
    return "degraded"
