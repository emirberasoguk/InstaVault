"""Analytics and Machine Learning Engine for InstaVault.

Ponytail principle: Pure Python + NumPy implementation with zero extra dependencies.
Features:
1. Digital Fatigue Score (Session gap > 15m, night window 00:00-05:00 penalty, 0-100 normalized)
   Labels: "Düşük", "Dengeli", "Yüksek Risk", "Aşırı Tüketim"
2. Friendship & Reciprocity Score (Personalized PageRank & Multi-factor Weighted Graph)
   Weights: mutual follow, inbox messages, story likes, post likes/views
3. Interest & Content Clustering (TF-IDF + KMeans++ + Silhouette Score k=3..8)
   Explainable top terms and top creators per cluster.
4. GDPR Unforgotten Auditor (Deleted searches/posts vs. retained ad target interests)
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
import re
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# STOPWORDS & TEXT PREPROCESSING
# ---------------------------------------------------------------------------

TURKISH_STOPWORDS: Set[str] = {
    "acaba", "altmış", "altı", "ama", "ancak", "arada", "artık", "asla", "aslında",
    "ayrıca", "bana", "bazen", "bazı", "bazıları", "bazısı", "belki", "ben", "benden",
    "beni", "benim", "beri", "beş", "bile", "bin", "bir", "biraz", "biri", "birkaç",
    "birkez", "birçok", "birisi", "biz", "bizden", "bize", "bizi", "bizim",
    "böyle", "böylece", "bu", "buna", "bunda", "bundan", "bunu", "bunun", "burada",
    "bütün", "çoğu", "çoğuna", "çoğunu", "çok", "çünkü", "da", "daha", "dahi", "de",
    "defa", "değil", "diye", "doksan", "dokuz", "dolayı", "dolayısıyla", "dört", "edecek",
    "eden", "ederek", "edilecek", "ediliyor", "edilmesi", "ediyor", "eğer", "elli", "en",
    "etmesi", "etti", "ettiği", "ettiğini", "fakat", "gibi", "göre", "halen", "hangi",
    "hatta", "hem", "henüz", "hep", "hepsi", "hepsine", "hepsini", "her", "herkes",
    "herkese", "herkesi", "hiç", "hiçbir", "hiçbiri", "için", "içinde", "iki", "ile",
    "ilgili", "ise", "işte", "itibaren", "itibariyle", "kadar", "karşın", "katrilyon",
    "kendi", "kendine", "kendini", "kendisi", "kendisine", "kendisini", "kez", "ki",
    "kim", "kime", "kimi", "kimse", "kırk", "milyar", "milyon", "mu", "mü", "mı",
    "nasıl", "ne", "neden", "nedenle", "nerde", "nerede", "nereye", "nitekim", "o",
    "olan", "olarak", "oldu", "olduğu", "olduğunu", "olduklarını", "olmadı", "olmadığı",
    "olmak", "olması", "olmayan", "olmaz", "olsa", "olsun", "olup", "olur", "olursa",
    "oluyor", "on", "ona", "ondan", "onlar", "onlardan", "onlara", "onların",
    "onu", "onun", "otuz", "oysa", "öyle", "pek", "rağmen", "sadece", "sanki", "sekiz",
    "seksen", "sen", "senden", "sana", "seni", "senin", "siz", "sizden", "size", "sizi",
    "sizin", "sonra", "şayet", "şey", "şeyden", "şeye", "şeyi", "şeyler", "şimdi",
    "şöyle", "şu", "şuna", "şunda", "şundan", "şunlar", "şunu", "şunun", "tabii",
    "tam", "tamam", "tarafından", "trilyon", "tüm", "üç", "üzere", "var", "vardı",
    "ve", "veya", "veyahut", "ya", "yani", "yedi", "yetmiş", "yine", "yok", "yoksa",
    "yüz", "zaten",
    # Common social media tokens & noise
    "reels", "reel", "post", "instagram", "keşfet", "kesfet", "fyp", "viral",
    "video", "insta", "takip", "beğen", "trend", "explore", "com", "https", "http",
    "the", "and", "to", "of", "in", "for", "is", "on", "that", "by", "this",
    "with", "you", "it", "not", "or", "be", "are", "from", "at", "as", "your", "all",
}


def normalize_turkish_text(text: str) -> str:
    """Normalizes Turkish text for search and tokens."""
    if not text:
        return ""
    t = text.replace("İ", "i").replace("I", "ı").lower()
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\d+", " ", t)
    return " ".join(t.split())


def clean_text_tr(text: str) -> List[str]:
    """Cleans Turkish and multilingual text, parses hashtags, removes stopwords."""
    if not text:
        return []
    t = text.replace("İ", "i").replace("I", "ı").lower()
    hashtags = re.findall(r"#([a-zçğıöşü0-9_]+)", t)
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    words = re.findall(r"[a-zçğıöşü0-9]+", t)
    all_tokens = words + hashtags

    return [
        w for w in all_tokens
        if len(w) > 2 and not w.isdigit() and w not in TURKISH_STOPWORDS
    ]


def parse_timestamp_dt(ts: Any) -> Optional[datetime]:
    if isinstance(ts, datetime):
        return ts
    if not isinstance(ts, str):
        return None
    cleaned = ts.replace("\xa0", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%b %d, %Y %I:%M %p"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. DIGITAL FATIGUE SCORE
# ---------------------------------------------------------------------------

@dataclass
class FatigueReport:
    score: float
    level: str  # "Düşük", "Dengeli", "Yüksek Risk", "Aşırı Tüketim"
    total_events: int
    total_sessions: int
    night_events: int
    night_ratio: float
    avg_session_events: float
    max_session_duration_minutes: float


def calculate_digital_fatigue(
    timestamps: Optional[List[Any]] = None,
    conn: Optional[sqlite3.Connection] = None,
    session_gap_minutes: float = 15.0,
) -> FatigueReport:
    """Calculates Digital Fatigue Score (0-100) and level tag.

    - Gap > 15 minutes defines a new session.
    - Night window (00:00 - 05:00) penalizes the score.
    - Level tags: 'Düşük', 'Dengeli', 'Yüksek Risk', 'Aşırı Tüketim'.
    """
    event_dts: List[datetime] = []

    if timestamps:
        for t in timestamps:
            dt = parse_timestamp_dt(t)
            if dt:
                event_dts.append(dt)
    elif conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT watched_at FROM videos_watched
            UNION ALL
            SELECT viewed_at FROM posts_viewed
            ORDER BY 1 ASC
            """
        )
        for row in cur.fetchall():
            dt = parse_timestamp_dt(row[0])
            if dt:
                event_dts.append(dt)

    if not event_dts:
        return FatigueReport(
            score=0.0,
            level="Düşük",
            total_events=0,
            total_sessions=0,
            night_events=0,
            night_ratio=0.0,
            avg_session_events=0.0,
            max_session_duration_minutes=0.0,
        )

    event_dts.sort()
    total_events = len(event_dts)

    # 1. Detect sessions (gap > 15 minutes)
    sessions: List[List[datetime]] = []
    current_session: List[datetime] = [event_dts[0]]

    for i in range(1, total_events):
        diff = (event_dts[i] - event_dts[i - 1]).total_seconds() / 60.0
        if diff > session_gap_minutes:
            sessions.append(current_session)
            current_session = [event_dts[i]]
        else:
            current_session.append(event_dts[i])
    if current_session:
        sessions.append(current_session)

    total_sessions = len(sessions)

    # 2. Night consumption (00:00 - 05:00)
    night_events = sum(1 for dt in event_dts if 0 <= dt.hour < 5)
    night_ratio = night_events / total_events if total_events > 0 else 0.0

    # 3. Session statistics
    durations = [
        max(0.0, (s[-1] - s[0]).total_seconds() / 60.0) for s in sessions
    ]
    max_session_duration = max(durations) if durations else 0.0
    avg_session_events = total_events / total_sessions if total_sessions > 0 else 0.0

    # 4. Normalized score (0 - 100)
    # Night ratio is the strongest biological fatigue driver: 45%
    # Volume factor: 30% (normalized up to 200 events)
    # Session length & density: 25%
    night_component = (night_ratio * 100.0) * 0.45
    volume_component = min(1.0, total_events / 150.0) * 30.0
    session_component = (
        0.5 * min(1.0, avg_session_events / 20.0) +
        0.5 * min(1.0, max_session_duration / 60.0)
    ) * 25.0

    raw_score = night_component + volume_component + session_component
    final_score = round(float(np.clip(raw_score, 0.0, 100.0)), 1)

    if final_score < 25.0:
        level = "Düşük"
    elif final_score < 55.0:
        level = "Dengeli"
    elif final_score < 80.0:
        level = "Yüksek Risk"
    else:
        level = "Aşırı Tüketim"

    return FatigueReport(
        score=final_score,
        level=level,
        total_events=total_events,
        total_sessions=total_sessions,
        night_events=night_events,
        night_ratio=round(night_ratio, 4),
        avg_session_events=round(avg_session_events, 2),
        max_session_duration_minutes=round(max_session_duration, 1),
    )


