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
# MODULE: entity_discovery_engine
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Any, List


ASSET_DIR = Path("/opt/toknclaw/data/assets")

REGISTRY_FILE = ASSET_DIR / "asset_registry.json"
DISCOVERY_FILE = ASSET_DIR / "discovered_entities.json"


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _safe_list(v):
    return v if isinstance(v, list) else []


def _load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_json(path: Path, obj: Dict[str, Any]):
    path.write_text(json.dumps(obj, indent=2))


# -------------------------------------------------------
# Load registries
# -------------------------------------------------------

def _load_registry_entities() -> set:

    data = _load_json(REGISTRY_FILE)

    entities = set()

    for section in ["tokens", "protocols", "chains"]:
        block = _safe_dict(data.get(section))
        entities.update(block.keys())

    return {e.upper() for e in entities}


def _load_discovered_entities():

    data = _load_json(DISCOVERY_FILE)

    if "entities" not in data:
        data = {
            "entities": {},
            "meta": {
                "created_at": int(time.time()),
                "updated_at": int(time.time())
            }
        }

    return data


# -------------------------------------------------------
# Discovery
# -------------------------------------------------------

def _extract_entities_from_clusters(snapshot: Dict[str, Any]) -> List[str]:

    clusters = _safe_list(snapshot.get("clusters"))

    entities = []

    for c in clusters:
        entity = c.get("entity")

        if entity and isinstance(entity, str):
            entities.append(entity.upper())

    return list(set(entities))


def run_entity_discovery(snapshot: Dict[str, Any]) -> Dict[str, Any]:

    snapshot = _safe_dict(snapshot)

    discovered_store = _load_discovered_entities()

    registry_entities = _load_registry_entities()

    existing_discovered = set(
        k.upper() for k in discovered_store["entities"].keys()
    )

    entities = _extract_entities_from_clusters(snapshot)

    new_entities = []

    for e in entities:

        if e in registry_entities:
            continue

        if e in existing_discovered:
            continue

        discovered_store["entities"][e] = {
            "entity": e,
            "first_seen": int(time.time()),
            "last_seen": int(time.time()),
            "sources": [],
            "notes": [],
            "status": "unclassified"
        }

        new_entities.append(e)

    discovered_store["meta"]["updated_at"] = int(time.time())

    _save_json(DISCOVERY_FILE, discovered_store)

    return {
        "new_entities": new_entities,
        "discovered_total": len(discovered_store["entities"])
    }
