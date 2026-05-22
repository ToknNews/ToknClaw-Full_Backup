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
# MODULE: order_lifecycle_engine
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

Order Lifecycle Engine
----------------------

Tracks the lifecycle of every order produced by the execution planner.

States
------
• created
• submitted
• partially_filled
• filled
• cancelled
• rejected

Used By
-------
• execution planner
• paper trading engine
• live exchange adapters
• portfolio tracking
• risk management

Design
------
• deterministic lifecycle tracking
• venue-agnostic order state model
• execution audit trail
• compatible with live trading connectors

Author: TOKN Systems
"""

from __future__ import annotations
from typing import Dict, Any
import time


# ---------------------------------------------------
# Time Utility
# ---------------------------------------------------

def _timestamp() -> int:
    return int(time.time())


# ---------------------------------------------------
# Order Initialization
# ---------------------------------------------------

def build_order_lifecycle(order: Dict[str, Any]) -> Dict[str, Any]:

    return {
        "order_id": order.get("order_id"),
        "entity": order.get("entity"),
        "side": order.get("side"),
        "size": order.get("size"),
        "price": order.get("price"),
        "venue": order.get("venue", "paper"),
        "strategy": order.get("strategy"),
        "state": "created",
        "created_at": _timestamp(),
        "submitted_at": None,
        "filled_at": None,
        "cancelled_at": None,
        "rejected_at": None,
        "fills": [],
        "execution_result": None,
    }


# ---------------------------------------------------
# Lifecycle Updates
# ---------------------------------------------------

def update_order_state(order: Dict[str, Any], state: str) -> Dict[str, Any]:

    now = _timestamp()

    if state == "submitted":
        order["submitted_at"] = now

    elif state == "filled":
        order["filled_at"] = now

    elif state == "cancelled":
        order["cancelled_at"] = now

    elif state == "rejected":
        order["rejected_at"] = now

    elif state == "partial":
        order.setdefault("fills", []).append({
            "timestamp": now
        })

    order["state"] = state

    return order


# ---------------------------------------------------
# Fill Recording
# ---------------------------------------------------

def record_fill(order: Dict[str, Any], fill: Dict[str, Any]) -> Dict[str, Any]:

    order.setdefault("fills", []).append(fill)

    if fill.get("complete"):
        order["state"] = "filled"
        order["filled_at"] = _timestamp()

    else:
        order["state"] = "partial"

    return order
