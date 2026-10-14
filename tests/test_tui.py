import sqlite3
from pathlib import Path
import pytest
from rich.layout import Layout
from rich.panel import Panel

from instavault.db import SCHEMA_SQL, init_db
from instavault.tui import (
    build_dashboard,
    build_header_panel,
    build_metrics_panel,
    build_top_creators_and_interests_panel,
    build_unfollowers_panel,
    extract_top_interests,
    load_tui_data,
    run_tui,
)


@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


@pytest.fixture
def populated_db(memory_db):
    conn = memory_db
    cur = conn.cursor()
    # Add export
    cur.execute(
        """
        INSERT INTO exports (file_sha256, export_dir, rel_path, file_type, date_range_start, date_range_end, record_count)
        VALUES ('hash1', 'dir', 'file.html', 'videos_watched', '2026-08-01T00:00Z', '2026-08-31T00:00Z', 10)
        """
    )
    # Add videos
    cur.execute(
        """
        INSERT INTO videos_watched (url, caption, hashtags, owner_username, owner_name, watched_at)
        VALUES ('url1', 'Awesome video', 'python,linux,reklam', 'coder1', 'Alice', '2026-08-10 12:00:00')
        """
    )
    cur.execute(
        """
        INSERT INTO videos_watched (url, caption, hashtags, owner_username, owner_name, watched_at)
        VALUES ('url2', 'Another video', 'python,opensource', 'coder1', 'Alice', '2026-08-11 12:00:00')
        """
    )
    # Add saved
    cur.execute(
        """
        INSERT INTO saved_posts (url, caption, saved_at)
        VALUES ('url3', 'Saved post', '2026-08-12 12:00:00')
        """
    )
    # Add social connections
    cur.execute(
        """
        INSERT INTO social_connections (username, profile_url, connection_type, connected_at)
        VALUES ('alice', 'http://inst/alice', 'follower', '2026-08-01')
        """
    )
    cur.execute(
        """
        INSERT INTO social_connections (username, profile_url, connection_type, connected_at)
        VALUES ('alice', 'http://inst/alice', 'following', '2026-08-01')
        """
    )
    cur.execute(
        """
        INSERT INTO social_connections (username, profile_url, connection_type, connected_at)
        VALUES ('bob', 'http://inst/bob', 'following', '2026-08-01')
        """
    )
    conn.commit()
    return conn


def test_load_tui_data_empty(memory_db):
    data = load_tui_data(memory_db)
    assert data["export_count"] == 0
    assert data["video_count"] == 0
    assert data["post_count"] == 0
    assert data["total_consumption"] == 0
    assert data["saved_count"] == 0
    assert data["follower_count"] == 0
    assert data["following_count"] == 0
    assert data["ratio"] == 0.0
    assert data["top_creators"] == []
    assert data["top_interests"] == []
    assert data["unfollowers"] == []


def test_load_tui_data_populated(populated_db):
    data = load_tui_data(populated_db)
    assert data["export_count"] == 1
    assert data["video_count"] == 2
    assert data["saved_count"] == 1
    assert data["total_consumption"] == 2
    assert data["follower_count"] == 1
    assert data["following_count"] == 2
    assert data["ratio"] == 0.5
    assert len(data["top_creators"]) == 1
    assert data["top_creators"][0][0] == "coder1"
    assert data["unfollowers_count"] == 1
    assert data["unfollowers"][0][0] == "bob"


def test_extract_top_interests(populated_db):
    tags = extract_top_interests(populated_db, limit=5)
    tag_names = [t[0] for t in tags]
    assert "python" in tag_names
    assert "reklam" not in tag_names  # stopword filtered


def test_build_dashboard_structure(populated_db):
    layout = build_dashboard(populated_db)
    assert isinstance(layout, Layout)
    assert "header" in [child.name for child in layout.children]
    assert "body" in [child.name for child in layout.children]
    body = layout["body"]
    assert "left" in [child.name for child in body.children]
    assert "right" in [child.name for child in body.children]


def test_run_tui_execution(tmp_path):
    test_db = tmp_path / "test_run.db"
    init_db(test_db)
    # Should run and print without raising exceptions
    run_tui(db_path=test_db, watch=False)
