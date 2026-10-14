"""HTML Rapor Üretici Modülü (Liquid Glass UI & Standalone)."""

from html import escape
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from instavault.db import DEFAULT_DB_PATH, init_db


def fetch_report_data(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Veritabanından rapor için gerekli analitik verileri çeker."""
    cur = conn.cursor()

    # Genel sayaçlar
    cur.execute("SELECT COUNT(*), MIN(date_range_start), MAX(date_range_end) FROM exports")
    exp_row = cur.fetchone()
    export_count = exp_row[0] if exp_row else 0
    date_start = exp_row[1] if exp_row else None
    date_end = exp_row[2] if exp_row else None

    cur.execute("SELECT COUNT(*) FROM videos_watched")
    video_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM posts_viewed")
    post_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM saved_posts")
    saved_count = cur.fetchone()[0]

    # Sosyal metrikler
    cur.execute("SELECT COUNT(DISTINCT username) FROM social_connections WHERE connection_type = 'follower'")
    follower_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT username) FROM social_connections WHERE connection_type = 'following'")
    following_count = cur.fetchone()[0]

    # Karşılıklı takipler (Mutuals)
    cur.execute("""
        SELECT COUNT(DISTINCT f1.username)
        FROM social_connections f1
        INNER JOIN social_connections f2 ON f1.username = f2.username
        WHERE f1.connection_type = 'following' AND f2.connection_type = 'follower'
    """)
    mutual_count = cur.fetchone()[0]

    # Geri takip etmeyenler (Unfollowers)
    cur.execute("""
        SELECT DISTINCT f1.username, f1.profile_url
        FROM social_connections f1
        WHERE f1.connection_type = 'following'
        AND f1.username NOT IN (
            SELECT f2.username FROM social_connections f2 WHERE f2.connection_type = 'follower'
        )
        ORDER BY f1.username ASC
    """)
    unfollowers = [dict(r) for r in cur.fetchall()]

    # Hayranlar (Seni takip eden ama senin takip etmediğin)
    cur.execute("""
        SELECT COUNT(DISTINCT f1.username)
        FROM social_connections f1
        WHERE f1.connection_type = 'follower'
        AND f1.username NOT IN (
            SELECT f2.username FROM social_connections f2 WHERE f2.connection_type = 'following'
        )
    """)
    fans_count = cur.fetchone()[0]

    # Saatlik dağılım (00 - 23)
    cur.execute("""
        SELECT strftime('%H', watched_at) as hr, COUNT(*) as cnt
        FROM videos_watched
        WHERE watched_at IS NOT NULL AND watched_at != ''
        GROUP BY hr
        ORDER BY hr ASC
    """)
    hourly_rows = dict(cur.fetchall())
    hourly_distribution = [
        {"hour": f"{h:02d}", "count": hourly_rows.get(f"{h:02d}", 0)}
        for h in range(24)
    ]

    # Gece izleme (00:00 - 05:59)
    cur.execute("""
        SELECT COUNT(*) FROM videos_watched
        WHERE strftime('%H', watched_at) BETWEEN '00' AND '05'
    """)
    night_video_count = cur.fetchone()[0]
    night_ratio = (night_video_count / max(1, video_count)) * 100

    # En aktif saat
    peak_hour = max(hourly_distribution, key=lambda x: x["count"]) if hourly_distribution else {"hour": "00", "count": 0}

    # Günlük aktivite trendi (son 14 aktif gün)
    cur.execute("""
        SELECT substr(watched_at, 1, 10) as day, COUNT(*) as cnt
        FROM videos_watched
        WHERE watched_at IS NOT NULL AND watched_at != ''
        GROUP BY day
        ORDER BY day DESC
        LIMIT 14
    """)
    daily_trend = [dict(r) for r in cur.fetchall()]
    daily_trend.reverse()

    # En çok izlenen içerik üreticileri
    cur.execute("""
        SELECT owner_username, owner_name, COUNT(*) as count
        FROM videos_watched
        WHERE owner_username IS NOT NULL AND owner_username != ''
        GROUP BY owner_username
        ORDER BY count DESC
        LIMIT 15
    """)
    creators = [dict(r) for r in cur.fetchall()]

    # Tahmini harcanan izleme süresi (video başına ortalama 25 sn baz alınır)
    estimated_minutes = int((video_count * 25) / 60)
    estimated_hours = round(estimated_minutes / 60, 1)

    return {
        "export_count": export_count,
        "date_start": date_start or "N/A",
        "date_end": date_end or "N/A",
        "video_count": video_count,
        "post_count": post_count,
        "saved_count": saved_count,
        "follower_count": follower_count,
        "following_count": following_count,
        "mutual_count": mutual_count,
        "unfollower_count": len(unfollowers),
        "fans_count": fans_count,
        "unfollowers": unfollowers,
        "hourly_distribution": hourly_distribution,
        "night_video_count": night_video_count,
        "night_ratio": round(night_ratio, 1),
        "peak_hour": peak_hour,
        "daily_trend": daily_trend,
        "creators": creators,
        "estimated_minutes": estimated_minutes,
        "estimated_hours": estimated_hours,
    }


def render_hourly_svg(hourly_data: List[Dict[str, Any]]) -> str:
    """24 saatlik aktivite dağılımı için saf inline SVG grafiği üretir."""
    width = 760
    height = 200
    padding_x = 42
    padding_y = 28
    chart_w = width - (padding_x * 2)
    chart_h = height - (padding_y * 2)

    max_val = max([item["count"] for item in hourly_data] + [1])
    bar_width = chart_w / len(hourly_data)
    inner_bar_w = max(6.0, bar_width * 0.65)

    svg_parts = [
        f'<svg class="chart-svg" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        '  <defs>',
        '    <linearGradient id="barGradDay" x1="0" y1="0" x2="0" y2="1">',
        '      <stop offset="0%" stop-color="#818cf8"/>',
        '      <stop offset="100%" stop-color="#4f46e5" stop-opacity="0.6"/>',
        '    </linearGradient>',
        '    <linearGradient id="barGradNight" x1="0" y1="0" x2="0" y2="1">',
        '      <stop offset="0%" stop-color="#f43f5e"/>',
        '      <stop offset="100%" stop-color="#be123c" stop-opacity="0.65"/>',
        '    </linearGradient>',
        '    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">',
        '      <feGaussianBlur stdDeviation="3" result="blur"/>',
        '      <feComposite in="SourceGraphic" in2="blur" operator="over"/>',
        '    </filter>',
        '  </defs>',
    ]

    # Kılavuz çizgileri
    for step in [0.25, 0.5, 0.75, 1.0]:
        y_val = padding_y + chart_h - (chart_h * step)
        val_label = int(max_val * step)
        svg_parts.append(
            f'  <line x1="{padding_x}" y1="{y_val:.1f}" x2="{width - padding_x}" y2="{y_val:.1f}" '
            f'stroke="rgba(255,255,255,0.06)" stroke-dasharray="3 3"/>'
        )
        svg_parts.append(
            f'  <text x="{padding_x - 8}" y="{y_val + 3:.1f}" fill="rgba(255,255,255,0.35)" '
            f'font-size="9" text-anchor="end" font-family="monospace">{val_label}</text>'
        )

    # Barlar
    for i, item in enumerate(hourly_data):
        count = item["count"]
        hour_int = int(item["hour"])
        bar_h = (count / max_val) * chart_h if max_val > 0 else 0
        x_center = padding_x + (i * bar_width) + (bar_width / 2)
        x_bar = x_center - (inner_bar_w / 2)
        y_bar = padding_y + chart_h - bar_h

        is_night = hour_int < 6
        grad_id = "barGradNight" if is_night else "barGradDay"

        svg_parts.append(
            f'  <g class="chart-bar-group">'
            f'    <title>{item["hour"]}:00 - {count:,} video izlendi</title>'
            f'    <rect class="chart-bar" x="{x_bar:.1f}" y="{y_bar:.1f}" width="{inner_bar_w:.1f}" '
            f'height="{bar_h:.1f}" rx="3" fill="url(#{grad_id})"/>'
            f'    <text x="{x_center:.1f}" y="{height - 10}" fill="{"#f43f5e" if is_night else "rgba(255,255,255,0.4)"}" '
            f'font-size="9" text-anchor="middle" font-family="monospace">{item["hour"]}</text>'
            f'  </g>'
        )

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def render_html_report(data: Dict[str, Any]) -> str:
    """Liquid Glass ve Smooth Motion tasarım diliyle bağımsız HTML raporu üretir."""
    hourly_svg = render_hourly_svg(data["hourly_distribution"])

    # Creator rows HTML
    max_creator_cnt = max([c["count"] for c in data["creators"]] + [1])
    creator_rows_html = []
    for idx, c in enumerate(data["creators"], 1):
        pct = (c["count"] / max_creator_cnt) * 100
        uname = escape(c["owner_username"])
        name = escape(c["owner_name"] or "")
        count = c["count"]
        initials = (uname[:2] if len(uname) >= 2 else uname).upper()

        creator_rows_html.append(f"""
        <tr class="table-row">
            <td class="col-rank">#{idx}</td>
            <td class="col-creator">
                <div class="creator-cell">
                    <div class="creator-avatar">{initials}</div>
                    <div class="creator-meta">
                        <span class="creator-username">@{uname}</span>
                        {f'<span class="creator-name">{name}</span>' if name else ''}
                    </div>
                </div>
            </td>
            <td class="col-count">
                <span class="count-badge">{count:,}</span>
            </td>
            <td class="col-progress">
                <div class="progress-track">
                    <div class="progress-fill" style="width: {pct:.1f}%;"></div>
                </div>
            </td>
        </tr>
        """)

    # Fatigue evaluation
    night_ratio = data["night_ratio"]
    if night_ratio > 25:
        fatigue_status = "Yüksek Gece Maruziyeti"
        fatigue_badge_class = "badge-danger"
        fatigue_desc = "İzleme geçmişinizin 4'te 1'inden fazlası biyolojik uyku saatlerinde (00:00 - 06:00) gerçekleşti. Dijital yorgunluk ve mavi ışık yükü belirgin."
    elif night_ratio > 12:
        fatigue_status = "Dengeli / Orta Düzey"
        fatigue_badge_class = "badge-warning"
        fatigue_desc = "Gece izlemeleri belirli periyotlarda artış gösterse de genel akış gün içine dengelenmiş durumda."
    else:
        fatigue_status = "Sağlıklı Sirkadiyen Ritim"
        fatigue_badge_class = "badge-success"
        fatigue_desc = "İçerik tüketiminin neredeyse tamamı gündüz saatlerinde. Gece uyku periyodu korunmuş."

    html_template = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InstaVault // Analitik Raporu</title>
    <style>
        :root {{
            --bg-base: #060911;
            --bg-mesh-1: rgba(99, 102, 241, 0.12);
            --bg-mesh-2: rgba(236, 72, 153, 0.08);
            --bg-mesh-3: rgba(16, 185, 129, 0.06);
            --glass-bg: rgba(17, 24, 39, 0.55);
            --glass-bg-hover: rgba(24, 33, 53, 0.72);
            --glass-border: rgba(255, 255, 255, 0.08);
            --glass-border-specular: rgba(255, 255, 255, 0.16);
            --glass-shadow: 0 16px 40px -8px rgba(0, 0, 0, 0.65), inset 0 1px 0 0 rgba(255, 255, 255, 0.12);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-dim: #64748b;
            --accent-primary: #6366f1;
            --accent-glow: #818cf8;
            --accent-rose: #f43f5e;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --accent-cyan: #06b6d4;
            --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            --transition-smooth: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-base);
            background-image: 
                radial-gradient(at 0% 0%, var(--bg-mesh-1) 0px, transparent 50%),
                radial-gradient(at 100% 0%, var(--bg-mesh-2) 0px, transparent 50%),
                radial-gradient(at 50% 100%, var(--bg-mesh-3) 0px, transparent 60%);
            background-attachment: fixed;
            color: var(--text-main);
            font-family: var(--font-family);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            padding: 40px 24px;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        /* Header */
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 28px;
            border-bottom: 1px solid var(--glass-border);
            margin-bottom: 32px;
            flex-wrap: wrap;
            gap: 16px;
        }}

        .logo-wrap {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}

        .logo-icon {{
            width: 44px;
            height: 44px;
            border-radius: 12px;
            background: linear-gradient(135deg, #6366f1 0%, #ec4899 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 8px 20px rgba(99, 102, 241, 0.35);
        }}

        .header h1 {{
            font-size: 26px;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .header p {{
            font-size: 13px;
            color: var(--text-muted);
        }}

        .badge-tag {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(99, 102, 241, 0.15);
            border: 1px solid rgba(99, 102, 241, 0.3);
            color: var(--accent-glow);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }}

        /* Liquid Glass Card */
        .glass-card {{
            background: var(--glass-bg);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border: 1px solid var(--glass-border);
            border-top: 1px solid var(--glass-border-specular);
            border-radius: 20px;
            padding: 24px;
            box-shadow: var(--glass-shadow);
            transition: var(--transition-smooth);
            position: relative;
            overflow: hidden;
        }}

        .glass-card:hover {{
            background: var(--glass-bg-hover);
            transform: translateY(-2px);
            border-top-color: rgba(255, 255, 255, 0.28);
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}

        .card-title {{
            font-size: 16px;
            font-weight: 600;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .card-subtitle {{
            font-size: 12px;
            color: var(--text-dim);
            margin-top: 2px;
        }}

        /* Grid Layouts */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 28px;
        }}

        .stat-card {{
            padding: 20px;
        }}

        .stat-label {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-muted);
            font-weight: 600;
            margin-bottom: 8px;
        }}

        .stat-value {{
            font-size: 32px;
            font-weight: 700;
            letter-spacing: -1px;
            line-height: 1.1;
            color: #ffffff;
        }}

        .stat-meta {{
            font-size: 12px;
            color: var(--text-dim);
            margin-top: 8px;
        }}

        .main-split {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
            margin-bottom: 28px;
        }}

        @media (max-width: 960px) {{
            .main-split {{
                grid-template-columns: 1fr;
            }}
        }}

        /* Chart Section */
        .chart-svg {{
            width: 100%;
            height: auto;
            display: block;
        }}

        .chart-bar {{
            transition: var(--transition-smooth);
            cursor: pointer;
        }}

        .chart-bar-group:hover .chart-bar {{
            filter: brightness(1.3);
            transform: scaleY(1.03);
            transform-origin: bottom;
        }}

        .chart-legend {{
            display: flex;
            gap: 20px;
            align-items: center;
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 14px;
            justify-content: flex-end;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .legend-dot {{
            width: 10px;
            height: 10px;
            border-radius: 3px;
        }}

        /* Fatigue Card */
        .fatigue-meter {{
            text-align: center;
            padding: 16px 0;
        }}

        .fatigue-val {{
            font-size: 46px;
            font-weight: 800;
            letter-spacing: -1.5px;
            color: var(--accent-rose);
        }}

        .fatigue-subtext {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        .badge-pill {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            margin-top: 12px;
        }}

        .badge-danger {{
            background: rgba(244, 63, 94, 0.16);
            color: #fda4af;
            border: 1px solid rgba(244, 63, 94, 0.35);
        }}

        .badge-warning {{
            background: rgba(245, 158, 11, 0.16);
            color: #fde68a;
            border: 1px solid rgba(245, 158, 11, 0.35);
        }}

        .badge-success {{
            background: rgba(16, 185, 129, 0.16);
            color: #6ee7b7;
            border: 1px solid rgba(16, 185, 129, 0.35);
        }}

        .fatigue-metrics {{
            margin-top: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .f-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 14px;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 13px;
        }}

        .f-item-val {{
            font-weight: 600;
            color: var(--text-main);
        }}

        /* Social Ratio Bar */
        .social-breakdown {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .social-bar-track {{
            width: 100%;
            height: 10px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 9999px;
            overflow: hidden;
            display: flex;
        }}

        .social-bar-segment {{
            height: 100%;
            transition: var(--transition-smooth);
        }}

        /* Table */
        .table-responsive {{
            overflow-x: auto;
        }}

        .creators-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        .creators-table th {{
            text-align: left;
            padding: 12px 14px;
            color: var(--text-dim);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.6px;
            border-bottom: 1px solid var(--glass-border);
        }}

        .creators-table td {{
            padding: 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            vertical-align: middle;
        }}

        .table-row {{
            transition: var(--transition-smooth);
        }}

        .table-row:hover {{
            background: rgba(255, 255, 255, 0.03);
        }}

        .col-rank {{
            color: var(--text-dim);
            font-family: monospace;
            font-size: 12px;
            width: 50px;
        }}

        .creator-cell {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .creator-avatar {{
            width: 32px;
            height: 32px;
            border-radius: 10px;
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.3) 0%, rgba(236, 72, 153, 0.3) 100%);
            border: 1px solid rgba(255, 255, 255, 0.12);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 700;
            color: #ffffff;
        }}

        .creator-meta {{
            display: flex;
            flex-direction: column;
        }}

        .creator-username {{
            font-weight: 600;
            color: var(--text-main);
        }}

        .creator-name {{
            font-size: 11px;
            color: var(--text-dim);
        }}

        .count-badge {{
            display: inline-block;
            background: rgba(99, 102, 241, 0.14);
            color: var(--accent-glow);
            padding: 4px 10px;
            border-radius: 8px;
            font-weight: 600;
            font-family: monospace;
        }}

        .progress-track {{
            width: 100%;
            height: 6px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 9999px;
            overflow: hidden;
        }}

        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #6366f1 0%, #ec4899 100%);
            border-radius: 9999px;
        }}

        .footer {{
            text-align: center;
            padding: 32px 0 16px;
            color: var(--text-dim);
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div class="logo-wrap">
                <div class="logo-icon">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
                        <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
                        <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
                    </svg>
                </div>
                <div>
                    <h1>InstaVault Analitik Raporu</h1>
                    <p>Yerel Instagram Veri Kasası Arşiv İncelemesi ({data["date_start"]} ➔ {data["date_end"]})</p>
                </div>
            </div>
            <div>
                <span class="badge-tag">
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#10b981;"></span>
                    {data["export_count"]} Arşiv Dosyası İşlendi
                </span>
            </div>
        </header>

        <!-- KPI Grid -->
        <div class="stats-grid">
            <div class="glass-card stat-card">
                <div class="stat-label">İzlenen Videolar</div>
                <div class="stat-value">{data["video_count"]:,}</div>
                <div class="stat-meta">Reels ve video kayıtları</div>
            </div>
            <div class="glass-card stat-card">
                <div class="stat-label">Görüntülenen Gönderiler</div>
                <div class="stat-value">{data["post_count"]:,}</div>
                <div class="stat-meta">Akışta incelenen postlar</div>
            </div>
            <div class="glass-card stat-card">
                <div class="stat-label">Kaydedilen İçerikler</div>
                <div class="stat-value">{data["saved_count"]:,}</div>
                <div class="stat-meta">Kaydedilenler koleksiyonu</div>
            </div>
            <div class="glass-card stat-card">
                <div class="stat-label">Tahmini Ekran Süresi</div>
                <div class="stat-value">~{data["estimated_hours"]}h</div>
                <div class="stat-meta">{data["estimated_minutes"]:,} dakika video tüketimi</div>
            </div>
        </div>

        <!-- Charts Split -->
        <div class="main-split">
            <!-- Hourly Chart -->
            <div class="glass-card">
                <div class="card-header">
                    <div>
                        <div class="card-title">
                            <span>🕒 İzleme Dağılımı (24 Saatlik Spektrum)</span>
                        </div>
                        <div class="card-subtitle">Günün saatlerine göre video tüketim yoğunluğu</div>
                    </div>
                </div>
                {hourly_svg}
                <div class="chart-legend">
                    <div class="legend-item">
                        <div class="legend-dot" style="background: #f43f5e;"></div>
                        <span>Gece Biyolojik Saat (00:00 - 05:59)</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-dot" style="background: #818cf8;"></div>
                        <span>Gündüz / Akşam Saatleri</span>
                    </div>
                </div>
            </div>

            <!-- Digital Fatigue -->
            <div class="glass-card">
                <div class="card-header">
                    <div>
                        <div class="card-title">
                            <span>⚡ Dijital Yorgunluk Kartı</span>
                        </div>
                        <div class="card-subtitle">Gece maruziyeti ve ritim analizi</div>
                    </div>
                </div>
                <div class="fatigue-meter">
                    <div class="fatigue-val">%{data["night_ratio"]}</div>
                    <div class="fatigue-subtext">Gece Saatlerinde İzleme Oranı</div>
                    <div class="badge-pill {fatigue_badge_class}">{fatigue_status}</div>
                </div>
                <div class="fatigue-metrics">
                    <div class="f-item">
                        <span style="color:var(--text-muted);">Gece İzlenen Video:</span>
                        <span class="f-item-val" style="color:var(--accent-rose);">{data["night_video_count"]:,} adet</span>
                    </div>
                    <div class="f-item">
                        <span style="color:var(--text-muted);">En Yoğun Saat:</span>
                        <span class="f-item-val">{data["peak_hour"]["hour"]}:00 ({data["peak_hour"]["count"]:,} izleme)</span>
                    </div>
                    <div class="f-item">
                        <span style="color:var(--text-muted);">Durum Açıklaması:</span>
                        <span style="font-size:11px; text-align:right; max-width:60%; color:var(--text-dim);">{fatigue_desc}</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Social Comparison & Creators Split -->
        <div class="main-split">
            <!-- Creators Table -->
            <div class="glass-card">
                <div class="card-header">
                    <div>
                        <div class="card-title">
                            <span>🔥 En Çok İzlenen 15 İçerik Üreticisi</span>
                        </div>
                        <div class="card-subtitle">Algoritmada en çok vakit ayrılan profiller</div>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="creators-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Üretici</th>
                                <th style="text-align:right;">İzleme</th>
                                <th style="width:160px;">Oran</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(creator_rows_html)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Social Comparison Card -->
            <div class="glass-card">
                <div class="card-header">
                    <div>
                        <div class="card-title">
                            <span>👥 Takipçi vs Takip Edilen</span>
                        </div>
                        <div class="card-subtitle">Sosyal ağ karşılıklılık dengesi</div>
                    </div>
                </div>
                <div class="social-breakdown">
                    <div class="f-item">
                        <span style="color:var(--text-muted);">Takip Ettiklerin:</span>
                        <span class="f-item-val" style="color:var(--accent-cyan);">{data["following_count"]:,}</span>
                    </div>
                    <div class="f-item">
                        <span style="color:var(--text-muted);">Seni Takip Edenler:</span>
                        <span class="f-item-val" style="color:var(--accent-emerald);">{data["follower_count"]:,}</span>
                    </div>
                    <div class="f-item">
                        <span style="color:var(--text-muted);">Karşılıklı Takip (Mutual):</span>
                        <span class="f-item-val">{data["mutual_count"]:,}</span>
                    </div>
                    <div class="f-item" style="border-color: rgba(244, 63, 94, 0.2);">
                        <span style="color:#fda4af;">Geri Takip Etmeyenler:</span>
                        <span class="f-item-val" style="color:var(--accent-rose);">{data["unfollower_count"]:,}</span>
                    </div>
                    <div class="f-item">
                        <span style="color:var(--text-muted);">Seni Takip Eden Hayranlar:</span>
                        <span class="f-item-val" style="color:var(--accent-amber);">{data["fans_count"]:,}</span>
                    </div>

                    <div style="margin-top: 10px;">
                        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-dim); margin-bottom:6px;">
                            <span>Mutuals ({data["mutual_count"]})</span>
                            <span>Unfollowers ({data["unfollower_count"]})</span>
                        </div>
                        <div class="social-bar-track">
                            <div class="social-bar-segment" style="width: {(data['mutual_count'] / max(1, data['following_count'])) * 100:.1f}%; background: var(--accent-emerald);"></div>
                            <div class="social-bar-segment" style="width: {(data['unfollower_count'] / max(1, data['following_count'])) * 100:.1f}%; background: var(--accent-rose);"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <footer class="footer">
            <p>InstaVault &bull; Yerel ve Gizlilik Odaklı Instagram Veri Analitiği &bull; 100% Bağımsız Standalone Rapor</p>
        </footer>
    </div>
</body>
</html>
"""
    return html_template


def generate_report(db_path: Optional[str | Path] = None, output_path: str | Path = "report.html") -> Path:
    """Veritabanını okur ve bağımsız Liquid Glass HTML raporunu diske yazar."""
    target_db = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = init_db(target_db)
    data = fetch_report_data(conn)
    html_content = render_html_report(data)

    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_content, encoding="utf-8")
    return out
