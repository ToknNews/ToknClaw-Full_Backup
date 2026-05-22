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
# MODULE: history_store
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================


"""
history_store.py

Persistent intelligence storage for ToknClaw.

Stores structured time-series intelligence into SQLite so the
system can analyze long-term narrative arcs, entity evolution,
conviction history, and regime transitions.

Retention target: 180 days
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List


DB_PATH = Path("/opt/toknclaw/data/history/intelligence.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

RETENTION_SECONDS = 180 * 24 * 3600


def _connect():
    return sqlite3.connect(DB_PATH)


def initialize_db():

    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        ts INTEGER,
        entity TEXT,
        signal_type TEXT,
        source TEXT,
        confidence REAL,
        raw_json TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clusters (
        ts INTEGER,
        cluster_id TEXT,
        cluster_type TEXT,
        entity TEXT,
        signal_count INTEGER,
        total_value REAL,
        raw_json TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS narratives (
        ts INTEGER,
        narrative_id TEXT,
        narrative_type TEXT,
        sector TEXT,
        confidence REAL,
        raw_json TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS entity_intelligence (
        ts INTEGER,
        entity TEXT,
        confidence REAL,
        persistence REAL,
        velocity REAL,
        raw_json TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS conviction (
        ts INTEGER,
        entity TEXT,
        conviction_score REAL,
        raw_json TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS regime (
        ts INTEGER,
        regime TEXT,
        raw_json TEXT
    )
    """)

    conn.commit()
    conn.close()


def _insert_many(table: str, rows: List[tuple]):

    if not rows:
        return

    conn = _connect()
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(rows[0]))

    cur.executemany(
        f"INSERT INTO {table} VALUES ({placeholders})",
        rows
    )

    conn.commit()
    conn.close()


def persist_snapshot(snapshot: Dict[str, Any]):

    ts = int(snapshot.get("timestamp") or time.time())

    # ---------------------
    # SIGNALS
    # ---------------------

    signal_rows = []

    for s in snapshot.get("signals", []):
        signal_rows.append((
            ts,
            s.get("entity"),
            s.get("signal_type"),
            s.get("source"),
            s.get("confidence"),
            json.dumps(s)
        ))

    _insert_many("signals", signal_rows)

    # ---------------------
    # CLUSTERS
    # ---------------------

    cluster_rows = []

    for c in snapshot.get("clusters", []):
        cluster_rows.append((
            ts,
            c.get("cluster_id"),
            c.get("cluster_type"),
            c.get("entity"),
            c.get("signal_count"),
            c.get("total_value_usd"),
            json.dumps(c)
        ))

    _insert_many("clusters", cluster_rows)

    # ---------------------
    # NARRATIVES
    # ---------------------

    narrative_rows = []

    for n in snapshot.get("narratives", []):
        narrative_rows.append((
            ts,
            n.get("narrative_id"),
            n.get("narrative_type"),
            n.get("sector"),
            n.get("confidence"),
            json.dumps(n)
        ))

    _insert_many("narratives", narrative_rows)

    # ---------------------
    # ENTITY INTELLIGENCE
    # ---------------------

    entity_rows = []

    for entity, record in snapshot.get("entity_intelligence", {}).items():
        entity_rows.append((
            ts,
            entity,
            record.get("latest_confidence"),
            record.get("max_persistence_score"),
            record.get("max_velocity_score"),
            json.dumps(record)
        ))

    _insert_many("entity_intelligence", entity_rows)

    # ---------------------
    # CONVICTION
    # ---------------------

    conviction_rows = []

    for c in snapshot.get("conviction_scores", {}).get("items", []):
        conviction_rows.append((
            ts,
            c.get("entity"),
            c.get("conviction_score"),
            json.dumps(c)
        ))

    _insert_many("conviction", conviction_rows)

    # ---------------------
    # REGIME
    # ---------------------

    regime = snapshot.get("market_regime", {}).get("name")

    if regime:
        _insert_many("regime", [
            (ts, regime, json.dumps(snapshot.get("market_regime")))
        ])

    cleanup_old_data()


def cleanup_old_data():

    cutoff = int(time.time()) - RETENTION_SECONDS

    conn = _connect()
    cur = conn.cursor()

    for table in [
        "signals",
        "clusters",
        "narratives",
        "entity_intelligence",
        "conviction",
        "regime"
    ]:
        cur.execute(f"DELETE FROM {table} WHERE ts < ?", (cutoff,))

    conn.commit()
    conn.close()
