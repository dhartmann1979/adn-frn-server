"""
One SQLite database (WAL mode) holds everything – the FRN server and the dashboard:

* settings, users, sessions, audit           – admin area and server settings
* rooms, room_access, frn_lists, frn_accounts – rooms, access/admin/block/mute lists,
                                                FRN accounts (own password list)
* talks       – every transmission (room, station, start, duration)
* visits      – logins/logouts of stations (from the server log and the monitor)
* samples     – number of stations per room, once a minute (for "online" charts)
* chat        – text messages in the rooms
* news        – news of the portal page (only admins write and publish)
* talk_daily  – roll-up per day/room/station, kept up to date on every talk;
* online_daily – highest number of stations online per day (for long ranges)
                long ranges (90 days, 1 year) are read from here instead of
                summing every single talk
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, List

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',      -- superadmin | admin | user
    display_name  TEXT NOT NULL DEFAULT '',
    disabled      INTEGER NOT NULL DEFAULT 0,
    default_pw    INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    last_login    REAL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    ip         TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT ''
);
DROP TABLE IF EXISTS api_tokens;               -- until 2.10: old API tokens, no longer used
CREATE TABLE IF NOT EXISTS audit (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL NOT NULL,
    action   TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    detail   TEXT NOT NULL DEFAULT '',
    ip       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS talks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    end_ts    REAL,
    net       TEXT NOT NULL,
    cid       TEXT NOT NULL DEFAULT '',
    callsign  TEXT NOT NULL DEFAULT '',
    name      TEXT NOT NULL DEFAULT '',
    band      TEXT NOT NULL DEFAULT '',
    country   TEXT NOT NULL DEFAULT '',
    city      TEXT NOT NULL DEFAULT '',
    duration  REAL NOT NULL DEFAULT 0,
    seq       INTEGER
);
CREATE INDEX IF NOT EXISTS talks_ts ON talks(ts);
CREATE INDEX IF NOT EXISTS talks_call ON talks(callsign, ts);
CREATE TABLE IF NOT EXISTS talk_daily (
    day       TEXT NOT NULL,
    net       TEXT NOT NULL,
    callsign  TEXT NOT NULL,
    talks     INTEGER NOT NULL DEFAULT 0,
    seconds   REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (day, net, callsign)
);
CREATE TABLE IF NOT EXISTS visits (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    login_ts  REAL NOT NULL,
    logout_ts REAL,
    net       TEXT NOT NULL,
    cid       TEXT NOT NULL DEFAULT '',
    callsign  TEXT NOT NULL DEFAULT '',
    name      TEXT NOT NULL DEFAULT '',
    email     TEXT NOT NULL DEFAULT '',
    peer      TEXT NOT NULL DEFAULT '',
    band      TEXT NOT NULL DEFAULT '',
    country   TEXT NOT NULL DEFAULT '',
    city      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS visits_login ON visits(login_ts);
CREATE INDEX IF NOT EXISTS visits_open ON visits(logout_ts);
CREATE TABLE IF NOT EXISTS samples (
    ts      REAL NOT NULL,
    net     TEXT NOT NULL,
    clients INTEGER NOT NULL,
    PRIMARY KEY (ts, net)
);
CREATE TABLE IF NOT EXISTS online_daily (
    day     TEXT PRIMARY KEY,
    peak    INTEGER NOT NULL,
    peak_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chat (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL NOT NULL,
    net      TEXT NOT NULL,
    cid      TEXT NOT NULL DEFAULT '',
    callsign TEXT NOT NULL DEFAULT '',
    text     TEXT NOT NULL,
    private  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS chat_ts ON chat(ts);
CREATE TABLE IF NOT EXISTS rooms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    position      INTEGER NOT NULL DEFAULT 0,
    enabled       INTEGER NOT NULL DEFAULT 1,
    hidden        INTEGER NOT NULL DEFAULT 0,
    owners        TEXT NOT NULL DEFAULT '',     -- comma separated e-mails
    notice        TEXT NOT NULL DEFAULT '',     -- info message (HTML)
    show_info     TEXT NOT NULL DEFAULT 'acl',  -- acl | always
    tot           INTEGER NOT NULL DEFAULT 180, -- max. transmission (s), 0 = unlimited
    speechpause   INTEGER NOT NULL DEFAULT 0,   -- ms
    speechpause_msg TEXT NOT NULL DEFAULT '',
    parrot        INTEGER NOT NULL DEFAULT 0,
    parrot_startstop INTEGER NOT NULL DEFAULT 1,
    unmute_min    INTEGER NOT NULL DEFAULT 0,   -- mutes end after N minutes, 0 = never
    access_on     INTEGER NOT NULL DEFAULT 0,   -- ENA: only the access list gets in
    txright_on    INTEGER NOT NULL DEFAULT 0,   -- TXR: only entries with tx right may talk
    acl_cl        TEXT NOT NULL DEFAULT '',     -- crosslinks allowed: '' = all, 'none' or e-mails
    acl_gw        TEXT NOT NULL DEFAULT '',     -- gateways allowed
    acl_info      TEXT NOT NULL DEFAULT '',
    bl_regexp     TEXT NOT NULL DEFAULT '',
    bl_info       TEXT NOT NULL DEFAULT '',
    max_clients   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS room_access (
    room_id  INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    email    TEXT NOT NULL COLLATE NOCASE,
    can_tx   INTEGER NOT NULL DEFAULT 1,
    note     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (room_id, email)
);
CREATE TABLE IF NOT EXISTS frn_lists (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    kind     TEXT NOT NULL CHECK (kind IN ('admin','block','mute')),
    room_id  INTEGER REFERENCES rooms(id) ON DELETE CASCADE,   -- NULL = whole server
    email    TEXT NOT NULL COLLATE NOCASE,
    callsign TEXT NOT NULL DEFAULT '',
    info     TEXT NOT NULL DEFAULT '',      -- <ON>/<NN>/... of the client, JSON
    added_by TEXT NOT NULL DEFAULT '',
    ts       REAL NOT NULL,
    until_ts REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS frn_lists_u ON frn_lists(kind, IFNULL(room_id, 0), email);
CREATE TABLE IF NOT EXISTS frn_accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    callsign      TEXT NOT NULL DEFAULT '',
    name          TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    disabled      INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    last_login    REAL
);
CREATE TABLE IF NOT EXISTS news (               -- portal page: news written by admins (portal.py)
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    teaser       TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL DEFAULT '',
    category     TEXT NOT NULL DEFAULT 'info',
    icon         TEXT NOT NULL DEFAULT '',
    author       TEXT NOT NULL DEFAULT '',
    author_name  TEXT NOT NULL DEFAULT '',
    published    INTEGER NOT NULL DEFAULT 0,
    pinned       INTEGER NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    published_at REAL,
    updated_by   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS news_pub ON news(published, pinned, published_at);
CREATE TABLE IF NOT EXISTS portal_widgets (     -- portal page: widgets at the side (widgets.py), cache of the live data of other N8 systems
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                         -- frn_today | frn_rooms | frn_connect | hblink4 | crosslink | hotspot | gateway
    title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',               -- dashboard address of the other system (asked over n8feed.py)
    key TEXT NOT NULL DEFAULT '',               -- sync key of that system
    link TEXT NOT NULL DEFAULT '',              -- where a click on the widget leads (empty = url)
    enabled INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0,
    show_lh INTEGER NOT NULL DEFAULT 1,         -- show "last heard"
    lh_count INTEGER NOT NULL DEFAULT 5,
    data TEXT NOT NULL DEFAULT '',              -- last summary (JSON), cached
    fetched_at REAL, ok_at REAL, error TEXT NOT NULL DEFAULT '',
    created_at REAL
);
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS link_icons (
    url_hash    TEXT PRIMARY KEY,
    origin      TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    data        BLOB,
    fetched_at  REAL NOT NULL,
    error       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS client_logos (      -- own images for the client software avatars (clientsw.py)
    key          TEXT PRIMARY KEY,
    content_type TEXT NOT NULL,
    data         BLOB NOT NULL,
    updated_at   REAL NOT NULL,
    updated_by   TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS stations (
    callsign  TEXT PRIMARY KEY,
    cid       TEXT NOT NULL DEFAULT '',
    name      TEXT NOT NULL DEFAULT '',
    band      TEXT NOT NULL DEFAULT '',
    country   TEXT NOT NULL DEFAULT '',
    city      TEXT NOT NULL DEFAULT '',
    descr     TEXT NOT NULL DEFAULT '',
    client    INTEGER NOT NULL DEFAULT 0,
    first_ts  REAL NOT NULL,
    last_ts   REAL NOT NULL,
    last_net  TEXT NOT NULL DEFAULT ''
);
"""

