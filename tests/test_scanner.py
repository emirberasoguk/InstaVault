from pathlib import Path
import sqlite3
import pytest

from instavault.db import init_db
from instavault.scanner import scan_and_ingest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_scan_and_ingest_deduplication(tmp_path):
    db_file = tmp_path / "test_vault.db"
    conn = init_db(db_file)

    # First ingest run
    summary1 = scan_and_ingest(conn, FIXTURES_DIR)
    assert summary1.total_files_scanned >= 3
    assert summary1.new_files_ingested >= 3
    assert summary1.files_skipped_duplicate == 0

    # Verify counts in DB
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM exports")
    assert cur.fetchone()[0] >= 3

    cur.execute("SELECT COUNT(*) FROM videos_watched")
    assert cur.fetchone()[0] == 1

    cur.execute("SELECT COUNT(*) FROM social_connections")
    assert cur.fetchone()[0] == 3

    # Second ingest run with same fixtures -> must skip all due to SHA256 match
    summary2 = scan_and_ingest(conn, FIXTURES_DIR)
    assert summary2.new_files_ingested == 0
    assert summary2.files_skipped_duplicate >= 3

    # Counts in DB should remain unchanged
    cur.execute("SELECT COUNT(*) FROM videos_watched")
    assert cur.fetchone()[0] == 1
