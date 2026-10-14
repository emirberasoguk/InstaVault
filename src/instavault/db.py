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

CREATE TABLE IF NOT EXISTS advertisers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    advertiser_name TEXT NOT NULL,
    has_data_sharing BOOLEAN DEFAULT 0,
    export_id INTEGER REFERENCES exports(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(advertiser_name, export_id) ON CONFLICT IGNORE
);

CREATE TABLE IF NOT EXISTS off_meta_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    export_id INTEGER REFERENCES exports(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_name, timestamp) ON CONFLICT IGNORE
);

CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_query TEXT NOT NULL,
    searched_at TEXT NOT NULL,
    export_id INTEGER REFERENCES exports(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(search_query, searched_at) ON CONFLICT IGNORE
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_type TEXT NOT NULL,
    target_url TEXT,
    target_username TEXT,
    timestamp TEXT NOT NULL,
    export_id INTEGER REFERENCES exports(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(interaction_type, target_url, timestamp) ON CONFLICT IGNORE
);

CREATE TABLE IF NOT EXISTS deleted_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_type TEXT NOT NULL,
    caption TEXT,
    deleted_at TEXT NOT NULL,
    export_id INTEGER REFERENCES exports(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(content_type, deleted_at) ON CONFLICT IGNORE
);

CREATE INDEX IF NOT EXISTS idx_videos_owner ON videos_watched(owner_username);
CREATE INDEX IF NOT EXISTS idx_videos_watched_at ON videos_watched(watched_at);
CREATE INDEX IF NOT EXISTS idx_saved_owner ON saved_posts(owner_username);
CREATE INDEX IF NOT EXISTS idx_social_user_type ON social_connections(username, connection_type);
CREATE INDEX IF NOT EXISTS idx_advertisers_name ON advertisers(advertiser_name);
CREATE INDEX IF NOT EXISTS idx_off_meta_company ON off_meta_activity(company_name);
CREATE INDEX IF NOT EXISTS idx_searches_query ON searches(search_query);
CREATE INDEX IF NOT EXISTS idx_interactions_username ON interactions(target_username);
CREATE INDEX IF NOT EXISTS idx_interactions_type ON interactions(interaction_type);
CREATE INDEX IF NOT EXISTS idx_deleted_content_type ON deleted_content(content_type);
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