# columns added after the first release
MIGRATIONS = [
    ("rooms", "idx", "INTEGER"),                                 # netNN of server.properties, 0 = test/parrot room
    ("rooms", "tg_params", "TEXT NOT NULL DEFAULT ''"),          # netNN_tgbot_params
    ("frn_accounts", "password", "TEXT NOT NULL DEFAULT ''"),    # FRNPasswd.xml needs the password itself
    ("users", "mail_hash", "TEXT NOT NULL DEFAULT ''"),
    ("news", "image", "TEXT NOT NULL DEFAULT ''"),               # 2.28: topic image as data URL (JPEG/PNG/WebP, made small in the browser)
    ("news", "image_alt", "TEXT NOT NULL DEFAULT ''"),           # 2.25: SHA512-CRYPT of the password for the mailbox (mailpw.py)
]


class DB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA temp_store = MEMORY")
        self.conn.execute("PRAGMA cache_size = -8000")
        self.conn.executescript(SCHEMA)
        for table, col, decl in MIGRATIONS:
            cols = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    def q(self, sql: str, args: Iterable[Any] = ()) -> List[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, tuple(args)).fetchall()

    def x(self, sql: str, args: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, tuple(args))

    def many(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.executemany(sql, rows)
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def kv_get(self, key: str, default: str = "") -> str:
        rows = self.q("SELECT value FROM kv WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def kv_set(self, key: str, value: str) -> None:
        self.x("INSERT INTO kv (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def tx(self, statements: Iterable[tuple]) -> None:
        """Several statements in one transaction: [(sql, args), …]."""
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                for sql, args in statements:
                    self.conn.execute(sql, tuple(args))
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
