"""Transactional observations, immutable event evidence, and delivery outbox."""

import hashlib
import json
from pathlib import Path
import sqlite3

from .models import Observation


class Store:
    def __init__(self, path, readonly=False):
        if readonly:
            self.db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=20)
            self.db.row_factory = sqlite3.Row
            if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
                self.db.close()
                raise ValueError("unsupported or uninitialized archive schema")
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        if self.db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
            raise ValueError("unsupported archive schema version")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS observations (
                venue TEXT NOT NULL, asset TEXT NOT NULL, instrument TEXT NOT NULL,
                observed_at REAL NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (venue, asset, observed_at)
            );
            CREATE INDEX IF NOT EXISTS observation_lookup
                ON observations(venue, asset, instrument, observed_at);
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, event_key TEXT NOT NULL, kind TEXT NOT NULL,
                audience TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                text TEXT NOT NULL, evidence TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS event_lookup ON events(event_key, created_at);
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id),
                route TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
                remote_id TEXT, error TEXT, updated_at REAL NOT NULL,
                UNIQUE(event_id, route)
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cycles (
                id INTEGER PRIMARY KEY, completed_at REAL NOT NULL, issues TEXT NOT NULL,
                observation_count INTEGER NOT NULL
            );
            PRAGMA user_version=1;
        """)

    def close(self):
        self.db.close()

    def add_observations(self, observations):
        self.db.executemany("INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?)", [
            (o.venue, o.asset, o.instrument, o.observed_at, json.dumps(o.to_dict(), allow_nan=False))
            for o in observations
        ])

    def baseline(self, current, lookback, tolerance):
        target = current.observed_at - lookback
        row = self.db.execute("""SELECT payload FROM observations
            WHERE venue=? AND asset=? AND instrument=? AND observed_at BETWEEN ? AND ?
            ORDER BY observed_at DESC LIMIT 1""", (
                current.venue, current.asset, current.instrument, target - tolerance, target
            )).fetchone()
        return Observation(**json.loads(row[0])) if row else None

    def last_event(self, key):
        row = self.db.execute("SELECT MAX(created_at) FROM events WHERE event_key=?", (key,)).fetchone()
        return row[0]

    def alert_count(self, since):
        return self.db.execute("SELECT COUNT(*) FROM events WHERE kind='alert' AND created_at>=?", (since,)).fetchone()[0]

    def get_meta(self, key):
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_meta(self, key, value):
        self.db.execute("INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value, allow_nan=False)))

    def add_event(self, event, routes):
        event_id = hashlib.sha256((event.key + ':' + str(event.created_at)).encode()).hexdigest()[:24]
        self.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)", (
            event_id, event.key, event.kind, event.audience, event.created_at, event.expires_at,
            event.text, json.dumps(event.evidence, allow_nan=False, sort_keys=True)
        ))
        for route in routes:
            self.db.execute("INSERT INTO deliveries(event_id,route,updated_at) VALUES (?,?,?)",
                            (event_id, route.name, event.created_at))
        return event_id

    def record_cycle(self, now, issues, count):
        self.db.execute("INSERT INTO cycles(completed_at,issues,observation_count) VALUES (?,?,?)",
                        (now, json.dumps(issues, sort_keys=True), count))

    def pending(self, now):
        # A crash after the HTTP call may have delivered the message. Quarantine it.
        with self.db:
            self.db.execute("UPDATE deliveries SET status='unknown',error='interrupted_send',updated_at=? WHERE status='sending'", (now,))
            self.db.execute("""UPDATE deliveries SET status='expired',error='message_expired',updated_at=?
                WHERE status='pending' AND event_id IN (SELECT id FROM events WHERE expires_at<=?)""", (now, now))
        return self.db.execute("""SELECT d.*, e.text, e.audience, e.expires_at FROM deliveries d
            JOIN events e ON d.event_id=e.id WHERE d.status='pending' AND d.next_attempt<=?
            ORDER BY d.id LIMIT 20""", (now,)).fetchall()

    def delivery_state(self, delivery_id, status, now, *, remote_id=None, error=None, delay=0):
        with self.db:
            self.db.execute("""UPDATE deliveries SET status=?,updated_at=?,remote_id=?,error=?,
                next_attempt=?,attempts=attempts+? WHERE id=?""", (
                    status, now, remote_id, error, now + delay,
                    int(status == 'sending'), delivery_id
                ))

    def resolve_delivery(self, delivery_id, action, remote_id, now):
        if action not in {'sent', 'discarded'} or (action == 'sent' and not remote_id):
            raise ValueError("resolution requires sent with remote id, or discarded")
        with self.db:
            row = self.db.execute("SELECT status FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
            if not row or row[0] != 'unknown':
                raise ValueError("only uncertain deliveries can be resolved")
            self.db.execute("UPDATE deliveries SET status=?,remote_id=?,error='operator_resolved',updated_at=? WHERE id=?",
                            (action, remote_id, now, delivery_id))

    def status(self, now):
        cycle = self.db.execute("SELECT * FROM cycles ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "last_cycle_at": cycle['completed_at'] if cycle else None,
            "cycle_age_seconds": round(now - cycle['completed_at'], 1) if cycle else None,
            "source_issues": json.loads(cycle['issues']) if cycle else {"system": "not_started"},
            "observations": self.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
            "events": self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "deliveries": {row[0]: row[1] for row in self.db.execute("SELECT status,COUNT(*) FROM deliveries GROUP BY status")},
            "unresolved": [dict(r) for r in self.db.execute("SELECT id,route,error FROM deliveries WHERE status IN ('unknown','failed') ORDER BY id LIMIT 25")],
        }

    def export_events(self, limit=100):
        rows = self.db.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "evidence": json.loads(r['evidence'])} for r in rows]
