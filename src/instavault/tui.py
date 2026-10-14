"""InstaVault Terminal UI (TUI) Modülü.

Rich kütüphanesi (Layout, Panel, Table, Live, Bar) ile yerel Instagram
veri kasası için modern, hafif ve estetik bir gösterge paneli sunar.
"""

from collections import Counter
from datetime import datetime
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from rich.align import Align
from rich.bar import Bar
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from instavault.db import DEFAULT_DB_PATH, init_db

console = Console()


def extract_top_interests(conn: sqlite3.Connection, limit: int = 5) -> List[Tuple[str, int]]:
    """İzlenen ve görüntülenen içeriklerdeki etiketlerden en popüler ilgi alanlarını çıkarır."""
    cur = conn.cursor()
    cur.execute("""
        SELECT hashtags FROM videos_watched WHERE hashtags IS NOT NULL AND hashtags != ''
        UNION ALL
        SELECT hashtags FROM posts_viewed WHERE hashtags IS NOT NULL AND hashtags != ''
    """)
    counter: Counter[str] = Counter()
    stopwords = {
        "reklam", "fyp", "kesfet", "keşfet", "viral", "instagram", "explore",
        "video", "post", "reels", "reel", "story", "stories", "feed",
    }
    for row in cur.fetchall():
        raw = row[0]
        if not raw:
            continue
        parts = raw.split(",")
        for part in parts:
            clean = part.strip().lower()
            if clean.startswith("name"):
                clean = clean[4:]
            if len(clean) >= 3 and clean not in stopwords:
                counter[clean] += 1
    return counter.most_common(limit)


