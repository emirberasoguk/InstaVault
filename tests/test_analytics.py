from datetime import datetime, timedelta
import sqlite3
import pytest
import numpy as np

from instavault.analytics import (
    FatigueReport,
    FriendshipScore,
    ClusteringResult,
    GDPRUnforgottenReport,
    calculate_digital_fatigue,
    compute_digital_fatigue,
    calculate_friendship_scores,
    compute_social_insights,
    cluster_content_interests,
    compute_content_clusters,
    audit_unforgotten_interests,
    normalize_turkish_text,
    clean_text_tr,
    PureTfidfVectorizer,
    run_kmeans,
    compute_silhouette_score,
)
from instavault.db import init_db


# ===========================================================================
# 1. DIGITAL FATIGUE SCORE TESTS
# ===========================================================================

def test_fatigue_empty():
    report = calculate_digital_fatigue(timestamps=[])
    assert report.total_events == 0
    assert report.score == 0.0
    assert report.level == "Düşük"
    assert report.night_ratio == 0.0


def test_fatigue_daytime_mild():
    # 5 events during daytime (14:00 - 14:20), spaced by 4 minutes (same session)
    base = datetime(2026, 8, 1, 14, 0, 0)
    timestamps = [base + timedelta(minutes=4 * i) for i in range(5)]

    report = calculate_digital_fatigue(timestamps=timestamps)
    assert report.total_events == 5
    assert report.total_sessions == 1
    assert report.night_events == 0
    assert report.night_ratio == 0.0
    assert report.level in ("Düşük", "Dengeli")
    assert report.score < 50.0


def test_fatigue_session_gap_detection():
    # Two sessions: 3 events in morning, 30 min gap, then 3 events
    t1 = datetime(2026, 8, 1, 10, 0, 0)
    t2 = datetime(2026, 8, 1, 10, 5, 0)
    t3 = datetime(2026, 8, 1, 10, 10, 0)
    # 30 min gap
    t4 = datetime(2026, 8, 1, 10, 45, 0)
    t5 = datetime(2026, 8, 1, 10, 50, 0)

    report = calculate_digital_fatigue(timestamps=[t1, t2, t3, t4, t5])
    assert report.total_sessions == 2
    assert report.total_events == 5
    assert report.avg_session_events == 2.5


def test_fatigue_night_owl_extreme_consumption():
    # 100 events between 01:00 AM and 04:30 AM
    base = datetime(2026, 8, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=2 * i) for i in range(100)]

    report = calculate_digital_fatigue(timestamps=timestamps)
    assert report.night_events == 100
    assert report.night_ratio == 1.0
    assert report.score >= 70.0
    assert report.level in ("Yüksek Risk", "Aşırı Tüketim")


