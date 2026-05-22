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
# MODULE: signal_outcome_labeler
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
Signal Outcome Labeler

Purpose
-------
Tracks and labels the lifecycle of high-value strategy and narrative signals.

This module is the bridge between:
• signal generation
• strategy evaluation
• future backtesting
• OpenClaw agent tuning

It is intentionally light on RPC usage and reads primarily from:
• latest snapshot
• stored outcomes file

Current Version
---------------
This version is production-ready for lifecycle tracking and outcome state
management, but it does NOT fabricate price returns.

It records:
• tracked signals
• observation timestamps
• maturity windows
• pending / matured / skipped state
• future-ready schema for price-based labels

Future versions can plug in:
• token price snapshot history
• forward return calculations
• MFE / MAE
• pnl labeling
• win-rate analytics

Primary Inputs
--------------
/opt/toknclaw/data/snapshots/latest_snapshot.json

Primary Output
--------------
/opt/toknclaw/data/signal_outcomes.json

Agent Readiness
---------------
OpenClaw agents should tune:
• /opt/toknclaw/config/signal_outcome_labeler.json

Author: TOKN Systems
"""

from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_config import load_config


# ---------------------------------------------------
# PATHS
# ---------------------------------------------------

CONFIG_FILE = "signal_outcome_labeler.json"

SNAPSHOT_PATH = Path("/opt/toknclaw/data/snapshots/latest_snapshot.json")
PRICE_PATH = Path("/opt/toknclaw/data/token_price_history.json")
OUTCOMES_PATH = Path("/opt/toknclaw/data/signal_outcomes.json")
TMP_PATH = Path("/opt/toknclaw/data/signal_outcomes.tmp")


# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

DEFAULT_CONFIG = {
    "enabled": True,
    "tracked_signal_types": [
        "solana_strategy_entry_dip_buy",
        "solana_strategy_watch_dip_buy",
        "solana_memecoin_trending",
        "solana_memecoin_of_the_day",
        "solana_memecoin_narrative_candidate",
    ],
    "maturity_windows_minutes": [5, 15, 60, 240, 1440],
    "baseline_tolerance_minutes": 10,
    "forward_tolerance_minutes": 20,
    "win_threshold_pct": 5,
    "loss_threshold_pct": -5,
    "debug": True,
}


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def now():
    return datetime.now(UTC)


def now_iso():
    return now().isoformat()


def parse_dt(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(UTC)
    except:
        return None


def log(cfg, msg):
    if cfg.get("debug"):
        print("[OUTCOME]", msg)


def load_json(path, default):
    try:
        return json.load(open(path))
    except:
        return default


def save_json(path, tmp, data):
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    Path(tmp).replace(path)


# ---------------------------------------------------
# PRICE LOGIC
# ---------------------------------------------------

def get_price_points(entity, price_data):
    tokens = price_data.get("tokens", {})
    rows = tokens.get(entity, [])
    out = []

    for r in rows:
        ts = parse_dt(r.get("timestamp"))
        price = r.get("price_usd")
        if ts and price:
            out.append({"ts": ts, "price": float(price)})

    return sorted(out, key=lambda x: x["ts"])


def find_nearest(points, target, tol_min):
    best = None
    tol = timedelta(minutes=tol_min)

    for p in points:
        diff = abs(p["ts"] - target)
        if diff > tol:
            continue
        if not best or diff < abs(best["ts"] - target):
            best = p

    return best


def find_forward(points, target, tol_min):
    best = None
    tol = timedelta(minutes=tol_min)

    for p in points:
        if p["ts"] < target:
            continue
        diff = p["ts"] - target
        if diff > tol:
            continue
        if not best or diff < (best["ts"] - target):
            best = p

    return best


# ---------------------------------------------------
# CORE LOGIC
# ---------------------------------------------------

def extract_signals(snapshot, cfg):
    types = set(cfg["tracked_signal_types"])
    return [s for s in snapshot.get("signals", []) if isinstance(s, dict) and s.get("signal_type") in types]


def record_id(s):
    raw = f"{s.get('signal_type')}|{s.get('entity')}|{s.get('timestamp')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def classify(ret, cfg):
    if ret is None:
        return "unpriced"
    if ret >= cfg["win_threshold_pct"]:
        return "win"
    if ret <= cfg["loss_threshold_pct"]:
        return "loss"
    return "flat"


# ---------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------

def run():
    cfg = load_config(CONFIG_FILE) or DEFAULT_CONFIG

    snapshot = load_json(SNAPSHOT_PATH, {})
    price_data = load_json(PRICE_PATH, {"tokens": {}})
    store = load_json(OUTCOMES_PATH, {"records": {}, "summary": {}})

    records = store.setdefault("records", {})

    signals = extract_signals(snapshot, cfg)

    log(cfg, f"signals={len(signals)}")

    for s in signals:
        rid = record_id(s)

        if rid not in records:
            records[rid] = {
                "entity": s.get("entity"),
                "signal_type": s.get("signal_type"),
                "timestamp": s.get("timestamp"),
                "windows": {},
            }

        rec = records[rid]

        ts = parse_dt(rec["timestamp"])
        if not ts:
            continue

        prices = get_price_points(rec["entity"], price_data)

        base = find_nearest(prices, ts, cfg["baseline_tolerance_minutes"])

        for w in cfg["maturity_windows_minutes"]:
            tgt = ts + timedelta(minutes=w)

            fwd = find_forward(prices, tgt, cfg["forward_tolerance_minutes"])

            ret = None
            if base and fwd:
                ret = ((fwd["price"] - base["price"]) / base["price"]) * 100

            rec["windows"][str(w)] = {
                "baseline": base,
                "forward": fwd,
                "return_pct": ret,
                "label": classify(ret, cfg),
            }

    save_json(OUTCOMES_PATH, TMP_PATH, store)

    log(cfg, f"records={len(records)}")


if __name__ == "__main__":
    run()
