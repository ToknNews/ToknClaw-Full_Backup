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
# MODULE: narrative_storage
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict


NARRATIVE_DIR = Path("/opt/toknclaw/data/narratives")
ACTIVE_PATH = NARRATIVE_DIR / "narrative_history.json"
ARCHIVE_PATH = NARRATIVE_DIR / "narrative_archive.json"
BACKUP_PATH = NARRATIVE_DIR / "narrative_history.bak.json"

ARCHIVE_RETENTION_DAYS = 180
ARCHIVE_RETENTION_SEC = ARCHIVE_RETENTION_DAYS * 24 * 60 * 60


def _now_ts() -> int:
    return int(time.time())


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _default_store() -> Dict[str, Any]:
    now = _now_ts()
    return {
        "meta": {
            "created_at": now,
            "updated_at": now,
            "version": 1,
        },
        "narratives": {},
    }


def _ensure_dir() -> None:
    NARRATIVE_DIR.mkdir(parents=True, exist_ok=True)


def _safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return _default_store()

    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return _default_store()

        if "narratives" not in data or not isinstance(data["narratives"], dict):
            data["narratives"] = {}

        if "meta" not in data or not isinstance(data["meta"], dict):
            data["meta"] = {
                "created_at": _now_ts(),
                "updated_at": _now_ts(),
                "version": 1,
            }

        return data

    except Exception:
        return _default_store()


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_dir()

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp_path, path)


def load_active_history() -> Dict[str, Any]:
    _ensure_dir()
    return _safe_read_json(ACTIVE_PATH)


def load_archive_history() -> Dict[str, Any]:
    _ensure_dir()
    return _safe_read_json(ARCHIVE_PATH)


def save_active_history(store: Dict[str, Any]) -> None:
    _ensure_dir()

    store = _safe_dict(store)
    store.setdefault("meta", {})
    store.setdefault("narratives", {})
    store["meta"]["updated_at"] = _now_ts()

    if ACTIVE_PATH.exists():
        try:
            shutil.copy2(ACTIVE_PATH, BACKUP_PATH)
        except Exception:
            pass

    _atomic_write_json(ACTIVE_PATH, store)


def save_archive_history(store: Dict[str, Any]) -> None:
    _ensure_dir()

    store = _safe_dict(store)
    store.setdefault("meta", {})
    store.setdefault("narratives", {})
    store["meta"]["updated_at"] = _now_ts()

    _atomic_write_json(ARCHIVE_PATH, store)


def prune_archive(store: Dict[str, Any], now_ts: int | None = None) -> Dict[str, Any]:
    store = _safe_dict(store)
    store.setdefault("meta", {})
    store.setdefault("narratives", {})

    now_ts = now_ts or _now_ts()
    cutoff = now_ts - ARCHIVE_RETENTION_SEC

    pruned: Dict[str, Any] = {}

    for key, item in store["narratives"].items():
        if not isinstance(item, dict):
            continue

        last_seen = int(item.get("last_seen") or 0)

        if last_seen >= cutoff:
            pruned[key] = item

    store["narratives"] = pruned
    store["meta"]["updated_at"] = now_ts
    store["meta"]["archive_retention_days"] = ARCHIVE_RETENTION_DAYS

    return store


def archive_expired_narratives(
    active_store: Dict[str, Any],
    archive_store: Dict[str, Any],
    expired_keys: list[str],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    active_store = _safe_dict(active_store)
    archive_store = _safe_dict(archive_store)

    active_store.setdefault("meta", {})
    active_store.setdefault("narratives", {})

    archive_store.setdefault("meta", {})
    archive_store.setdefault("narratives", {})

    now = _now_ts()

    for key in expired_keys:
        item = active_store["narratives"].get(key)
        if not isinstance(item, dict):
            continue

        archive_store["narratives"][key] = item
        del active_store["narratives"][key]

    active_store["meta"]["updated_at"] = now
    archive_store["meta"]["updated_at"] = now

    return active_store, archive_store
