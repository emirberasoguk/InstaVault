import argparse
from pathlib import Path
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from instavault.db import DEFAULT_DB_PATH, init_db
from instavault.scanner import scan_and_ingest

console = Console()


def cmd_scan(args: argparse.Namespace) -> None:
    source_dir = Path(args.input).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve() if args.db else DEFAULT_DB_PATH

    console.print(f"[bold cyan]🔍 InstaVault Ingest Başlatılıyor...[/bold cyan]")
    console.print(f"Kaynak Dizin: [yellow]{source_dir}[/yellow]")
    console.print(f"Veritabanı:   [green]{db_path}[/green]\n")

    if not source_dir.exists():
        console.print(f"[bold red]Hata:[/bold red] Kaynak dizin bulunamadı: {source_dir}")
        sys.exit(1)

    conn = init_db(db_path)
    with console.status("[bold green]Arşivler taranıyor ve parse ediliyor...[/bold green]"):
        summary = scan_and_ingest(conn, source_dir)

    table = Table(title="📊 Tarama ve Vault Aktarım Özeti", show_header=True, header_style="bold magenta")
    table.add_column("Metrik", style="dim", width=30)
    table.add_column("Değer", justify="right")

    table.add_row("Toplam İncelenen HTML Dosyası", str(summary.total_files_scanned))
    table.add_row("Yeni İşlenen Arşiv Dosyası", f"[green]{summary.new_files_ingested}[/green]")
    table.add_row("Atlanan (Zaten Kayıtlı / Hash)", f"[yellow]{summary.files_skipped_duplicate}[/yellow]")
    table.add_section()
    table.add_row("İzlenen Videolar (Reels/Video)", str(summary.records_inserted.get("videos_watched", 0)))
    table.add_row("Görüntülenen Gönderiler (Posts)", str(summary.records_inserted.get("posts_viewed", 0)))
    table.add_row("Kaydedilen İçerikler (Saved)", str(summary.records_inserted.get("saved_posts", 0)))
    table.add_row("Takipçiler (Followers)", str(summary.records_inserted.get("followers", 0)))
    table.add_row("Takip Edilenler (Following)", str(summary.records_inserted.get("following", 0)))
    table.add_row("Reklam Verenler (Advertisers)", str(summary.records_inserted.get("advertisers", 0)))
    table.add_row("Meta Dışı Etkinlikler (Off-Meta)", str(summary.records_inserted.get("off_meta_activity", 0)))
    table.add_row("Son Aramalar (Searches)", str(summary.records_inserted.get("recent_searches", 0)))
    table.add_row("Beğenilen Gönderiler (Liked Posts)", str(summary.records_inserted.get("liked_posts", 0)))
    table.add_row("Hikaye Beğenileri (Story Likes)", str(summary.records_inserted.get("story_likes", 0)))
    table.add_row("Silinen İçerikler (Deleted Content)", str(summary.records_inserted.get("deleted_content", 0)))

    console.print(table)


