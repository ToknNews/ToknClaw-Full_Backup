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
# MODULE: engine_registry
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

TOKNCLAW ENGINE REGISTRY
Central engine loader for the entire platform.

Purpose
-------
• stabilize imports
• allow hot-swappable engines
• enable OpenClaw agents to call engines
• eliminate snapshot import breakage
"""

from __future__ import annotations

import importlib
from typing import Callable, Dict


ENGINE_MAP = {
    "portfolio_risk": ("pipeline.position_risk_engine", "build_position_risk"),
    "execution_plan": ("pipeline.execution_router_engine", "build_execution_router"),
    "portfolio": ("pipeline.portfolio_construction_engine", "build_portfolio"),
    "portfolio_optimization": ("pipeline.portfolio_optimization_engine", "build_portfolio_optimization"),
    "strategy_simulation": ("pipeline.strategy_simulation_engine", "build_strategy_simulation"),
    "strategy_performance": ("pipeline.strategy_performance_engine", "build_strategy_performance"),
}


_ENGINE_CACHE: Dict[str, Callable] = {}


def get_engine(engine_name: str) -> Callable:
    """
    Returns a callable engine.

    Example
    -------
    engine = get_engine("portfolio_risk")
    result = engine(snapshot)
    """

    if engine_name in _ENGINE_CACHE:
        return _ENGINE_CACHE[engine_name]

    if engine_name not in ENGINE_MAP:
        raise RuntimeError(f"Engine not registered: {engine_name}")

    module_name, func_name = ENGINE_MAP[engine_name]

    module = importlib.import_module(module_name)

    func = getattr(module, func_name)

    _ENGINE_CACHE[engine_name] = func

    return func