def compute_digital_fatigue(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Compatibility wrapper returning dictionary format with hourly distribution."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT watched_at FROM videos_watched 
        UNION ALL 
        SELECT viewed_at FROM posts_viewed
        ORDER BY 1 ASC
        """
    )
    rows = cur.fetchall()

    if not rows:
        return {
            "total_events": 0,
            "total_sessions": 0,
            "night_events": 0,
            "night_ratio_pct": 0.0,
            "fatigue_score": 0,
            "fatigue_level": "Veri Yok",
            "hourly_distribution": [0] * 24,
            "peak_hour": None,
        }

    timestamps: List[datetime] = []
    hourly_distribution = [0] * 24

    for r in rows:
        dt = parse_timestamp_dt(r[0])
        if dt:
            timestamps.append(dt)
            hourly_distribution[dt.hour] += 1

    report = calculate_digital_fatigue(timestamps=timestamps)
    peak_hour = int(np.argmax(hourly_distribution)) if timestamps else None

    return {
        "total_events": report.total_events,
        "total_sessions": report.total_sessions,
        "night_events": report.night_events,
        "night_ratio_pct": round(report.night_ratio * 100.0, 1),
        "fatigue_score": int(round(report.score)),
        "fatigue_level": report.level,
        "hourly_distribution": hourly_distribution,
        "peak_hour": peak_hour,
    }


# ---------------------------------------------------------------------------
# 2. FRIENDSHIP & RECIPROCITY SCORE (PAGERANK & WEIGHTED GRAPH)
# ---------------------------------------------------------------------------

@dataclass
class FriendshipScore:
    username: str
    score: float  # Normalized 0-100
    mutual_follow: bool
    breakdown: Dict[str, float] = field(default_factory=dict)


def calculate_friendship_scores(
    interactions: Optional[List[Dict[str, Any]]] = None,
    conn: Optional[sqlite3.Connection] = None,
    self_username: str = "self",
    damping: float = 0.85,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> List[FriendshipScore]:
    """Calculates Friendship & Reciprocity Scores using Personalized PageRank

    and multi-factor interaction graph.
    Weights:
      - mutual_follow: 3.0
      - inbox: 4.0
      - story_like: 2.0
      - post_like: 1.0
      - view: 0.5
      - saved: 1.5
    """
    interaction_weights = {
        "mutual_follow": 3.0,
        "inbox": 4.0,
        "story_like": 2.0,
        "post_like": 1.0,
        "view": 0.5,
        "saved": 1.5,
    }

    user_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    mutual_status: Dict[str, bool] = defaultdict(bool)

    if conn:
        cur = conn.cursor()
        cur.execute("SELECT username, connection_type FROM social_connections")
        conns = cur.fetchall()
        followers = {row[0] for row in conns if row[1] == "follower"}
        following = {row[0] for row in conns if row[1] == "following"}
        all_users = followers | following

        for u in all_users:
            is_mutual = (u in followers) and (u in following)
            mutual_status[u] = is_mutual
            if is_mutual:
                user_stats[u]["mutual_follow"] += 1.0
            elif u in following:
                user_stats[u]["following"] += 1.0
            elif u in followers:
                user_stats[u]["follower"] += 1.0

        # Videos watched
        cur.execute(
            """
            SELECT owner_username, COUNT(*) 
            FROM videos_watched 
            WHERE owner_username IS NOT NULL 
            GROUP BY owner_username
            """
        )
        for row in cur.fetchall():
            user_stats[row[0]]["view"] += float(row[1])

        # Saved posts
        cur.execute(
            """
            SELECT owner_username, COUNT(*) 
            FROM saved_posts 
            WHERE owner_username IS NOT NULL 
            GROUP BY owner_username
            """
        )
        for row in cur.fetchall():
            user_stats[row[0]]["saved"] += float(row[1])

    if interactions:
        for item in interactions:
            u = item.get("username") or item.get("target")
            if not u or u == self_username:
                continue
            itype = item.get("type", "post_like")
            count = float(item.get("count", 1.0))
            user_stats[u][itype] += count
            if itype == "mutual_follow":
                mutual_status[u] = True

    if not user_stats:
        return []

    # Graph Setup
    users = sorted(user_stats.keys())
    node_to_idx = {self_username: 0}
    for i, u in enumerate(users, start=1):
        node_to_idx[u] = i

    n = len(node_to_idx)
    adj = np.zeros((n, n), dtype=np.float64)

    for u, stats in user_stats.items():
        uidx = node_to_idx[u]
        w_in = 0.0
        w_out = 0.0

        if stats.get("mutual_follow", 0) > 0:
            w_in += interaction_weights["mutual_follow"]
            w_out += interaction_weights["mutual_follow"]
        if stats.get("follower", 0) > 0:
            w_in += 1.0
        if stats.get("following", 0) > 0:
            w_out += 1.0

        inbox_count = stats.get("inbox", 0.0)
        w_in += inbox_count * (interaction_weights["inbox"] * 0.5)
        w_out += inbox_count * (interaction_weights["inbox"] * 0.5)

        story_count = stats.get("story_like", 0.0)
        w_out += story_count * interaction_weights["story_like"]

        post_count = stats.get("post_like", 0.0)
        w_out += post_count * interaction_weights["post_like"]

        view_count = stats.get("view", 0.0)
        w_out += view_count * interaction_weights["view"]

        saved_count = stats.get("saved", 0.0)
        w_out += saved_count * interaction_weights["saved"]

        adj[0, uidx] = max(w_out, 0.1)
        adj[uidx, 0] = max(w_in, 0.1)

    # Transition probability matrix
    row_sums = adj.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    transition_mat = adj / row_sums

    # Personalized PageRank
    p = np.zeros(n, dtype=np.float64)
    p[0] = 1.0
    v = np.zeros(n, dtype=np.float64)
    v[0] = 1.0

    for _ in range(max_iter):
        p_next = damping * (transition_mat.T @ p) + (1.0 - damping) * v
        if np.linalg.norm(p_next - p, ord=1) < tol:
            p = p_next
            break
        p = p_next

    user_pr_scores = p[1:]
    max_pr = np.max(user_pr_scores) if len(user_pr_scores) > 0 and np.max(user_pr_scores) > 0 else 1.0

    results: List[FriendshipScore] = []
    for u in users:
        uidx = node_to_idx[u]
        stats = dict(user_stats[u])
        is_mutual = mutual_status[u]

        base_score = (p[uidx] / max_pr) * 80.0
        reciprocity_bonus = 20.0 if is_mutual else 0.0
        total_score = round(float(np.clip(base_score + reciprocity_bonus, 0.0, 100.0)), 2)

        results.append(
            FriendshipScore(
                username=u,
                score=total_score,
                mutual_follow=is_mutual,
                breakdown=stats,
            )
        )

    results.sort(key=lambda x: x.score, reverse=True)
    return results


def compute_social_insights(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Compatibility wrapper for social graph metrics."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT username FROM social_connections WHERE connection_type = 'follower'")
    followers = {r[0] for r in cur.fetchall()}

    cur.execute("SELECT DISTINCT username FROM social_connections WHERE connection_type = 'following'")
    following = {r[0] for r in cur.fetchall()}

    mutuals = sorted(list(followers & following))
    not_following_back = sorted(list(following - followers))
    fans_not_followed = sorted(list(followers - following))

    reciprocity_rate = (len(mutuals) / len(following) * 100) if following else 0.0

    return {
        "follower_count": len(followers),
        "following_count": len(following),
        "mutual_count": len(mutuals),
        "unfollower_count": len(not_following_back),
        "fan_count": len(fans_not_followed),
        "reciprocity_rate_pct": round(reciprocity_rate, 1),
        "not_following_back": not_following_back,
        "fans_not_followed": fans_not_followed,
    }


# ---------------------------------------------------------------------------
# 3. INTEREST & CONTENT CLUSTERING (TF-IDF + KMEANS++ + SILHOUETTE)
# ---------------------------------------------------------------------------

@dataclass
class ClusterInfo:
    cluster_id: int
    size: int
    top_terms: List[Tuple[str, float]]
    top_creators: List[Tuple[str, int]]


@dataclass
class ClusteringResult:
    best_k: int
    silhouette_score: float
    clusters: List[ClusterInfo]
    total_documents: int


class PureTfidfVectorizer:
    """Lightweight pure NumPy/Python TF-IDF vectorizer."""

    def __init__(self, min_df: int = 1, max_features: int = 500):
        self.min_df = min_df
        self.max_features = max_features
        self.vocabulary_: Dict[str, int] = {}
        self.idf_: np.ndarray = np.array([])
        self.feature_names_: List[str] = []

    def fit_transform(self, tokenized_docs: List[List[str]]) -> np.ndarray:
        n_docs = len(tokenized_docs)
        if n_docs == 0:
            return np.zeros((0, 0), dtype=np.float64)

        df_counts: Dict[str, int] = Counter()
        for doc in tokenized_docs:
            for t in set(doc):
                df_counts[t] += 1

        valid_terms = [
            (t, count) for t, count in df_counts.items() if count >= self.min_df
        ]
        valid_terms.sort(key=lambda x: x[1], reverse=True)
        valid_terms = valid_terms[: self.max_features]

        self.feature_names_ = [t for t, _ in valid_terms]
        self.vocabulary_ = {t: i for i, t in enumerate(self.feature_names_)}
        n_features = len(self.feature_names_)

        if n_features == 0:
            return np.zeros((n_docs, 0), dtype=np.float64)

        # Smooth IDF
        dfs = np.array([df_counts[t] for t in self.feature_names_], dtype=np.float64)
        self.idf_ = np.log((1.0 + n_docs) / (1.0 + dfs)) + 1.0

        matrix = np.zeros((n_docs, n_features), dtype=np.float64)
        for i, doc in enumerate(tokenized_docs):
            if not doc:
                continue
            tf_counts = Counter(doc)
            total_doc_words = len(doc)
            for term, count in tf_counts.items():
                if term in self.vocabulary_:
                    j = self.vocabulary_[term]
                    matrix[i, j] = (count / total_doc_words) * self.idf_[j]

        # L2 row normalization
        row_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        row_norms[row_norms == 0] = 1.0
        return matrix / row_norms


def kmeans_plus_plus_init(X: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """KMeans++ center initialization."""
    n_samples = X.shape[0]
    centers = np.empty((k, X.shape[1]), dtype=X.dtype)
    initial_idx = rng.integers(0, n_samples)
    centers[0] = X[initial_idx]

    closest_dist_sq = np.sum((X - centers[0]) ** 2, axis=1)

    for i in range(1, k):
        total_dist = closest_dist_sq.sum()
        probs = np.full(n_samples, 1.0 / n_samples) if total_dist == 0 else closest_dist_sq / total_dist
        next_idx = rng.choice(n_samples, p=probs)
        centers[i] = X[next_idx]
        new_dist_sq = np.sum((X - centers[i]) ** 2, axis=1)
        closest_dist_sq = np.minimum(closest_dist_sq, new_dist_sq)

    return centers


def run_kmeans(
    X: np.ndarray,
    k: int,
    max_iter: int = 100,
    tol: float = 1e-4,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Runs KMeans clustering returning labels and cluster centers."""
    rng = np.random.default_rng(seed)
    n_samples = X.shape[0]

    if k >= n_samples:
        return np.arange(n_samples, dtype=np.int32), X.copy()

    centers = kmeans_plus_plus_init(X, k, rng)
    labels = np.zeros(n_samples, dtype=np.int32)

    for _ in range(max_iter):
        dists = np.sum((X[:, np.newaxis, :] - centers[np.newaxis, :, :]) ** 2, axis=2)
        new_labels = np.argmin(dists, axis=1)

        if np.array_equal(new_labels, labels):
            break
        labels = new_labels

        new_centers = np.empty_like(centers)
        for cluster_idx in range(k):
            members = X[labels == cluster_idx]
            if len(members) > 0:
                mean_center = members.mean(axis=0)
                norm = np.linalg.norm(mean_center)
                new_centers[cluster_idx] = mean_center / norm if norm > 0 else mean_center
            else:
                new_centers[cluster_idx] = X[rng.integers(0, n_samples)]

        if np.linalg.norm(new_centers - centers) < tol:
            centers = new_centers
            break
        centers = new_centers

    return labels, centers


def compute_silhouette_score(X: np.ndarray, labels: np.ndarray) -> float:
    """Computes mean Silhouette score across all samples."""
    n_samples = X.shape[0]
    unique_labels = np.unique(labels)
    n_clusters = len(unique_labels)

    if n_clusters <= 1 or n_clusters >= n_samples:
        return 0.0

    diff = X[:, np.newaxis, :] - X[np.newaxis, :, :]
    dist_matrix = np.sqrt(np.sum(diff ** 2, axis=2))

    silhouettes = np.zeros(n_samples, dtype=np.float64)

    for i in range(n_samples):
        own_cluster = labels[i]
        own_members = np.where(labels == own_cluster)[0]

        if len(own_members) <= 1:
            silhouettes[i] = 0.0
            continue

        a_i = np.sum(dist_matrix[i, own_members]) / (len(own_members) - 1)

        b_i = float("inf")
        for other_cluster in unique_labels:
            if other_cluster == own_cluster:
                continue
            other_members = np.where(labels == other_cluster)[0]
            if len(other_members) == 0:
                continue
            mean_dist = np.mean(dist_matrix[i, other_members])
            if mean_dist < b_i:
                b_i = mean_dist

        denom = max(a_i, b_i)
        silhouettes[i] = (b_i - a_i) / denom if denom > 0 else 0.0

    return float(np.mean(silhouettes))


def cluster_content_interests(
    posts: List[Dict[str, Any]],
    k_range: range = range(3, 9),
    min_df: int = 1,
) -> ClusteringResult:
    """Clusters watched and saved posts based on caption and hashtag texts

    using pure NumPy TF-IDF, KMeans++, and chooses best k via Silhouette Score.
    """
    if not posts:
        return ClusteringResult(
            best_k=0,
            silhouette_score=0.0,
            clusters=[],
            total_documents=0,
        )

    tokenized_docs: List[List[str]] = []
    creators: List[Optional[str]] = []

    for post in posts:
        caption = post.get("caption") or ""
        hashtags = post.get("hashtags") or ""
        combined = f"{caption} {hashtags}"
        tokens = clean_text_tr(combined)
        tokenized_docs.append(tokens)
        creators.append(post.get("owner_username"))

    total_docs = len(tokenized_docs)
    vectorizer = PureTfidfVectorizer(min_df=min_df)
    X = vectorizer.fit_transform(tokenized_docs)

    if X.shape[1] == 0 or total_docs < 2:
        return ClusteringResult(
            best_k=1,
            silhouette_score=0.0,
            clusters=[
                ClusterInfo(
                    cluster_id=0,
                    size=total_docs,
                    top_terms=[],
                    top_creators=Counter(filter(None, creators)).most_common(5),
                )
            ],
            total_documents=total_docs,
        )

    max_k = min(max(k_range), total_docs - 1)
    min_k = min(min(k_range), max_k)
    if min_k > max_k or max_k < 2:
        best_k = min(total_docs, 2)
        labels, centers = run_kmeans(X, best_k)
        best_silhouette = compute_silhouette_score(X, labels)
    else:
        candidates = list(range(min_k, max_k + 1))
        best_k = candidates[0]
        best_silhouette = -1.0
        best_labels = None
        best_centers = None

        for k in candidates:
            labels, centers = run_kmeans(X, k)
            score = compute_silhouette_score(X, labels)
            if score > best_silhouette or best_labels is None:
                best_silhouette = score
                best_k = k
                best_labels = labels
                best_centers = centers

        labels = best_labels
        centers = best_centers

    clusters: List[ClusterInfo] = []
    feature_names = vectorizer.feature_names_

    for cluster_idx in range(best_k):
        member_indices = np.where(labels == cluster_idx)[0]
        size = len(member_indices)

        if len(feature_names) > 0 and cluster_idx < len(centers):
            center_weights = centers[cluster_idx]
            top_term_indices = np.argsort(center_weights)[::-1][:6]
            top_terms = [
                (feature_names[idx], round(float(center_weights[idx]), 4))
                for idx in top_term_indices
                if center_weights[idx] > 0
            ]
        else:
            top_terms = []

        cluster_creators = [creators[idx] for idx in member_indices if creators[idx]]
        top_creators = Counter(cluster_creators).most_common(5)

        clusters.append(
            ClusterInfo(
                cluster_id=cluster_idx,
                size=size,
                top_terms=top_terms,
                top_creators=top_creators,
            )
        )

    return ClusteringResult(
        best_k=best_k,
        silhouette_score=round(float(best_silhouette), 4),
        clusters=clusters,
        total_documents=total_docs,
    )


def compute_content_clusters(conn: sqlite3.Connection, k_clusters: int = 4) -> List[Dict[str, Any]]:
    """Compatibility wrapper for database content clustering."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT caption, hashtags, owner_username 
        FROM videos_watched 
        WHERE caption IS NOT NULL OR hashtags IS NOT NULL
        UNION ALL
        SELECT caption, hashtags, owner_username 
        FROM saved_posts 
        WHERE caption IS NOT NULL OR hashtags IS NOT NULL
        """
    )
    rows = cur.fetchall()

    if not rows or len(rows) < 4:
        return []

    posts = [
        {"caption": r[0], "hashtags": r[1], "owner_username": r[2]}
        for r in rows
    ]
    clustering = cluster_content_interests(posts, k_range=range(k_clusters, k_clusters + 1))

    output = []
    for c in clustering.clusters:
        top_term_names = [t[0] for t in c.top_terms]
        name = " / ".join(top_term_names[:2]).title() if top_term_names else f"Küme {c.cluster_id + 1}"
        output.append({
            "cluster_id": c.cluster_id,
            "name": name,
            "document_count": c.size,
            "top_terms": top_term_names,
            "top_creators": [u[0] for u in c.top_creators],
        })

    output.sort(key=lambda x: x["document_count"], reverse=True)
    return output