def cmd_stats(args: argparse.Namespace) -> None:
    db_path = Path(args.db).expanduser().resolve() if args.db else DEFAULT_DB_PATH
    if not db_path.exists():
        console.print(f"[bold red]Hata:[/bold red] Veritabanı bulunamadı: {db_path}. Önce 'scan' çalıştırın.")
        sys.exit(1)

    conn = init_db(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*), MIN(date_range_start), MAX(date_range_end) FROM exports")
    exp_count, min_date, max_date = cur.fetchone()

    cur.execute("SELECT COUNT(*) FROM videos_watched")
    video_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM posts_viewed")
    post_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM saved_posts")
    saved_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT username) FROM social_connections WHERE connection_type = 'follower'")
    follower_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT username) FROM social_connections WHERE connection_type = 'following'")
    following_count = cur.fetchone()[0]

    summary_panel = f"""[bold]Toplam Arşiv Dosyası:[/bold] {exp_count}
[bold]Kapsanan Tarih Aralığı:[/bold] {min_date or 'N/A'} ➔ {max_date or 'N/A'}
[bold]İzlenen Videolar:[/bold] {video_count:,}
[bold]Görüntülenen Gönderiler:[/bold] {post_count:,}
[bold]Kaydedilen Gönderiler:[/bold] {saved_count:,}
[bold]Takipçi Havuzu:[/bold] {follower_count:,} tekil hesap
[bold]Takip Edilen Havuzu:[/bold] {following_count:,} tekil hesap"""

    console.print(Panel(summary_panel, title="🏛️ InstaVault İstatistikleri", border_style="cyan"))

    # Top watched creators
    cur.execute("""
        SELECT owner_username, owner_name, COUNT(*) as cnt 
        FROM videos_watched 
        WHERE owner_username IS NOT NULL 
        GROUP BY owner_username 
        ORDER BY cnt DESC 
        LIMIT 5
    """)
    top_creators = cur.fetchall()
    if top_creators:
        table = Table(title="🔥 En Çok İzlenen 5 İçerik Üreticisi", show_header=True, header_style="bold green")
        table.add_column("Kullanıcı Adı", style="cyan")
        table.add_column("İsim", style="dim")
        table.add_column("İzleme Sayısı", justify="right")
        for row in top_creators:
            table.add_row(row["owner_username"], row["owner_name"] or "-", str(row["cnt"]))
        console.print(table)


def cmd_social(args: argparse.Namespace) -> None:
    db_path = Path(args.db).expanduser().resolve() if args.db else DEFAULT_DB_PATH
    if not db_path.exists():
        console.print(f"[bold red]Hata:[/bold red] Veritabanı bulunamadı: {db_path}.")
        sys.exit(1)

    conn = init_db(db_path)
    cur = conn.cursor()

    # Non-reciprocal: Following but not following back
    cur.execute("""
        SELECT DISTINCT f1.username, f1.profile_url
        FROM social_connections f1
        WHERE f1.connection_type = 'following'
        AND f1.username NOT IN (
            SELECT f2.username FROM social_connections f2 WHERE f2.connection_type = 'follower'
        )
        ORDER BY f1.username ASC
    """)
    not_following_back = cur.fetchall()

    table = Table(
        title=f"⚠️ Geri Takip Etmeyen Hesaplar (Karşılıksız Takipler: {len(not_following_back)})",
        show_header=True,
        header_style="bold red"
    )
    table.add_column("Kullanıcı Adı", style="yellow")
    table.add_column("Profil Bağlantısı", style="dim")

    for r in not_following_back[: args.limit]:
        table.add_row(r["username"], r["profile_url"] or "-")

    console.print(table)
    if len(not_following_back) > args.limit:
        console.print(f"[dim]... ve {len(not_following_back) - args.limit} hesap daha (hepsini görmek için --limit parametresi verin)[/dim]")


def cmd_tui(args: argparse.Namespace) -> None:
    from instavault.tui import run_tui

    run_tui(db_path=args.db, watch=getattr(args, "watch", False))


def cmd_report(args: argparse.Namespace) -> None:
    from instavault.report import generate_report

    output_path = Path(args.output).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve() if args.db else None

    console.print("[bold cyan]📊 InstaVault HTML Raporu Üretiliyor...[/bold cyan]")
    out = generate_report(db_path=db_path, output_path=output_path)
    console.print(f"[bold green]✔ Rapor başarıyla oluşturuldu:[/bold green] [yellow]{out}[/yellow]")
    console.print("[dim]Tarayıcınızda açıp Liquid Glass görselleştirmelerini inceleyebilirsiniz.[/dim]")


def cmd_serve(args: argparse.Namespace) -> None:
    from instavault.web import run_server

    db_path = Path(args.db).expanduser().resolve() if args.db else None
    run_server(db_path=db_path, host=args.bind, port=args.port)


