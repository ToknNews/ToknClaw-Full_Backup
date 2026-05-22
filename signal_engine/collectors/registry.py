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
# MODULE: registry
# PURPOSE: Central collector registry with execution class support
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from typing import Callable, Dict, Any


COLLECTOR_REGISTRY: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------
# COLLECTOR REGISTRATION
# ---------------------------------------------------

def register_collector(
    name: str,
    priority: int = 100,
    tags: list | None = None,
    timeout: int = 10,
    category: str | None = None,
    execution: str = "fast",
):
    if tags is None:
        tags = []

    execution = str(execution or "fast").strip().lower()
    if execution not in {"fast", "slow"}:
        execution = "fast"

    def wrapper(func: Callable):
        if name in COLLECTOR_REGISTRY:
            raise RuntimeError(
                f"[TOKNCLAW REGISTRY] duplicate collector registration: {name}"
            )

        COLLECTOR_REGISTRY[name] = {
            "function": func,
            "name": name,
            "priority": int(priority),
            "timeout": int(timeout),
            "tags": list(tags),
            "category": category,
            "module": func.__module__,
            "execution": execution,
        }

        return func

    return wrapper

# ---------------------------------------------------
# REGISTRY ACCESS
# ---------------------------------------------------

def get_registry():
    return COLLECTOR_REGISTRY


# ---------------------------------------------------
# REGISTRY DIAGNOSTICS
# ---------------------------------------------------

def registry_stats():

    collectors = list(COLLECTOR_REGISTRY.values())

    categories = {}
    execution_types = {"fast": 0, "slow": 0}

    for c in collectors:

        cat = c.get("category") or "uncategorized"
        categories.setdefault(cat, 0)
        categories[cat] += 1

        exec_type = c.get("execution", "slow")
        execution_types[exec_type] = execution_types.get(exec_type, 0) + 1

    stats = {
        "collector_count": len(collectors),
        "collectors": [c["name"] for c in collectors],
        "categories": categories,
        "execution": execution_types,
    }

    return stats


# ---------------------------------------------------
# DEBUG HELPERS
# ---------------------------------------------------

def print_registry():

    stats = registry_stats()

    print(f"[TOKNCLAW REGISTRY] collectors={stats['collector_count']}")
    print(f"[TOKNCLAW REGISTRY] execution={stats['execution']}")

    for c in COLLECTOR_REGISTRY.values():

        print(
            f" • {c['name']} "
            f"(priority={c['priority']}, "
            f"timeout={c['timeout']}, "
            f"execution={c.get('execution')}, "
            f"category={c.get('category')})"
        )
