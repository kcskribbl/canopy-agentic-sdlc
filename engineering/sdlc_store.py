"""Transactional state, immutable content-addressed artifacts and chained events."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import sqlite3


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, workspace):
        self.root = workspace.resolve()
        home = self.root / ".canopy"
        if (home / "ledger.sqlite").exists():
            raise ValueError("This workspace holds a legacy acceptance ledger. Select a separate workspace.")
        home.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(home / "control.sqlite", isolation_level=None, timeout=15)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS objects(hash TEXT PRIMARY KEY, body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS products(project TEXT PRIMARY KEY, hash TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS trust(slot INTEGER PRIMARY KEY CHECK(slot=1), hash TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, run TEXT NOT NULL, hash TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS history ON events(run,seq);
          CREATE TRIGGER IF NOT EXISTS no_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
          CREATE TRIGGER IF NOT EXISTS no_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
          CREATE TRIGGER IF NOT EXISTS no_object_update BEFORE UPDATE ON objects BEGIN SELECT RAISE(ABORT,'immutable artifact'); END;
          CREATE TRIGGER IF NOT EXISTS no_object_delete BEFORE DELETE ON objects BEGIN SELECT RAISE(ABORT,'immutable artifact'); END;
        """)

    @contextmanager
    def tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def put(self, value):
        key = sha(value)
        self.db.execute("INSERT OR IGNORE INTO objects VALUES(?,?)", (key, encode(value)))
        return key

    def get(self, key):
        row = self.db.execute("SELECT body FROM objects WHERE hash=?", (key,)).fetchone()
        if not row or sha(value := json.loads(row[0])) != key:
            raise ValueError("Missing or damaged artifact: " + key)
        return value

    def load(self, run):
        row = self.db.execute("SELECT state FROM runs WHERE id=?", (run,)).fetchone()
        if not row:
            raise ValueError("Unknown run: " + run)
        return json.loads(row[0])

    def save(self, s):
        self.db.execute("INSERT OR REPLACE INTO runs VALUES(?,?)", (s["run"], encode(s)))

    def product(self, project):
        row = self.db.execute("SELECT hash FROM products WHERE project=?", (project,)).fetchone()
        return row[0] if row else self.put({})

    def trust(self):
        row=self.db.execute("SELECT hash FROM trust WHERE slot=1").fetchone()
        return self.get(row[0]) if row else None

    def log(self, s, stage, owner, action, **details):
        prev = self.db.execute("SELECT hash FROM events WHERE run=? ORDER BY seq DESC LIMIT 1", (s["run"],)).fetchone()
        e = dict(run=s["run"], revision=s["revision"], stage=stage, agent=owner, action=action,
                 timestamp=utc(), previous=prev[0] if prev else None, details=details)
        self.db.execute("INSERT INTO events(run,hash,body) VALUES(?,?,?)", (s["run"], sha(e), encode(e)))

    def history(self, run):
        prev = None
        result = []
        for key, body in self.db.execute("SELECT hash,body FROM events WHERE run=? ORDER BY seq", (run,)):
            e = json.loads(body)
            if sha(e) != key or e["previous"] != prev:
                raise ValueError("Invalid trace hash chain")
            prev = key
            result.append(dict(e, hash=key))
        return result