def cmd_systemd(args: argparse.Namespace) -> None:
    from instavault.systemd import install_systemd_units, uninstall_systemd_units

    if args.install:
        units = install_systemd_units(
            scan_input=args.input,
            on_calendar=args.calendar,
        )
        console.print("[bold green]✔ InstaVault systemd servis ve timer dosyaları başarıyla kuruldu:[/bold green]")
        for kind, path in units.items():
            console.print(f"  • {kind}: [cyan]{path}[/cyan]")
        console.print("\n[dim]Timer'ı etkinleştirmek için: systemctl --user enable --now instavault.timer[/dim]")
    elif args.uninstall:
        res = uninstall_systemd_units()
        if res:
            console.print("[bold yellow]✔ InstaVault systemd servis ve timer dosyaları kaldırıldı.[/bold yellow]")
        else:
            console.print("[dim]Kaldırılacak systemd dosyası bulunamadı.[/dim]")
    else:
        console.print("[yellow]Bilgi:[/yellow] Kullanım: [bold]instavault systemd --install[/bold] veya [bold]--uninstall[/bold]")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="instavault",
        description="Yerel Instagram Veri Kasası ve Analitik CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Komutlar")

    # scan
    p_scan = subparsers.add_parser("scan", help="Instagram arşiv klasörlerini tara ve yerel veritabanına aktar")
    p_scan.add_argument("--input", "-i", default="~/Desktop/İnstagram Ham Veri", help="Instagram ham veri ana klasörü")
    p_scan.add_argument("--db", "-d", default=None, help="SQLite veritabanı dosya yolu")
    p_scan.set_defaults(func=cmd_scan)

    # stats
    p_stats = subparsers.add_parser("stats", help="Yerel veri kasası istatistiklerini görüntüle")
    p_stats.add_argument("--db", "-d", default=None, help="SQLite veritabanı dosya yolu")
    p_stats.set_defaults(func=cmd_stats)

    # social
    p_social = subparsers.add_parser("social", help="Takipçi/takip edilen ve karşılıksız takip analizleri")
    p_social.add_argument("--db", "-d", default=None, help="SQLite veritabanı dosya yolu")
    p_social.add_argument("--limit", "-l", type=int, default=25, help="Listelenecek azami hesap sayısı")
    p_social.set_defaults(func=cmd_social)

    # tui
    p_tui = subparsers.add_parser("tui", help="Terminal kullanıcı arayüzü ve modern analitik paneli")
    p_tui.add_argument("--db", "-d", default=None, help="SQLite veritabanı dosya yolu")
    p_tui.add_argument("--watch", "-w", action="store_true", help="Canlı yenileme modu (Live refresh)")
    p_tui.set_defaults(func=cmd_tui)

    # report
    p_report = subparsers.add_parser("report", help="Liquid Glass analitik HTML raporu üret")
    p_report.add_argument("-o", "--output", default="report.html", help="Çıktı HTML dosyası (varsayılan: report.html)")
    p_report.add_argument("--db", "-d", default=None, help="SQLite veritabanı dosya yolu")
    p_report.set_defaults(func=cmd_report)

    # serve
    p_serve = subparsers.add_parser("serve", help="Yerel web sunucusunu ve Liquid Glass arayüzünü başlat")
    p_serve.add_argument("--bind", default="127.0.0.1", help="Dinlenecek IP adresi (Sadece 127.0.0.1)")
    p_serve.add_argument("--port", "-p", type=int, default=4173, help="Dinlenecek port (varsayılan: 4173)")
    p_serve.add_argument("--db", "-d", default=None, help="SQLite veritabanı dosya yolu")
    p_serve.set_defaults(func=cmd_serve)

    # systemd
    p_systemd = subparsers.add_parser("systemd", help="systemd user servisi ve timer kurulumu/yönetimi")
    p_systemd.add_argument("--install", action="store_true", help="~/.config/systemd/user/ altına servis ve timer kur")
    p_systemd.add_argument("--uninstall", action="store_true", help="systemd servis ve timer dosyalarını kaldır")
    p_systemd.add_argument("--input", "-i", default=None, help="Özel Instagram ham veri klasörü")
    p_systemd.add_argument("--calendar", default="daily", help="Timer periyodu (varsayılan: daily)")
    p_systemd.set_defaults(func=cmd_systemd)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