# ---------------------------------------------------------------------------
# 4. GDPR UNFORGOTTEN AUDITOR
# ---------------------------------------------------------------------------

@dataclass
class UnforgottenMatch:
    deleted_item: str
    matched_ad_target: str
    similarity_score: float  # 0.0 - 1.0
    match_type: str  # "exact", "token_overlap", "substring", "jaccard"


@dataclass
class GDPRUnforgottenReport:
    total_deleted_audited: int
    total_ad_targets_audited: int
    unforgotten_matches: List[UnforgottenMatch]
    match_count: int
    privacy_risk_level: str  # "Düşük", "Orta", "Yüksek", "Kritik"
    compliance_score: float  # 0-100 (100 = perfectly forgotten / zero leaks)


def compute_string_similarity(s1: str, s2: str) -> Tuple[float, str]:
    """Computes normalized text match similarity between a deleted term and an ad topic."""
    t1 = s1.strip().lower()
    t2 = s2.strip().lower()

    if not t1 or not t2:
        return 0.0, "none"

    if t1 == t2:
        return 1.0, "exact"

    if len(t1) >= 4 and t1 in t2:
        ratio = len(t1) / len(t2)
        return min(0.95, 0.70 + 0.25 * ratio), "substring"
    if len(t2) >= 4 and t2 in t1:
        ratio = len(t2) / len(t1)
        return min(0.95, 0.70 + 0.25 * ratio), "substring"

    tokens1 = set(clean_text_tr(t1))
    tokens2 = set(clean_text_tr(t2))

    if tokens1 and tokens2:
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        jaccard = len(intersection) / len(union)
        if len(intersection) > 0:
            if tokens1.issubset(tokens2) or tokens2.issubset(tokens1):
                return max(jaccard, 0.80), "token_overlap"
            return jaccard, "jaccard"

    return 0.0, "none"


