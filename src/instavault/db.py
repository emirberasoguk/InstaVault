import os
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "instavault" / "vault.db"

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_sha256 TEXT UNIQUE NOT NULL,
    export_dir TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    account_username TEXT,
    date_range_start TEXT,
    date_range_end TEXT,
    generated_at TEXT,
    record_count INTEGER DEFAULT 0,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS videos_watched (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    caption TEXT,
    hashtags TEXT,
    owner_username TEXT,
    owner_name TEXT,
    owner_url TEXT,
    watched_at TEXT NOT NULL,
    export_id INTEGER REFERENCES exports(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(url, watched_at) ON CONFLICT IGNORE
);

CREATE TABLE IF NOT EXISTS posts_viewed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    caption TEXT,
    hashtags TEXT,
    owner_username TEXT,
    owner_name TEXT,
    owner_url TEXT,
    viewed_at TEXT NOT NULL,
    export_id INTEGER REFERENCES exports(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(url, viewed_at) ON CONFLICT IGNORE
);

CREATE TABLE IF NOT EXISTS saved_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    caption TEXT,
    hashtags TEXT,
    owner_username TEXT,
    owner_name TEXT,
    owner_url TEXT,
    saved_at TEXT NOT NULL,
    export_id INTEGER REFERENCES exports(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(url, saved_at) ON CONFLICT IGNORE
);

CREATE TABLE IF NOT EXISTS social_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    profile_url TEXT,
    connection_type TEXT NOT NULL, -- 'follower', 'following', 'pending_request'
    connected_at TEXT NOT NULL,
    export_id INTEGER REFERENCES exports(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(username, connection_type, connected_at) ON CONFLICT IGNORE
);

CREATE INDEX IF NOT EXISTS idx_videos_owner ON videos_watched(owner_username);
CREATE INDEX IF NOT EXISTS idx_videos_watched_at ON videos_watched(watched_at);
CREATE INDEX IF NOT EXISTS idx_saved_owner ON saved_posts(owner_username);
CREATE INDEX IF NOT EXISTS idx_social_user_type ON social_connections(username, connection_type);
"""


def get_db_path(override_path: Optional[str | Path] = None) -> Path:
    if override_path:
        path = Path(override_path)
    else:
        path = DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db(db_path: Optional[str | Path] = None) -> sqlite3.Connection:
    target_path = get_db_path(db_path)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.executescript(SCHEMA_SQL)
    return conn


def is_file_ingested(conn: sqlite3.Connection, sha256_hash: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM exports WHERE file_sha256 = ?", (sha256_hash,))
    return cur.fetchone() is not None
