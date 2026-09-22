"""SQLite-Datenbank – Schema und einfache Zugriffshelfer.

Alles läuft lokal in einer einzigen Datei ``data.db``. Kein Datenbankserver,
keine externe Abhängigkeit.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS hotels (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL DEFAULT '',
    url        TEXT NOT NULL DEFAULT '',
    ort        TEXT NOT NULL DEFAULT '',
    region     TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    features   TEXT NOT NULL DEFAULT '[]',
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    von        TEXT NOT NULL DEFAULT '',
    bis        TEXT NOT NULL DEFAULT '',
    personen   INTEGER NOT NULL DEFAULT 2,
    kinder     TEXT NOT NULL DEFAULT '',
    extra      TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'entwurf'
);

CREATE TABLE IF NOT EXISTS emails (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER,
    hotel_id   INTEGER,
    to_email   TEXT NOT NULL DEFAULT '',
    subject    TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'entwurf',
    sent_at    TEXT,
    error      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (request_id) REFERENCES requests(id) ON DELETE CASCADE,
    FOREIGN KEY (hotel_id)   REFERENCES hotels(id)   ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS offers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hotel_id    INTEGER,
    request_id  INTEGER,
    created_at  TEXT NOT NULL,
    price       REAL,
    currency    TEXT NOT NULL DEFAULT 'EUR',
    von         TEXT NOT NULL DEFAULT '',
    bis         TEXT NOT NULL DEFAULT '',
    naechte     INTEGER,
    personen    INTEGER,
    zimmer      TEXT NOT NULL DEFAULT '',
    verpflegung TEXT NOT NULL DEFAULT '',
    leistungen  TEXT NOT NULL DEFAULT '',
    storno      TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    source_url  TEXT NOT NULL DEFAULT '',
    raw         TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (hotel_id)   REFERENCES hotels(id)   ON DELETE SET NULL,
    FOREIGN KEY (request_id) REFERENCES requests(id) ON DELETE SET NULL
);
"""


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def query(sql: str, args: tuple = (), one: bool = False):
    conn = _connect()
    try:
        cur = conn.execute(sql, args)
        rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows
    finally:
        conn.close()


def execute(sql: str, args: tuple = ()) -> int:
    """Führt INSERT/UPDATE/DELETE aus und gibt lastrowid zurück."""
    conn = _connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ---------- Serialisierung ----------

def hotel_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["features"] = json.loads(d.get("features") or "[]")
    except json.JSONDecodeError:
        d["features"] = []
    return d


def offer_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)