def test_fatigue_from_db(tmp_path):
    db_file = tmp_path / "fatigue_vault.db"
    conn = init_db(db_file)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO exports (file_sha256, export_dir, rel_path, file_type)
        VALUES ('hash1', 'dir', 'file.html', 'videos_watched')
        """
    )
    exp_id = cur.lastrowid

    times = [
        "2026-08-01 02:10:00",
        "2026-08-01 02:15:00",
        "2026-08-01 02:20:00",
        "2026-08-01 02:50:00",  # New session
    ]
    for idx, t in enumerate(times):
        cur.execute(
            """
            INSERT INTO videos_watched (url, watched_at, export_id)
            VALUES (?, ?, ?)
            """,
            (f"https://instagram.com/p/{idx}", t, exp_id),
        )
    conn.commit()

    report = calculate_digital_fatigue(conn=conn)
    assert report.total_events == 4
    assert report.total_sessions == 2
    assert report.night_events == 4
    assert report.night_ratio == 1.0


def test_compute_digital_fatigue_wrapper():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE videos_watched (watched_at TEXT);")
    conn.execute("CREATE TABLE posts_viewed (viewed_at TEXT);")

    empty_res = compute_digital_fatigue(conn)
    assert empty_res["total_events"] == 0
    assert empty_res["fatigue_score"] == 0

    for h in range(10):
        conn.execute(f"INSERT INTO videos_watched VALUES ('2026-08-20 {10+h:02d}:00:00');")
    for h in range(5):
        conn.execute(f"INSERT INTO posts_viewed VALUES ('2026-08-21 {h:02d}:15:00');")

    res = compute_digital_fatigue(conn)
    assert res["total_events"] == 15
    assert res["night_events"] == 5
    assert res["night_ratio_pct"] > 30.0
    assert res["fatigue_score"] >= 15
    assert res["peak_hour"] is not None


# ===========================================================================
# 2. FRIENDSHIP & RECIPROCITY SCORE TESTS
# ===========================================================================

def test_friendship_empty():
    results = calculate_friendship_scores(interactions=[])
    assert results == []


def test_friendship_from_interactions_ranking():
    interactions = [
        {"username": "best_friend", "type": "mutual_follow", "count": 1},
        {"username": "best_friend", "type": "inbox", "count": 10},
        {"username": "best_friend", "type": "story_like", "count": 5},
        {"username": "casual_user", "type": "post_like", "count": 2},
        {"username": "stranger", "type": "view", "count": 1},
    ]

    scores = calculate_friendship_scores(interactions=interactions)
    assert len(scores) == 3
    assert scores[0].username == "best_friend"
    assert scores[0].mutual_follow is True
    assert scores[0].score > scores[1].score
    assert scores[1].username == "casual_user"
    assert scores[2].username == "stranger"


def test_friendship_from_db(tmp_path):
    db_file = tmp_path / "social_vault.db"
    conn = init_db(db_file)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO exports (file_sha256, export_dir, rel_path, file_type)
        VALUES ('hash_soc', 'dir', 'file.html', 'followers')
        """
    )
    exp_id = cur.lastrowid

    cur.execute(
        "INSERT INTO social_connections (username, connection_type, connected_at, export_id) VALUES (?, ?, ?, ?)",
        ("alice", "follower", "2026-01-01 10:00:00", exp_id),
    )
    cur.execute(
        "INSERT INTO social_connections (username, connection_type, connected_at, export_id) VALUES (?, ?, ?, ?)",
        ("alice", "following", "2026-01-01 10:00:00", exp_id),
    )
    cur.execute(
        "INSERT INTO social_connections (username, connection_type, connected_at, export_id) VALUES (?, ?, ?, ?)",
        ("bob", "follower", "2026-01-01 10:00:00", exp_id),
    )
    for i in range(5):
        cur.execute(
            "INSERT INTO videos_watched (url, owner_username, watched_at, export_id) VALUES (?, ?, ?, ?)",
            (f"https://instagram.com/reel/{i}", "alice", f"2026-02-0{i+1} 12:00:00", exp_id),
        )
    conn.commit()

    scores = calculate_friendship_scores(conn=conn)
    assert len(scores) >= 2
    alice_score = next(s for s in scores if s.username == "alice")
    bob_score = next(s for s in scores if s.username == "bob")

    assert alice_score.mutual_follow is True
    assert bob_score.mutual_follow is False
    assert alice_score.score > bob_score.score


def test_compute_social_insights_wrapper():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE social_connections (username TEXT, connection_type TEXT);")
    conn.execute("INSERT INTO social_connections VALUES ('alice', 'follower');")
    conn.execute("INSERT INTO social_connections VALUES ('bob', 'follower');")
    conn.execute("INSERT INTO social_connections VALUES ('alice', 'following');")
    conn.execute("INSERT INTO social_connections VALUES ('charlie', 'following');")

    res = compute_social_insights(conn)
    assert res["follower_count"] == 2
    assert res["following_count"] == 2
    assert res["mutual_count"] == 1
    assert "charlie" in res["not_following_back"]
    assert "bob" in res["fans_not_followed"]


# ===========================================================================
# 3. INTEREST & CONTENT CLUSTERING TESTS
# ===========================================================================

def test_normalize_turkish_text():
    text = "İSTANBUL ve Ankara #kodlama https://github.com 123"
    norm = normalize_turkish_text(text)
    assert "istanbul" in norm
    assert "ankara" in norm
    assert "https" not in norm
    assert "123" not in norm


def test_clean_text_turkish():
    sample = "Yapay Zeka ve Python ile Makine Öğrenmesi! Harika bir gün. #veri_bilimi #kodlama"
    tokens = clean_text_tr(sample)
    assert "yapay" in tokens
    assert "zeka" in tokens
    assert "python" in tokens
    assert "makine" in tokens
    assert "öğrenmesi" in tokens
    assert "veri_bilimi" in tokens
    assert "kodlama" in tokens
    assert "ve" not in tokens
    assert "ile" not in tokens
    assert "bir" not in tokens


def test_pure_tfidf_vectorizer():
    docs = [
        ["python", "veri", "yapay", "zeka"],
        ["python", "kodlama", "yazilim"],
        ["yemek", "tarif", "mutfak"],
        ["yemek", "tatli", "pasta"],
    ]
    vectorizer = PureTfidfVectorizer(min_df=1)
    X = vectorizer.fit_transform(docs)

    assert X.shape[0] == 4
    assert X.shape[1] > 0
    for row in X:
        assert np.isclose(np.linalg.norm(row), 1.0)


