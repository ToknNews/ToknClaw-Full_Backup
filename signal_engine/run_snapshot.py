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
# MODULE: run_snapshot
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

Purpose
-------
Executes the ToknClaw intelligence pipeline and persists snapshots.

Responsibilities
----------------
• load environment variables
• execute snapshot pipeline
• store versioned snapshots
• update latest snapshot
• emit runtime diagnostics
• prune old snapshots
• support agent orchestration

Primary Output
--------------
/opt/toknclaw/data/snapshots/latest_snapshot.json

Author: TOKN Systems
"""

import json
import os
import time
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from signal_engine.pipeline.snapshot import generate_snapshot

# ---------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------

ENV_PATH = "/opt/toknclaw/signal_engine/.env"
load_dotenv(ENV_PATH)


# ---------------------------------------------------
# STORAGE PATHS
# ---------------------------------------------------

SNAPSHOT_DIR = Path("/opt/toknclaw/data/snapshots")
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

LATEST_PATH = SNAPSHOT_DIR / "latest_snapshot.json"

RETENTION_LIMIT = int(os.getenv("TOKN_SNAPSHOT_RETENTION", 500))


# ---------------------------------------------------
# SNAPSHOT STORAGE
# ---------------------------------------------------

def save_snapshot(snapshot):

    def serialize(obj):

        # convert Signal objects
        if hasattr(obj, "__dict__"):
            data = dict(obj.__dict__)

            ts = data.get("timestamp")
            if hasattr(ts, "isoformat"):
                data["timestamp"] = ts.isoformat()

            return data

        # convert datetime objects
        if hasattr(obj, "isoformat"):
            return obj.isoformat()

        # fallback
        return str(obj)

    ts = datetime.now(timezone.utc).isoformat()

    snapshot["timestamp"] = ts

    filename = ts.replace(":", "-")
    snapshot_path = SNAPSHOT_DIR / f"snapshot_{filename}.json"

    # write full snapshot
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=serialize)

    # atomic latest snapshot write
    tmp_path = SNAPSHOT_DIR / "latest_snapshot.tmp"

    with open(tmp_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=serialize)

    tmp_path.replace(LATEST_PATH)

    return snapshot_path

# ---------------------------------------------------
# SNAPSHOT RETENTION
# ---------------------------------------------------

def prune_snapshots():

    files = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))

    if len(files) <= RETENTION_LIMIT:
        return

    excess = len(files) - RETENTION_LIMIT

    for f in files[:excess]:
        try:
            f.unlink()
        except Exception:
            pass


# ---------------------------------------------------
# DIAGNOSTICS
# ---------------------------------------------------

def print_runtime_stats(snapshot, runtime):

    signals = len(snapshot.get("signals", []))
    clusters = len(snapshot.get("clusters", []))
    narratives = len(snapshot.get("narratives", []))
    strategies = len(snapshot.get("optimized_strategies", []))

    print(f"[TOKNCLAW] runtime: {runtime:.2f}s")
    print(f"[TOKNCLAW] signals: {signals}")
    print(f"[TOKNCLAW] clusters: {clusters}")
    print(f"[TOKNCLAW] narratives: {narratives}")
    print(f"[TOKNCLAW] strategies: {strategies}")

def run_full_snapshot():
    from signal_engine.pipeline.snapshot import generate_snapshot
    return generate_snapshot(mode="full")

# ---------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------

def main():

    start = time.time()

    try:

        snapshot = generate_snapshot()

    except Exception as e:

        print("[TOKNCLAW] snapshot generation failed")
        print(e)

        raise

    runtime = time.time() - start

    path = save_snapshot(snapshot)

    prune_snapshots()

    print_runtime_stats(snapshot, runtime)

    print(f"[SNAPSHOT] saved → {path}")
    print(f"[SNAPSHOT] latest → {LATEST_PATH}")


# ---------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------

if __name__ == "__main__":
    main()
