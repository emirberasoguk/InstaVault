from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from typing import Dict, List, Optional
from bs4 import BeautifulSoup

from instavault.db import is_file_ingested
from instavault.parser import (
    compute_file_sha256,
    parse_export_header,
    parse_media_cards,
    parse_social_connections,
)


@dataclass
class ScanSummary:
    total_files_scanned: int = 0
    new_files_ingested: int = 0
    files_skipped_duplicate: int = 0
    records_inserted: Dict[str, int] = field(default_factory=lambda: {
        "videos_watched": 0,
        "posts_viewed": 0,
        "saved_posts": 0,
        "followers": 0,
        "following": 0,
    })


def detect_file_type(path: Path) -> Optional[str]:
    name = path.name.lower()

    if name == "videos_watched.html" or ("video" in name and name.endswith(".html")):
        return "videos_watched"
    if name == "posts_viewed.html" or ("post" in name and "view" in name and name.endswith(".html")):
        return "posts_viewed"
    if name == "saved_posts.html" or ("saved" in name and name.endswith(".html")):
        return "saved_posts"
    if name.startswith("followers") and name.endswith(".html"):
        return "followers"
    if name == "following.html" or ("following" in name and name.endswith(".html")):
        return "following"
    if "pending_follow" in name and name.endswith(".html"):
        return "pending_requests"
    return None


def ingest_file(conn: sqlite3.Connection, file_path: Path, root_dir: Path) -> int:
    file_type = detect_file_type(file_path)
    if not file_type:
        return 0

    sha256_hash = compute_file_sha256(file_path)
    if is_file_ingested(conn, sha256_hash):
        return -1  # Already ingested

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(content, "lxml")
    header_meta = parse_export_header(soup)

    rel_path = str(file_path.relative_to(root_dir))
    export_dir_name = file_path.parent.name

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO exports (
            file_sha256, export_dir, rel_path, file_type,
            account_username, date_range_start, date_range_end, generated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sha256_hash,
            export_dir_name,
            rel_path,
            file_type,
            header_meta.get("account_username"),
            header_meta.get("date_range_start"),
            header_meta.get("date_range_end"),
            header_meta.get("generated_at"),
        ),
    )
    export_id = cur.lastrowid

    inserted_count = 0

    if file_type in ("videos_watched", "posts_viewed", "saved_posts"):
        records = parse_media_cards(soup)
        target_table = file_type
        for r in records:
            if file_type == "videos_watched":
                cur.execute(
                    """
                    INSERT OR IGNORE INTO videos_watched 
                    (url, caption, hashtags, owner_username, owner_name, owner_url, watched_at, export_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["url"],
                        r["caption"],
                        r["hashtags"],
                        r["owner_username"],
                        r["owner_name"],
                        r["owner_url"],
                        r["timestamp"],
                        export_id,
                    ),
                )
            elif file_type == "posts_viewed":
                cur.execute(
                    """
                    INSERT OR IGNORE INTO posts_viewed 
                    (url, caption, hashtags, owner_username, owner_name, owner_url, viewed_at, export_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["url"],
                        r["caption"],
                        r["hashtags"],
                        r["owner_username"],
                        r["owner_name"],
                        r["owner_url"],
                        r["timestamp"],
                        export_id,
                    ),
                )
            elif file_type == "saved_posts":
                cur.execute(
                    """
                    INSERT OR IGNORE INTO saved_posts 
                    (url, caption, hashtags, owner_username, owner_name, owner_url, saved_at, export_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["url"],
                        r["caption"],
                        r["hashtags"],
                        r["owner_username"],
                        r["owner_name"],
                        r["owner_url"],
                        r["timestamp"],
                        export_id,
                    ),
                )
            if cur.rowcount > 0:
                inserted_count += 1

    elif file_type in ("followers", "following", "pending_requests"):
        conn_type = "follower" if file_type == "followers" else ("following" if file_type == "following" else "pending")
        records = parse_social_connections(soup, default_type=conn_type)
        for r in records:
            cur.execute(
                """
                INSERT OR IGNORE INTO social_connections
                (username, profile_url, connection_type, connected_at, export_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    r["username"],
                    r["profile_url"],
                    r["connection_type"],
                    r["connected_at"],
                    export_id,
                ),
            )
            if cur.rowcount > 0:
                inserted_count += 1

    cur.execute("UPDATE exports SET record_count = ? WHERE id = ?", (inserted_count, export_id))
    conn.commit()
    return inserted_count


def scan_and_ingest(conn: sqlite3.Connection, base_dir: Path | str) -> ScanSummary:
    root = Path(base_dir).expanduser().resolve()
    summary = ScanSummary()

    if not root.exists():
        raise FileNotFoundError(f"Source directory not found: {root}")

    # Gather all candidate HTML files
    html_files = sorted(root.rglob("*.html"))
    for file_path in html_files:
        ftype = detect_file_type(file_path)
        if not ftype:
            continue

        summary.total_files_scanned += 1
        res = ingest_file(conn, file_path, root)
        if res == -1:
            summary.files_skipped_duplicate += 1
        else:
            summary.new_files_ingested += 1
            if ftype in summary.records_inserted:
                summary.records_inserted[ftype] += res

    return summary
