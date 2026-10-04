"""Append-only setup evidence and restart-safe lifecycle state (archive schema 3)."""

import json

from .setup_data import Candle

SCHEMA = """
CREATE TABLE IF NOT EXISTS setup_candles (
    venue TEXT NOT NULL, asset TEXT NOT NULL, open_at REAL NOT NULL,
    close_at REAL NOT NULL, received_at REAL NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY(venue,asset,open_at)
);
CREATE INDEX IF NOT EXISTS setup_candle_lookup ON setup_candles(venue,asset,close_at);
CREATE TABLE IF NOT EXISTS setup_samples (
    id INTEGER PRIMARY KEY, collected_at REAL NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS setups (
    id TEXT PRIMARY KEY REFERENCES events(id), asset TEXT NOT NULL,
    created_at REAL NOT NULL, stage TEXT NOT NULL, closed_at REAL, payload TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS setup_one_active ON setups(asset) WHERE closed_at IS NULL;
CREATE TABLE IF NOT EXISTS setup_events (
    event_id TEXT PRIMARY KEY REFERENCES events(id),
    setup_id TEXT NOT NULL REFERENCES setups(id), sequence INTEGER NOT NULL,
    UNIQUE(setup_id,sequence)
);
"""


class SetupArchive:
    def add_setup_candles(self, candles):
        revisions = set()
        for candle in candles:
            existing = self.db.execute('SELECT payload FROM setup_candles WHERE venue=? AND asset=? AND open_at=?',
                                       (candle.venue, candle.asset, candle.open_at)).fetchone()
            if existing:
                old = json.loads(existing[0])
                if any(old[key] != getattr(candle, key) for key in ('open', 'high', 'low', 'close', 'volume_base')):
                    revisions.add(candle.venue + ':' + candle.asset)
                continue
            self.db.execute('INSERT INTO setup_candles VALUES (?,?,?,?,?,?)', (
                candle.venue, candle.asset, candle.open_at, candle.close_at, candle.received_at,
                json.dumps(candle.to_dict(), allow_nan=False)))
        return revisions

    def setup_candles(self, venue, asset, asof, limit=200):
        rows = self.db.execute('''SELECT payload FROM setup_candles WHERE venue=? AND asset=?
            AND close_at<=? AND received_at<=? ORDER BY close_at DESC LIMIT ?''',
                              (venue, asset, asof, asof, limit)).fetchall()
        return [Candle(**json.loads(row[0])) for row in reversed(rows)]

    def setup_sample(self, now, payload):
        self.db.execute('INSERT INTO setup_samples(collected_at,payload) VALUES (?,?)',
                        (now, json.dumps(payload, allow_nan=False, sort_keys=True)))

    def active_setups(self):
        return [json.loads(row[0]) for row in self.db.execute(
            'SELECT payload FROM setups WHERE closed_at IS NULL ORDER BY created_at,id')]

    def save_setup(self, track):
        self.db.execute('''INSERT INTO setups VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE
            SET stage=excluded.stage,closed_at=excluded.closed_at,payload=excluded.payload''', (
                track['id'], track['spec']['asset'], track['spec']['created_at'], track['stage'],
                track.get('closed_at'), json.dumps(track, allow_nan=False, sort_keys=True)))

    def setup_receipt_routes(self, original_id, routes):
        receipts = {row[0] for row in self.db.execute('''SELECT route FROM deliveries
            WHERE event_id=? AND status='sent' AND remote_id IS NOT NULL AND remote_id!='' ''', (original_id,))}
        return [r for r in routes if r.audience == 'paid' and r.name in receipts]

    def supersede_setup(self, original_id, now):
        self.db.execute('''UPDATE deliveries SET status='expired',error='superseded_setup',updated_at=?
            WHERE status='pending' AND event_id IN
            (SELECT event_id FROM setup_events WHERE setup_id=?)''', (now, original_id))

    def withdraw_setup_deliveries(self, now):
        self.db.execute("""UPDATE deliveries SET status='expired',error='setup_publishing_disabled',updated_at=?
            WHERE status='pending' AND event_id IN (SELECT event_id FROM setup_events)""", (now,))

    def link_setup_event(self, event_id, original_id, sequence):
        self.db.execute('INSERT INTO setup_events VALUES (?,?,?)', (event_id, original_id, sequence))

    def setup_created_count(self, since):
        return self.db.execute('SELECT COUNT(*) FROM setups WHERE created_at>=?', (since,)).fetchone()[0]

    def setup_last_closed(self, asset):
        return self.db.execute('SELECT MAX(closed_at) FROM setups WHERE asset=?', (asset,)).fetchone()[0]

    def setup_status(self, limit=0):
        if self.db.execute('PRAGMA user_version').fetchone()[0] < 3:
            return {'active': 0, 'states': {}, 'health': {'status': 'not_installed'}}
        output = {'active': self.db.execute('SELECT COUNT(*) FROM setups WHERE closed_at IS NULL').fetchone()[0],
                  'states': dict(self.db.execute('SELECT stage,COUNT(*) FROM setups GROUP BY stage')),
                  'candles': self.db.execute('SELECT COUNT(*) FROM setup_candles').fetchone()[0],
                  'health': self.get_meta('setup_health') or {'status': 'not_started'}}
        if limit:
            output['recent'] = [json.loads(row[0]) for row in self.db.execute(
                'SELECT payload FROM setups ORDER BY created_at DESC LIMIT ?', (limit,))]
        return output
