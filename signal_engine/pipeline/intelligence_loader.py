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
# MODULE: intelligence_loader
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
intelligence_loader.py

Engine registry + execution framework.

Automatically discovers intelligence engines and executes them in priority order.

Each engine module must expose:

ENGINE_ID
ENGINE_PRIORITY
ENGINE_TAGS
ENGINE_ENABLED
run(snapshot: dict) -> dict

Return value from run() will be merged into snapshot.

Features
--------
• Engine auto discovery
• Priority execution ordering
• Runtime monitoring
• Failure isolation
• Output merging
• Engine health reporting
• Future ready for agents / scheduling
"""

from __future__ import annotations

import importlib
import pkgutil
import inspect
import time
from typing import Dict, Any, List

ENGINE_PACKAGE = "pipeline.engines"


def discover_engines() -> List[Dict[str, Any]]:

    engines = []

    try:
        package = importlib.import_module(ENGINE_PACKAGE)
    except Exception as e:
        print(f"[ENGINE] package load failed: {e}")
        return engines

    for _, module_name, _ in pkgutil.walk_packages(
        package.__path__,
        package.__name__ + "."
    ):

        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            print(f"[ENGINE] import failed {module_name}: {e}")
            continue

        run_func = getattr(module, "run", None)

        if not callable(run_func):
            continue

        engine_id = getattr(module, "ENGINE_ID", module_name)
        priority = getattr(module, "ENGINE_PRIORITY", 1000)
        enabled = getattr(module, "ENGINE_ENABLED", True)
        tags = getattr(module, "ENGINE_TAGS", [])

        engines.append({
            "id": engine_id,
            "module": module_name,
            "priority": priority,
            "enabled": enabled,
            "tags": tags,
            "function": run_func
        })

    engines.sort(key=lambda x: x["priority"])

    return engines


def run_intelligence_engines(snapshot: Dict[str, Any]) -> Dict[str, Any]:

    engines = discover_engines()

    engine_health = {}

    for engine in engines:

        if not engine["enabled"]:
            continue

        engine_id = engine["id"]
        func = engine["function"]

        start = time.time()

        try:

            output = func(snapshot) or {}

            if isinstance(output, dict):

                for key, value in output.items():

                    if key not in snapshot:
                        snapshot[key] = value

            runtime = int((time.time() - start) * 1000)

            engine_health[engine_id] = {
                "status": "ok",
                "runtime_ms": runtime,
                "module": engine["module"]
            }

        except Exception as e:

            runtime = int((time.time() - start) * 1000)

            print(f"[ENGINE ERROR] {engine_id}: {e}")

            engine_health[engine_id] = {
                "status": "failed",
                "runtime_ms": runtime,
                "module": engine["module"],
                "error": str(e)
            }

    snapshot.setdefault("engine_health", {})
    snapshot["engine_health"].update(engine_health)

    return snapshot