def load_tui_data(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Veritabanından TUI için gerekli tüm metrikleri ve özetleri çeker."""
    cur = conn.cursor()

    # Exports
    cur.execute("SELECT COUNT(*), MAX(ingested_at), MIN(date_range_start), MAX(date_range_end) FROM exports")
    exp_count, max_ingest, date_start, date_end = cur.fetchone()
    exp_count = exp_count or 0

    # Videos & Posts
    cur.execute("SELECT COUNT(*) FROM videos_watched")
    video_count = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM posts_viewed")
    post_count = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM saved_posts")
    saved_count = cur.fetchone()[0] or 0

    total_consumption = video_count + post_count

    # Social connections
    cur.execute("SELECT COUNT(DISTINCT username) FROM social_connections WHERE connection_type = 'follower'")
    follower_count = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(DISTINCT username) FROM social_connections WHERE connection_type = 'following'")
    following_count = cur.fetchone()[0] or 0

    ratio = (follower_count / following_count) if following_count > 0 else 0.0

    # Top creators
    cur.execute("""
        SELECT owner_username, owner_name, COUNT(*) as cnt
        FROM videos_watched
        WHERE owner_username IS NOT NULL AND owner_username != ''
        GROUP BY owner_username
        ORDER BY cnt DESC
        LIMIT 5
    """)
    top_creators = [(r["owner_username"], r["owner_name"] or "", r["cnt"]) for r in cur.fetchall()]

    # Top interests
    top_interests = extract_top_interests(conn, limit=5)

    # Unfollowers
    cur.execute("""
        SELECT DISTINCT f1.username, f1.profile_url
        FROM social_connections f1
        WHERE f1.connection_type = 'following'
        AND f1.username NOT IN (
            SELECT f2.username FROM social_connections f2 WHERE f2.connection_type = 'follower'
        )
        ORDER BY f1.username ASC
    """)
    unfollowers = [(r["username"], r["profile_url"] or "") for r in cur.fetchall()]

    # Dijital Yorgunluk Hesabı
    days = 1
    if date_start and date_end:
        try:
            d_start = datetime.fromisoformat(date_start.replace("Z", "+00:00"))
            d_end = datetime.fromisoformat(date_end.replace("Z", "+00:00"))
            days = max(1, (d_end - d_start).days)
        except Exception:
            days = 30
    elif total_consumption > 0:
        days = 30

    daily_avg = total_consumption / days if days > 0 else 0.0
    # 0 - 25: Düşük (%15-%40), 25 - 60: Orta (%40-%70), 60+: Yüksek (%70-%100)
    fatigue_pct = min(100.0, max(5.0, (daily_avg / 85.0) * 100.0)) if total_consumption > 0 else 0.0

    if fatigue_pct >= 70.0:
        fatigue_status = "YÜKSEK RİSK"
        fatigue_color = "red"
        fatigue_desc = "Aşırı dopamin yükü / tüketim yoğun"
    elif fatigue_pct >= 40.0:
        fatigue_status = "ORTA SEVİYE"
        fatigue_color = "yellow"
        fatigue_desc = "Dengeli ancak takip edilmeli"
    else:
        fatigue_status = "DÜŞÜK / DENGELİ"
        fatigue_color = "green"
        fatigue_desc = "Sağlıklı dijital tüketim profili"

    return {
        "export_count": exp_count,
        "last_updated": max_ingest or "Henüz veri yok",
        "date_start": date_start[:10] if date_start else "N/A",
        "date_end": date_end[:10] if date_end else "N/A",
        "video_count": video_count,
        "post_count": post_count,
        "total_consumption": total_consumption,
        "saved_count": saved_count,
        "follower_count": follower_count,
        "following_count": following_count,
        "ratio": ratio,
        "top_creators": top_creators,
        "top_interests": top_interests,
        "unfollowers": unfollowers,
        "unfollowers_count": len(unfollowers),
        "daily_avg": daily_avg,
        "fatigue_pct": fatigue_pct,
        "fatigue_status": fatigue_status,
        "fatigue_color": fatigue_color,
        "fatigue_desc": fatigue_desc,
    }


def build_header_panel(data: Dict[str, Any]) -> Panel:
    """Header paneli: InstaVault logosu, veri kasanın son güncellenme zamanı ve toplam arşiv sayısı."""
    header_table = Table.grid(expand=True)
    header_table.add_column("brand", justify="left")
    header_table.add_column("stats", justify="right")

    brand_line1 = "[bold cyan]⚡ INSTAVAULT[/bold cyan] [bold white]│ Yerel Veri Kasası[/bold white]"
    brand_line2 = f"[dim]Arşiv:[/dim] [green]{data['export_count']} Dosya[/green] [dim]• SQLite WAL[/dim]"

    stats_line1 = f"[dim]Son Güncelleme:[/dim] [yellow]{data['last_updated']}[/yellow]"
    stats_line2 = f"[dim]Aralık:[/dim] [cyan]{data['date_start']} / {data['date_end']}[/cyan]"

    header_table.add_row(brand_line1, stats_line1)
    header_table.add_row(brand_line2, stats_line2)
    return Panel(header_table, border_style="cyan", padding=(0, 1))


def build_metrics_panel(data: Dict[str, Any]) -> Panel:
    """Sol panel: Metrik paneli (Toplam izleme, kaydetme, takipçi/takip edilen oranları, dijital yorgunluk ibresi)."""
    grid = Table.grid(padding=(0, 1), expand=True)
    grid.add_column("icon", width=3)
    grid.add_column("label", style="bold white")
    grid.add_column("value", justify="right")

    grid.add_row("🎬", "İzlenen Videolar", f"[bold cyan]{data['video_count']:,}[/bold cyan]")
    grid.add_row("📸", "Görüntülenen Gönderiler", f"[bold cyan]{data['post_count']:,}[/bold cyan]")
    grid.add_row("👁️", "Toplam Tüketim", f"[bold bright_white]{data['total_consumption']:,}[/bold bright_white]")
    grid.add_row("🔖", "Kaydedilen Gönderiler", f"[bold green]{data['saved_count']:,}[/bold green]")

    save_rate = (data['saved_count'] / data['total_consumption'] * 100) if data['total_consumption'] > 0 else 0.0
    grid.add_row("📌", "Kaydetme Oranı", f"[dim]%{save_rate:.1f}[/dim]")

    grid.add_row("", "", "")  # Boşluk
    grid.add_row("👥", "Takipçi Havuzu", f"[bold magenta]{data['follower_count']:,}[/bold magenta]")
    grid.add_row("👤", "Takip Edilenler", f"[bold magenta]{data['following_count']:,}[/bold magenta]")
    grid.add_row("⚖️", "Takipçi/Takip Oranı", f"[bold yellow]{data['ratio']:.2f}[/bold yellow]")

    fatigue_bar = Bar(
        size=100.0,
        begin=0.0,
        end=data["fatigue_pct"],
        width=22,
        color=data["fatigue_color"],
        bgcolor="grey23"
    )

    fatigue_text = (
        f"[{data['fatigue_color']}]● {data['fatigue_pct']:.0f}% {data['fatigue_status']}[/{data['fatigue_color']}]\n"
        f"[dim]{data['fatigue_desc']} (Günde ~{data['daily_avg']:.0f} içerik)[/dim]"
    )

    fatigue_group = Group(
        fatigue_text,
        fatigue_bar
    )

    fatigue_panel = Panel(
        fatigue_group,
        title="[bold]🧠 Dijital Yorgunluk İbresi[/bold]",
        border_style=data["fatigue_color"],
        padding=(0, 1)
    )

    body_group = Group(grid, fatigue_panel)
    return Panel(body_group, title="[bold blue]📊 Metrik Paneli[/bold blue]", border_style="blue", padding=(0, 1))


def build_top_creators_and_interests_panel(data: Dict[str, Any]) -> Panel:
    """Sağ üst panel: En çok izlenen içerik üreticileri ve ilgi alanları."""
    table = Table(expand=True, box=None, padding=(0, 1))
    table.add_column("🔥 İçerik Üreticisi", style="cyan", ratio=3)
    table.add_column("İzleme", justify="right", style="dim", ratio=1)
    table.add_column("🎯 İlgi Alanı / Tag", style="green", ratio=3)
    table.add_column("Adet", justify="right", style="dim", ratio=1)

    creators = data["top_creators"]
    interests = data["top_interests"]
    max_len = max(len(creators), len(interests), 1)

    if not creators and not interests:
        table.add_row("[dim]Veri bulunamadı[/dim]", "-", "[dim]Veri bulunamadı[/dim]", "-")
    else:
        for i in range(max_len):
            c_name = f"@{creators[i][0]}" if i < len(creators) else ""
            c_val = str(creators[i][2]) if i < len(creators) else ""
            t_name = f"#{interests[i][0]}" if i < len(interests) else ""
            t_val = str(interests[i][1]) if i < len(interests) else ""
            table.add_row(c_name, c_val, t_name, t_val)

    return Panel(
        table,
        title="[bold magenta]🔥 En Çok İzlenen Üreticiler & İlgi Alanları[/bold magenta]",
        border_style="magenta",
        padding=(0, 1)
    )


def build_unfollowers_panel(data: Dict[str, Any], limit: int = 6) -> Panel:
    """Sağ alt panel: Karşılıksız takipler (unfollowers) listesi."""
    unfollowers = data["unfollowers"]
    count = data["unfollowers_count"]

    table = Table(expand=True, box=None, padding=(0, 1))
    table.add_column("Kullanıcı Adı", style="yellow", ratio=2)
    table.add_column("Durum", style="red", ratio=2)
    table.add_column("Profil Bağlantısı", style="dim", ratio=3)

    if not unfollowers:
        table.add_row("[green]Karşılıksız takip bulunmuyor.[/green]", "-", "-")
    else:
        for user, url in unfollowers[:limit]:
            table.add_row(f"@{user}", "Geri Takip Etmiyor", url or f"instagram.com/{user}")

    elements: List[Any] = [table]
    if count > limit:
        elements.append(
            Text(f"... ve {count - limit} hesap daha geri takip etmiyor (CLI: instavault social)", style="dim italic")
        )

    title = f"[bold red]⚠️ Karşılıksız Takipler (Unfollowers: {count})[/bold red]"
    return Panel(Group(*elements), title=title, border_style="red", padding=(0, 1))


def build_dashboard(conn: sqlite3.Connection) -> Layout:
    """Bütün TUI panellerini birleştiren ana Layout nesnesini oluşturur."""
    data = load_tui_data(conn)

    layout = Layout()
    layout.split(
        Layout(name="header", size=4),
        Layout(name="body", ratio=1)
    )
    layout["body"].split_row(
        Layout(name="left", ratio=38),
        Layout(name="right", ratio=62)
    )
    layout["right"].split_column(
        Layout(name="top_right", ratio=1),
        Layout(name="bottom_right", ratio=1)
    )

    layout["header"].update(build_header_panel(data))
    layout["left"].update(build_metrics_panel(data))
    layout["top_right"].update(build_top_creators_and_interests_panel(data))
    layout["bottom_right"].update(build_unfollowers_panel(data))

    return layout


def run_tui(db_path: Optional[str | Path] = None, watch: bool = False) -> None:
    """TUI konsolunu başlatır ve görüntüler."""
    conn = init_db(db_path)
    layout = build_dashboard(conn)

    if watch:
        console.clear()
        with Live(layout, console=console, refresh_per_second=1, screen=True) as live:
            try:
                while True:
                    time.sleep(2)
                    live.update(build_dashboard(conn))
            except KeyboardInterrupt:
                pass
    else:
        console.print(layout)
