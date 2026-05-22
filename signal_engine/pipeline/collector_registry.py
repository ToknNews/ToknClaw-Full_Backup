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
# MODULE: collector_registry
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import json
import importlib
from pathlib import Path
from typing import Dict, List, Callable


MANIFEST_PATH = Path("/opt/toknclaw/config/collector_manifest.json")


def _load_manifest():

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("collector_manifest.json missing")

    return json.loads(MANIFEST_PATH.read_text())


def load_collectors():

    manifest = _load_manifest()

    collectors = []

    for item in manifest.get("collectors", []):

        if not item.get("enabled"):
            continue

        module_name = item["module"]
        func_name = item["function"]

        module = importlib.import_module(module_name)

        func = getattr(module, func_name)

        collectors.append({
            "id": item["id"],
            "priority": item.get("priority", 10),
            "timeout": item.get("timeout_sec", 20),
            "tags": item.get("tags", []),
            "function": func,
            "module": module_name
        })

    collectors.sort(key=lambda x: x["priority"])

    return collectors