def audit_unforgotten_interests(
    deleted_items: List[Any],
    ad_targets: List[Any],
    threshold: float = 0.5,
) -> GDPRUnforgottenReport:
    """Audits deleted history (searches, deleted posts, cleared likes) against

    retained ad interest profiles and advertiser targeting lists.
    Flags 'unforgotten' trails where supposedly deleted data continues to drive ads.
    """
    def extract_term(item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            return (
                item.get("query")
                or item.get("search_query")
                or item.get("title")
                or item.get("caption")
                or item.get("name")
                or ""
            )
        return str(item)

    clean_deleted = [extract_term(x) for x in deleted_items if extract_term(x)]
    clean_ads = [extract_term(x) for x in ad_targets if extract_term(x)]

    matches: List[UnforgottenMatch] = []

    for d_item in clean_deleted:
        for ad_item in clean_ads:
            score, m_type = compute_string_similarity(d_item, ad_item)
            if score >= threshold:
                matches.append(
                    UnforgottenMatch(
                        deleted_item=d_item,
                        matched_ad_target=ad_item,
                        similarity_score=round(score, 3),
                        match_type=m_type,
                    )
                )

    matches.sort(key=lambda x: x.similarity_score, reverse=True)
    match_count = len(matches)

    leak_penalty = min(100.0, match_count * 15.0)
    compliance_score = round(max(0.0, 100.0 - leak_penalty), 1)

    if match_count == 0:
        risk_level = "Düşük"
    elif match_count <= 2:
        risk_level = "Orta"
    elif match_count <= 5:
        risk_level = "Yüksek"
    else:
        risk_level = "Kritik"

    return GDPRUnforgottenReport(
        total_deleted_audited=len(clean_deleted),
        total_ad_targets_audited=len(clean_ads),
        unforgotten_matches=matches,
        match_count=match_count,
        privacy_risk_level=risk_level,
        compliance_score=compliance_score,
    )