def test_cluster_content_interests_three_topics():
    posts = [
        # AI / Tech topic
        {"caption": "Python ve derin öğrenme modelleri", "hashtags": "#yapayzeka #yazilim", "owner_username": "tech_guru"},
        {"caption": "Yeni yapay zeka algoritması kodlama", "hashtags": "#python #ai", "owner_username": "tech_guru"},
        {"caption": "Veri bilimi ve makine öğrenmesi projeleri", "hashtags": "#kodlama #yazilim", "owner_username": "data_lead"},
        # Culinary / Food topic
        {"caption": "Nefis İtalyan makarna tarifi", "hashtags": "#yemek #tarif", "owner_username": "chef_mario"},
        {"caption": "Pratik akşam yemeği menüsü mutfak", "hashtags": "#yemek #mutfak", "owner_username": "chef_mario"},
        {"caption": "Fırında lezzetli tatlı ve pasta", "hashtags": "#tatli #pasta", "owner_username": "baker_jane"},
        # Sports / Fitness topic
        {"caption": "Günlük fitness antrenmanı ve kardiyo", "hashtags": "#spor #fitness", "owner_username": "fit_coach"},
        {"caption": "Vücut geliştirme motivasyonu egzersiz", "hashtags": "#fitness #gym", "owner_username": "fit_coach"},
        {"caption": "Koşu ve açık hava spor aktiviteleri", "hashtags": "#spor #maraton", "owner_username": "runner_sam"},
    ]

    result = cluster_content_interests(posts, k_range=range(3, 5))
    assert isinstance(result, ClusteringResult)
    assert result.total_documents == 9
    assert result.best_k in (3, 4)
    assert len(result.clusters) == result.best_k
    assert result.silhouette_score > 0.0

    for cl in result.clusters:
        assert cl.size > 0
        assert len(cl.top_terms) > 0


def test_cluster_empty_and_single():
    assert cluster_content_interests([]).total_documents == 0
    single_res = cluster_content_interests([{"caption": "Tek başına bir post"}])
    assert single_res.total_documents == 1
    assert single_res.best_k == 1


def test_compute_content_clusters_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE videos_watched (caption TEXT, hashtags TEXT, owner_username TEXT);")
    conn.execute("CREATE TABLE saved_posts (caption TEXT, hashtags TEXT, owner_username TEXT);")

    # Insert 6 sample records
    for i in range(3):
        conn.execute("INSERT INTO videos_watched VALUES (?, ?, ?)", (f"Python yazılım kodu {i}", "#yazilim #ai", "tech_dev"))
    for i in range(3):
        conn.execute("INSERT INTO saved_posts VALUES (?, ?, ?)", (f"Lezzetli tatlı tarifi {i}", "#tatli #pasta", "chef_anna"))

    clusters = compute_content_clusters(conn, k_clusters=2)
    assert len(clusters) == 2
    assert clusters[0]["document_count"] > 0


# ===========================================================================
# 4. GDPR UNFORGOTTEN AUDITOR TESTS
# ===========================================================================

def test_gdpr_unforgotten_no_overlap():
    deleted_items = ["eski tatil fotoğrafları", "istanbul vapur manzarası"]
    ad_topics = ["Cryptocurrency Trading", "Cloud Computing SaaS", "Car Insurance"]

    report = audit_unforgotten_interests(deleted_items, ad_topics)
    assert report.match_count == 0
    assert report.privacy_risk_level == "Düşük"
    assert report.compliance_score == 100.0
    assert len(report.unforgotten_matches) == 0


def test_gdpr_unforgotten_exact_and_substring_matches():
    deleted_searches = [
        "kripto para",
        "diyet hapı",
        "araba kiralama",
    ]
    ad_target_profiles = [
        "Kripto Para",                         # Exact match
        "Hızlı Diyet Hapı ve Zayıflama",       # Substring match
        "Doğa Yürüyüşü",                       # No match
    ]

    report = audit_unforgotten_interests(deleted_searches, ad_target_profiles)
    assert report.match_count == 2
    assert report.privacy_risk_level in ("Orta", "Yüksek")
    assert report.compliance_score < 100.0

    top_match = report.unforgotten_matches[0]
    assert top_match.similarity_score >= 0.7


def test_gdpr_unforgotten_dict_inputs():
    deleted_items = [
        {"search_query": "yazılım mühendisliği iş ilanları"},
        {"query": "ev kiralama fiyatları"},
    ]
    ad_targets = [
        {"name": "Yazılım Mühendisliği Kariyer"},
        {"title": "Mutfak Robotu"},
    ]

    report = audit_unforgotten_interests(deleted_items, ad_targets)
    assert report.total_deleted_audited == 2
    assert report.total_ad_targets_audited == 2
    assert report.match_count >= 1
