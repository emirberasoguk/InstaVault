import json
from pathlib import Path
import sqlite3
import threading
import time
import urllib.request
import pytest

from instavault.db import SCHEMA_SQL, init_db
from instavault.report import fetch_report_data, generate_report, render_html_report, render_hourly_svg
from instavault.web import InstaVaultRequestHandler, ThreadingHTTPServer, get_web_dashboard_html


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_vault.db"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)

    cur = conn.cursor()
    # Exports
    cur.execute("""
        INSERT INTO exports (file_sha256, export_dir, rel_path, file_type, date_range_start, date_range_end, record_count)
        VALUES ('hash1', '/test', 'vid.html', 'videos_watched', '2026-08-01', '2026-08-31', 5)
    """)
    # Videos
    cur.execute("""
        INSERT INTO videos_watched (url, caption, hashtags, owner_username, owner_name, watched_at)
        VALUES 
        ('https://instagram.com/p/1', 'Night video', '#tech', 'creator_one', 'Creator One', '2026-08-10 03:30:00'),
        ('https://instagram.com/p/2', 'Day video', '#code', 'creator_one', 'Creator One', '2026-08-10 14:15:00'),
        ('https://instagram.com/p/3', 'Another day video', '#linux', 'creator_two', 'Creator Two', '2026-08-11 16:45:00')
    """)
    # Posts
    cur.execute("""
        INSERT INTO posts_viewed (url, viewed_at)
        VALUES ('https://instagram.com/p/p1', '2026-08-10 12:00:00')
    """)
    # Saved
    cur.execute("""
        INSERT INTO saved_posts (url, saved_at)
        VALUES ('https://instagram.com/p/s1', '2026-08-10 13:00:00')
    """)
    # Social: following
    cur.execute("""
        INSERT INTO social_connections (username, connection_type, connected_at)
        VALUES 
        ('mutual_friend', 'following', '2026-01-01 10:00:00'),
        ('unfollower_guy', 'following', '2026-01-01 10:00:00'),
        ('mutual_friend', 'follower', '2026-01-01 10:00:00'),
        ('fan_user', 'follower', '2026-01-01 10:00:00')
    """)
    conn.commit()
    conn.close()
    return db_file


def test_fetch_report_data_and_svg(test_db: Path):
    conn = init_db(test_db)
    data = fetch_report_data(conn)

    assert data["video_count"] == 3
    assert data["post_count"] == 1
    assert data["saved_count"] == 1
    assert data["follower_count"] == 2
    assert data["following_count"] == 2
    assert data["mutual_count"] == 1
    assert data["unfollower_count"] == 1
    assert data["fans_count"] == 1
    assert data["unfollowers"][0]["username"] == "unfollower_guy"
    assert data["night_video_count"] == 1
    assert round(data["night_ratio"], 1) == 33.3
    assert len(data["creators"]) == 2
    assert data["creators"][0]["owner_username"] == "creator_one"
    assert data["creators"][0]["count"] == 2

    # SVG rendering
    svg = render_hourly_svg(data["hourly_distribution"])
    assert "<svg" in svg
    assert "barGradNight" in svg
    assert "barGradDay" in svg


def test_generate_report_standalone(test_db: Path, tmp_path: Path):
    out_html = tmp_path / "out_report.html"
    res = generate_report(db_path=test_db, output_path=out_html)

    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "InstaVault Analitik Raporu" in content
    assert "creator_one" in content
    assert "backdrop-filter" in content
    # Offline verification: No external CDN or webfont links or external resources
    assert "<link rel=\"stylesheet\" href=\"http" not in content
    assert "<script src=\"http" not in content
    assert "fonts.googleapis.com" not in content
    assert "cdnjs.cloudflare.com" not in content


def test_generate_report_empty_db(tmp_path: Path):
    empty_db = tmp_path / "empty.db"
    out_html = tmp_path / "empty_report.html"
    res = generate_report(db_path=empty_db, output_path=out_html)

    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "InstaVault Analitik Raporu" in content


def test_web_server_endpoints(test_db: Path):
    # Set handler db_path
    InstaVaultRequestHandler.db_path = test_db

    # Use port 0 to bind dynamically to any free port
    server = ThreadingHTTPServer(("127.0.0.1", 0), InstaVaultRequestHandler)
    port = server.server_port
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    base_url = f"http://127.0.0.1:{port}"
    time.sleep(0.1)

    try:
        # GET /
        with urllib.request.urlopen(f"{base_url}/") as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8")
            assert "InstaVault" in body
            assert "unfollower-search" in body

        # GET /api/stats
        with urllib.request.urlopen(f"{base_url}/api/stats") as resp:
            assert resp.status == 200
            stats = json.loads(resp.read().decode("utf-8"))
            assert stats["video_count"] == 3
            assert stats["mutual_count"] == 1
            assert stats["unfollower_count"] == 1

        # GET /api/unfollowers
        with urllib.request.urlopen(f"{base_url}/api/unfollowers") as resp:
            assert resp.status == 200
            unfollowers = json.loads(resp.read().decode("utf-8"))
            assert len(unfollowers) == 1
            assert unfollowers[0]["username"] == "unfollower_guy"

        # GET /api/timeline
        with urllib.request.urlopen(f"{base_url}/api/timeline") as resp:
            assert resp.status == 200
            timeline = json.loads(resp.read().decode("utf-8"))
            assert len(timeline["hourly"]) == 24
            assert len(timeline["daily"]) >= 1

        # GET /api/creators
        with urllib.request.urlopen(f"{base_url}/api/creators") as resp:
            assert resp.status == 200
            creators = json.loads(resp.read().decode("utf-8"))
            assert len(creators) == 2
            assert creators[0]["username"] == "creator_one"

        # GET /api/nonexistent -> 404
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base_url}/api/nonexistent")
        assert exc_info.value.code == 404

    finally:
        server.shutdown()
        server.server_close()
