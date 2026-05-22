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
# MODULE: collector_loader
# PURPOSE: Discovers, registers, prioritizes, and executes ToknClaw collectors.
#
# AUTHOR: TOKN SYSTEM
# ============================================================

Responsibilities
----------------
• dynamically import collector modules so decorators execute
• discover collector functions deterministically
• apply manifest and runtime overrides
• execute collectors by tier
• isolate collector failures without killing the pipeline
• return aggregated signals and collector health

Author: TOKN Systems
"""

from __future__ import annotations

from signal_engine import bootstrap
import bootstrap
import importlib
import inspect
import json
import os
import pkgutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Tuple

from signal_engine.collectors.registry import get_registry
from signal_engine.pipeline.collector_tiers import build_execution_plan


COLLECTOR_PACKAGE = "signal_engine.collectors"

REGISTRY_PATH = Path("/opt/toknclaw/config/collector_manifest.json")
RUNTIME_CONFIG_PATH = Path("/opt/toknclaw/config/collector_settings.json")

DEFAULT_PRIORITY = int(os.getenv("TOKN_COLLECTOR_DEFAULT_PRIORITY", "100"))
DEFAULT_TIMEOUT_SEC = float(os.getenv("TOKN_COLLECTOR_TIMEOUT_SEC", "10"))
DEFAULT_MAX_WORKERS = int(os.getenv("TOKN_COLLECTOR_MAX_WORKERS", "8"))


# ---------------------------------------------------
# FORCE IMPORT (CRITICAL FOR DECORATORS)
# ---------------------------------------------------

def force_import_collectors() -> None:
    """
    Ensure all collector modules are imported so that
    @register_collector decorators execute and populate
    COLLECTOR_REGISTRY.
    """

    try:
        package = importlib.import_module(COLLECTOR_PACKAGE)
    except Exception as e:
        print(f"[COLLECTOR LOADER] failed to import base package: {e}")
        return

    modules = pkgutil.walk_packages(
        package.__path__,
        package.__name__ + ".",
    )

    count = 0

    for _, module_name, _ in modules:
        try:
            importlib.import_module(module_name)
            count += 1
        except Exception as e:
            print(f"[COLLECTOR] import failed {module_name}: {e}")

    print(f"[COLLECTOR LOADER] force-imported modules={count}")


# ---------------------------------------------------
# ENVIRONMENT FILTERS
# ---------------------------------------------------

ENABLED_COLLECTORS = {
    x.strip().lower()
    for x in os.getenv("TOKN_COLLECTOR_ENABLED", "").split(",")
    if x.strip()
}

DISABLED_COLLECTORS = {
    x.strip().lower()
    for x in os.getenv("TOKN_COLLECTOR_DISABLED", "").split(",")
    if x.strip()
}


# ---------------------------------------------------
# RUNTIME CONFIG (OpenClaw editable)
# ---------------------------------------------------

CFG_ENABLED = set()
CFG_DISABLED = set()

if RUNTIME_CONFIG_PATH.exists():
    try:
        with open(RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        CFG_ENABLED = {
            x.strip().lower()
            for x in cfg.get("enabled_collectors", [])
            if isinstance(x, str)
        }

        CFG_DISABLED = {
            x.strip().lower()
            for x in cfg.get("disabled_collectors", [])
            if isinstance(x, str)
        }

    except Exception as e:
        print(f"[COLLECTOR CONFIG] failed to load runtime config: {e}")


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------
def split_collectors(collectors):
    fast = []
    slow = []

    for c in collectors:
        if c.get("execution") == "fast":
            fast.append(c)
        else:
            slow.append(c)

    return fast, slow


def _safe_int(v: Any, d: int) -> int:
    try:
        return int(v)
    except Exception:
        return d


def _safe_float(v: Any, d: float) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _normalize_signal_output(result: Any) -> List[Any]:
    if result is None:
        return []

    if isinstance(result, list):
        return result

    if isinstance(result, tuple):
        return list(result)

    if isinstance(result, dict):
        return [result]

    try:
        return list(result)
    except Exception:
        return []


def _normalize_tags(tags: Any) -> List[str]:
    if tags is None:
        return []

    if not isinstance(tags, list):
        tags = [tags]

    return [str(t).strip().lower() for t in tags if str(t).strip()]


def _normalize_category(category: Any) -> str | None:
    if category is None:
        return None

    category = str(category).strip().lower()
    return category or None


def _collector_lookup_keys(
    collector_name: str,
    module_name: str,
    collector_id: str | None = None,
) -> set[str]:
    keys = {
        collector_name.lower(),
        module_name.lower(),
        f"{module_name.lower()}:{collector_name.lower()}",
    }

    if collector_id:
        keys.add(str(collector_id).lower())

    return keys


# ---------------------------------------------------
# ENABLE / DISABLE FILTER
# ---------------------------------------------------

def _is_enabled(
    collector_name: str,
    module_name: str,
    collector_id: str | None,
    enabled_flag: bool,
) -> bool:
    if not enabled_flag:
        return False

    keys = _collector_lookup_keys(collector_name, module_name, collector_id)

    if ENABLED_COLLECTORS and not (keys & ENABLED_COLLECTORS):
        return False

    if keys & DISABLED_COLLECTORS:
        return False

    if CFG_ENABLED and not (keys & CFG_ENABLED):
        return False

    if keys & CFG_DISABLED:
        return False

    return True


# ---------------------------------------------------
# MANIFEST REGISTRY
# ---------------------------------------------------

def _load_manifest_registry() -> Dict[str, Dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return {}

    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    registry: Dict[str, Dict[str, Any]] = {}

    for c in data.get("collectors", []):
        module = c.get("module")
        function = c.get("function")

        if not module or not function:
            continue

        key = f"{module}:{function}"

        registry[key] = {
            "priority": _safe_int(c.get("priority"), DEFAULT_PRIORITY),
            "timeout_sec": _safe_float(c.get("timeout_sec"), DEFAULT_TIMEOUT_SEC),
            "enabled": bool(c.get("enabled", True)),
            "tags": _normalize_tags(c.get("tags") or []),
            "id": c.get("id"),
            "category": _normalize_category(c.get("category")),
        }

    return registry


# ---------------------------------------------------
# DISCOVERY
# ---------------------------------------------------

def discover_collectors() -> List[Dict[str, Any]]:
    registry = get_registry()
    collectors = []

    for name, meta in registry.items():

        # ---------------------------------------------------
        # AUTO TIER ASSIGNMENT (NO MANUAL EDITING)
        # ---------------------------------------------------

        n = name.lower()

        if any(x in n for x in [
            "jupiter", "raydium", "liquidity", "mev", "velocity", "whale"
        ]):
            tier = "tier_1"

        elif any(x in n for x in [
            "strategy", "allocator", "dip", "momentum", "migration"
        ]):
            tier = "tier_2"

        elif any(x in n for x in [
            "meta", "narrative", "name", "culture"
        ]):
            tier = "tier_3"

        else:
            tier = "tier_4"

        collectors.append(
            {
                "collector_name": name,
                "collector_id": meta.get("id"),
                "module": meta.get("module"),
                "function": meta.get("function"),
                "priority": int(meta.get("priority", DEFAULT_PRIORITY)),
                "timeout_sec": float(meta.get("timeout", DEFAULT_TIMEOUT_SEC)),
                "tags": meta.get("tags", []),
                "category": meta.get("category"),
                "execution": meta.get("execution") or "fast",
                "tier": tier,
            }
        )

    collectors.sort(
        key=lambda x: (
            -int(x.get("priority", DEFAULT_PRIORITY)),
            x.get("collector_name", ""),
        )
    )

    return collectors

# ---------------------------------------------------
# EXECUTION
# ---------------------------------------------------

def _execute_collector(collector: Dict[str, Any]) -> Dict[str, Any]:
    name = collector["collector_name"]
    module = collector["module"]
    func = collector["function"]

    print(f"[EXEC] running {name}")

    start = time.perf_counter()

    try:
        raw = func()
        signals = _normalize_signal_output(raw)
        runtime_ms = int((time.perf_counter() - start) * 1000)

        status = "ok" if signals else "degraded"

        return {
            "name": name,
            "module": module,
            "status": status,
            "count": len(signals),
            "runtime_ms": runtime_ms,
            "signals": signals,
            "note": "" if signals else "No signals returned",
        }

    except Exception as e:
        runtime_ms = int((time.perf_counter() - start) * 1000)

        return {
            "name": name,
            "module": module,
            "status": "failed",
            "count": 0,
            "runtime_ms": runtime_ms,
            "signals": [],
            "note": str(e),
        }


# ---------------------------------------------------
# PUBLIC EXECUTION
# ---------------------------------------------------

def run_collectors(max_workers: int | None = None, mode: str = "full") -> Tuple[List[Any], Dict[str, Dict[str, Any]]]:

    force_import_collectors()

    max_workers = max_workers or DEFAULT_MAX_WORKERS

    registry = get_registry()
    collectors = discover_collectors()

    # ---------------------------------------------------
    # MODE FILTER (FIXED)
    # ---------------------------------------------------

    if mode == "fast":
        collectors = [
            c for c in collectors
            if (c.get("execution") or "fast") == "fast"
        ]

    print(
        f"[COLLECTOR REGISTRY] registered={len(registry)} "
        f"discovered={len(collectors)} mode={mode}"
    )

    # ---------------------------------------------------
    # SPLIT FAST / SLOW (ONLY FOR FULL MODE)
    # ---------------------------------------------------

    if mode == "full":

        fast_collectors = [c for c in collectors if c.get("execution") == "fast"]
        slow_collectors = [c for c in collectors if c.get("execution") != "fast"]

        execution_plan = (
            build_execution_plan(fast_collectors)
            + build_execution_plan(slow_collectors)
        )

    else:
        execution_plan = build_execution_plan(collectors)

    # ---------------------------------------------------
    # EXECUTION
    # ---------------------------------------------------

    all_results: List[Any] = []
    all_health: Dict[str, Dict[str, Any]] = {}

    for tier_block in execution_plan:

        tier = tier_block["tier"]
        batch = tier_block["collectors"]

        print(f"[COLLECTOR] executing {tier} ({len(batch)} collectors)")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:

            futures = {
                executor.submit(_execute_collector, c): c
                for c in batch
            }

            for future, collector in futures.items():

                try:
                    payload = future.result()

                except Exception as e:
                    print(f"[COLLECTOR ERROR] {collector['collector_name']} → {e}")
                    continue

                key = f"{payload['module']}:{payload['name']}"

                all_results.extend(payload.get("signals", []))
                all_health[key] = payload

    return all_results, all_health

