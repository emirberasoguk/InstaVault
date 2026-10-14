"""Yerel Web Sunucusu ve REST API Modülü (Liquid Glass UI & Smooth Motion)."""

from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from instavault.db import DEFAULT_DB_PATH, init_db
from instavault.report import fetch_report_data, render_hourly_svg


def get_web_dashboard_html() -> str:
    """Liquid Glass ve Smooth Motion özelliklerine sahip interaktif dashboard HTML şablonu."""
    return """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InstaVault // Canlı Veri Kasası</title>
    <style>
        :root {
            --bg-base: #060911;
            --bg-mesh-1: rgba(99, 102, 241, 0.15);
            --bg-mesh-2: rgba(236, 72, 153, 0.10);
            --bg-mesh-3: rgba(16, 185, 129, 0.08);
            --glass-bg: rgba(17, 24, 39, 0.58);
            --glass-bg-hover: rgba(26, 36, 58, 0.75);
            --glass-border: rgba(255, 255, 255, 0.08);
            --glass-border-specular: rgba(255, 255, 255, 0.18);
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
            --transition-smooth: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
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
            padding: 32px 24px;
            min-height: 100vh;
        }

        .container {
            max-width: 1280px;
            margin: 0 auto;
        }

        /* Top Nav */
        .nav-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 24px;
            margin-bottom: 28px;
            border-radius: 20px;
            background: var(--glass-bg);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border: 1px solid var(--glass-border);
            border-top: 1px solid var(--glass-border-specular);
            box-shadow: var(--glass-shadow);
            flex-wrap: wrap;
            gap: 16px;
        }

        .brand-wrap {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-icon {
            width: 40px;
            height: 40px;
            border-radius: 12px;
            background: linear-gradient(135deg, #6366f1 0%, #ec4899 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 8px 20px rgba(99, 102, 241, 0.4);
        }

        .brand-title {
            font-size: 20px;
            font-weight: 700;
            letter-spacing: -0.4px;
            background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .nav-tabs {
            display: flex;
            gap: 8px;
            background: rgba(0, 0, 0, 0.25);
            padding: 4px;
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 8px 16px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition-smooth);
        }

        .tab-btn:hover {
            color: var(--text-main);
        }

        .tab-btn.active {
            background: rgba(99, 102, 241, 0.35);
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
            border: 1px solid rgba(99, 102, 241, 0.5);
        }

        .live-status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--accent-emerald);
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.25);
            padding: 6px 14px;
            border-radius: 9999px;
            font-weight: 600;
        }

        .live-pulse {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent-emerald);
            box-shadow: 0 0 10px var(--accent-emerald);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }

        /* Glass Cards */
        .glass-card {
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
        }

        .glass-card:hover {
            background: var(--glass-bg-hover);
            transform: translateY(-2px);
        }

        /* KPIs */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }

        .stat-label {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-muted);
            font-weight: 600;
            margin-bottom: 6px;
        }

        .stat-value {
            font-size: 32px;
            font-weight: 700;
            letter-spacing: -1px;
            color: #ffffff;
        }

        .stat-sub {
            font-size: 12px;
            color: var(--text-dim);
            margin-top: 6px;
        }

        /* Layout Grid */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }

        @media (max-width: 992px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
        }

        /* Section Title & Controls */
        .card-header-flex {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
            gap: 12px;
            flex-wrap: wrap;
        }

        .card-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Search Input */
        .search-box {
            position: relative;
            min-width: 240px;
        }

        .search-input {
            width: 100%;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 8px 14px 8px 34px;
            color: var(--text-main);
            font-size: 13px;
            outline: none;
            transition: var(--transition-smooth);
        }

        .search-input:focus {
            border-color: var(--accent-primary);
            box-shadow: 0 0 12px rgba(99, 102, 241, 0.25);
            background: rgba(0, 0, 0, 0.45);
        }

        .search-icon {
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-dim);
            pointer-events: none;
        }

        /* Tab Views */
        .tab-panel {
            display: none;
            opacity: 0;
            transform: translateY(6px);
            transition: var(--transition-smooth);
        }

        .tab-panel.active {
            display: block;
            opacity: 1;
            transform: translateY(0);
        }

        /* Lists & Tables */
        .unfollowers-scroll {
            max-height: 440px;
            overflow-y: auto;
            padding-right: 6px;
        }

        .unfollowers-scroll::-webkit-scrollbar {
            width: 6px;
        }

        .unfollowers-scroll::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.02);
            border-radius: 8px;
        }

        .unfollowers-scroll::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.12);
            border-radius: 8px;
        }

        .unfollower-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 14px;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            margin-bottom: 8px;
            transition: var(--transition-smooth);
        }

        .unfollower-row:hover {
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(244, 63, 94, 0.3);
            transform: translateX(3px);
        }

        .user-tag {
            font-weight: 600;
            color: #fca5a5;
            font-size: 13px;
        }

        .user-link-btn {
            font-size: 12px;
            color: var(--accent-glow);
            text-decoration: none;
            padding: 4px 10px;
            border-radius: 8px;
            background: rgba(99, 102, 241, 0.12);
            border: 1px solid rgba(99, 102, 241, 0.25);
            transition: var(--transition-smooth);
        }

        .user-link-btn:hover {
            background: rgba(99, 102, 241, 0.25);
            color: #ffffff;
        }

        /* SVG Chart */
        .chart-svg {
            width: 100%;
            height: auto;
            display: block;
        }

        .chart-bar-group:hover rect {
            filter: brightness(1.25);
        }

        /* Fatigue Box */
        .fatigue-card-inner {
            text-align: center;
            padding: 14px 0;
        }

        .fatigue-big {
            font-size: 44px;
            font-weight: 800;
            color: var(--accent-rose);
        }

        .fatigue-pill {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            background: rgba(244, 63, 94, 0.15);
            color: #fda4af;
            border: 1px solid rgba(244, 63, 94, 0.35);
            margin-top: 10px;
        }

        .info-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 14px;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.02);
            margin-top: 8px;
            font-size: 13px;
        }

        .empty-placeholder {
            text-align: center;
            padding: 40px 16px;
            color: var(--text-dim);
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Top Nav -->
        <nav class="nav-bar">
            <div class="brand-wrap">
                <div class="brand-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
                        <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
                        <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
                    </svg>
                </div>
                <div>
                    <span class="brand-title">InstaVault</span>
                    <span style="font-size: 11px; color: var(--text-dim); margin-left: 6px;">Live Vault Engine</span>
                </div>
            </div>

            <div class="nav-tabs">
                <button class="tab-btn active" onclick="switchTab('overview')">Genel Bakış</button>
                <button class="tab-btn" onclick="switchTab('unfollowers')">Unfollowers</button>
                <button class="tab-btn" onclick="switchTab('creators')">İçerik Üreticileri</button>
            </div>

            <div class="live-status">
                <span class="live-pulse"></span>
                <span>127.0.0.1:4173 &bull; Güvenli Yerel Ağ</span>
            </div>
        </nav>

        <!-- KPI Cards -->
        <div class="stats-grid">
            <div class="glass-card">
                <div class="stat-label">Toplam İzlenen Video</div>
                <div class="stat-value" id="kpi-videos">-</div>
                <div class="stat-sub">Reels ve video kayıtları</div>
            </div>
            <div class="glass-card">
                <div class="stat-label">Görüntülenen Gönderiler</div>
                <div class="stat-value" id="kpi-posts">-</div>
                <div class="stat-sub">Akış gönderi incelemeleri</div>
            </div>
            <div class="glass-card">
                <div class="stat-label">Kaydedilen İçerikler</div>
                <div class="stat-value" id="kpi-saved">-</div>
                <div class="stat-sub">Kaydedilenler arşivi</div>
            </div>
            <div class="glass-card">
                <div class="stat-label">Takipçi / Takip Edilen</div>
                <div class="stat-value" id="kpi-social">- / -</div>
                <div class="stat-sub" id="kpi-unfollowers-sub">- karşılıksız takip</div>
            </div>
        </div>

        <!-- TAB 1: OVERVIEW -->
        <div id="tab-overview" class="tab-panel active">
            <div class="dashboard-grid">
                <!-- Hourly Chart Card -->
                <div class="glass-card">
                    <div class="card-header-flex">
                        <div class="card-title">
                            <span>🕒 İzleme Dağılımı (24 Saatlik Spektrum)</span>
                        </div>
                        <span style="font-size: 12px; color: var(--text-dim);" id="timeline-info">Yükleniyor...</span>
                    </div>
                    <div id="hourly-chart-box">
                        <!-- SVG chart dynamically loaded -->
                    </div>
                </div>

                <!-- Digital Fatigue Card -->
                <div class="glass-card">
                    <div class="card-header-flex">
                        <div class="card-title">
                            <span>⚡ Dijital Yorgunluk Kartı</span>
                        </div>
                    </div>
                    <div class="fatigue-card-inner">
                        <div class="fatigue-big" id="fatigue-ratio">-%</div>
                        <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Gece İzleme Maruziyeti (00:00 - 06:00)</div>
                        <div class="fatigue-pill" id="fatigue-status">Hesaplanıyor...</div>
                    </div>
                    <div style="margin-top: 18px;">
                        <div class="info-row">
                            <span style="color: var(--text-muted);">Gece İzlenen Video:</span>
                            <span style="font-weight: 600; color: var(--accent-rose);" id="fatigue-night-count">-</span>
                        </div>
                        <div class="info-row">
                            <span style="color: var(--text-muted);">Tahmini Ekran Süresi:</span>
                            <span style="font-weight: 600;" id="fatigue-hours">-</span>
                        </div>
                        <div class="info-row">
                            <span style="color: var(--text-muted);">Karşılıklı Takipler (Mutual):</span>
                            <span style="font-weight: 600; color: var(--accent-emerald);" id="social-mutuals">-</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 2: UNFOLLOWERS -->
        <div id="tab-unfollowers" class="tab-panel">
            <div class="glass-card">
                <div class="card-header-flex">
                    <div>
                        <div class="card-title">
                            <span>⚠️ Geri Takip Etmeyen Hesaplar</span>
                            <span style="font-size: 12px; color: var(--accent-rose); font-weight: 700; margin-left: 6px;" id="unfollowers-total-badge"></span>
                        </div>
                        <div style="font-size: 12px; color: var(--text-dim); margin-top: 2px;">Senin takip ettiğin fakat seni takip etmeyen profiller</div>
                    </div>
                    <div class="search-box">
                        <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        <input type="text" id="unfollower-search" class="search-input" placeholder="Kullanıcı ara..." oninput="filterUnfollowers()">
                    </div>
                </div>

                <div class="unfollowers-scroll" id="unfollowers-container">
                    <div class="empty-placeholder">Yükleniyor...</div>
                </div>
            </div>
        </div>

        <!-- TAB 3: CREATORS -->
        <div id="tab-creators" class="tab-panel">
            <div class="glass-card">
                <div class="card-header-flex">
                    <div>
                        <div class="card-title">
                            <span>🔥 En Çok İzlenen İçerik Üreticileri</span>
                        </div>
                        <div style="font-size: 12px; color: var(--text-dim); margin-top: 2px;">En çok vakit geçirdiğin video üreticileri</div>
                    </div>
                    <div class="search-box">
                        <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        <input type="text" id="creator-search" class="search-input" placeholder="Üretici ara..." oninput="filterCreators()">
                    </div>
                </div>

                <div class="unfollowers-scroll" id="creators-container">
                    <div class="empty-placeholder">Yükleniyor...</div>
                </div>
            </div>
        </div>

        <footer style="text-align: center; margin-top: 36px; font-size: 12px; color: var(--text-dim);">
            InstaVault &bull; 127.0.0.1 Yerel Analitik Sunucusu &bull; Zero External Network Calls
        </footer>
    </div>

    <script>
        let allUnfollowers = [];
        let allCreators = [];

        function switchTab(tabName) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

            const targetBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => 
                b.getAttribute('onclick').includes(tabName)
            );
            if (targetBtn) targetBtn.classList.add('active');

            const targetPanel = document.getElementById('tab-' + tabName);
            if (targetPanel) targetPanel.classList.add('active');
        }

        async function loadDashboard() {
            try {
                // Stats
                const statsRes = await fetch('/api/stats');
                const stats = await statsRes.json();

                document.getElementById('kpi-videos').textContent = Number(stats.video_count).toLocaleString();
                document.getElementById('kpi-posts').textContent = Number(stats.post_count).toLocaleString();
                document.getElementById('kpi-saved').textContent = Number(stats.saved_count).toLocaleString();
                document.getElementById('kpi-social').textContent = stats.follower_count + ' / ' + stats.following_count;
                document.getElementById('kpi-unfollowers-sub').textContent = stats.unfollower_count + ' karşılıksız takip';

                document.getElementById('fatigue-ratio').textContent = '%' + stats.night_ratio;
                document.getElementById('fatigue-night-count').textContent = Number(stats.night_video_count).toLocaleString() + ' video';
                document.getElementById('fatigue-hours').textContent = '~' + stats.estimated_hours + ' saat';
                document.getElementById('social-mutuals').textContent = stats.mutual_count + ' hesap';

                if (stats.night_ratio > 25) {
                    document.getElementById('fatigue-status').textContent = 'Yüksek Gece Yorgunluğu Riski';
                } else if (stats.night_ratio > 12) {
                    document.getElementById('fatigue-status').textContent = 'Orta Düzey Gece Maruziyeti';
                } else {
                    document.getElementById('fatigue-status').textContent = 'Sağlıklı Sirkadiyen Ritim';
                }

                // Timeline & Hourly chart
                loadTimeline();

                // Unfollowers
                loadUnfollowers();

                // Creators
                loadCreators();

            } catch (err) {
                console.error('Yükleme hatası:', err);
            }
        }

        async function loadTimeline() {
            try {
                const res = await fetch('/api/timeline');
                const data = await res.json();
                document.getElementById('timeline-info').textContent = data.hourly.length + ' saat dilimi';
                renderClientChart(data.hourly);
            } catch (err) {
                console.error(err);
            }
        }

        function renderClientChart(hourly) {
            const width = 760;
            const height = 180;
            const padX = 40;
            const padY = 24;
            const chartW = width - (padX * 2);
            const chartH = height - (padY * 2);

            const maxVal = Math.max(...hourly.map(h => h.count), 1);
            const barW = chartW / hourly.length;
            const innerW = Math.max(6, barW * 0.65);

            let barsSvg = '';
            for (let i = 0; i < hourly.length; i++) {
                const item = hourly[i];
                const count = item.count;
                const hourNum = parseInt(item.hour, 10);
                const barH = (count / maxVal) * chartH;
                const xCenter = padX + (i * barW) + (barW / 2);
                const xBar = xCenter - (innerW / 2);
                const yBar = padY + chartH - barH;
                const isNight = hourNum < 6;
                const color = isNight ? '#f43f5e' : '#818cf8';

                barsSvg += `
                    <g class="chart-bar-group">
                        <title>${item.hour}:00 - ${count} video</title>
                        <rect x="${xBar.toFixed(1)}" y="${yBar.toFixed(1)}" width="${innerW.toFixed(1)}" height="${barH.toFixed(1)}" rx="3" fill="${color}"/>
                        <text x="${xCenter.toFixed(1)}" y="${height - 8}" fill="${isNight ? '#f43f5e' : 'rgba(255,255,255,0.4)'}" font-size="9" text-anchor="middle" font-family="monospace">${item.hour}</text>
                    </g>
                `;
            }

            const svg = `
                <svg class="chart-svg" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
                    <line x1="${padX}" y1="${padY + chartH}" x2="${width - padX}" y2="${padY + chartH}" stroke="rgba(255,255,255,0.1)"/>
                    ${barsSvg}
                </svg>
            `;
            document.getElementById('hourly-chart-box').innerHTML = svg;
        }

        async function loadUnfollowers() {
            try {
                const res = await fetch('/api/unfollowers');
                allUnfollowers = await res.json();
                document.getElementById('unfollowers-total-badge').textContent = '(' + allUnfollowers.length + ')';
                renderUnfollowers(allUnfollowers);
            } catch (err) {
                console.error(err);
            }
        }

        function renderUnfollowers(list) {
            const container = document.getElementById('unfollowers-container');
            if (!list.length) {
                container.innerHTML = '<div class="empty-placeholder">Eşleşen hesap bulunamadı.</div>';
                return;
            }

            container.innerHTML = list.map(u => `
                <div class="unfollower-row">
                    <div>
                        <span class="user-tag">@${escapeHtml(u.username)}</span>
                    </div>
                    <div>
                        ${u.profile_url ? `<a href="${escapeHtml(u.profile_url)}" target="_blank" rel="noopener noreferrer" class="user-link-btn">Profili Aç &nearr;</a>` : ''}
                    </div>
                </div>
            `).join('');
        }

        function filterUnfollowers() {
            const q = document.getElementById('unfollower-search').value.toLowerCase().trim();
            const filtered = allUnfollowers.filter(u => u.username.toLowerCase().includes(q));
            renderUnfollowers(filtered);
        }

        async function loadCreators() {
            try {
                const res = await fetch('/api/creators');
                allCreators = await res.json();
                renderCreators(allCreators);
            } catch (err) {
                console.error(err);
            }
        }

        function renderCreators(list) {
            const container = document.getElementById('creators-container');
            if (!list.length) {
                container.innerHTML = '<div class="empty-placeholder">Eşleşen üretici bulunamadı.</div>';
                return;
            }

            container.innerHTML = list.map((c, idx) => `
                <div class="unfollower-row">
                    <div style="display:flex; align-items:center; gap:12px;">
                        <span style="font-family:monospace; color:var(--text-dim); font-size:12px;">#${idx + 1}</span>
                        <div>
                            <div style="font-weight:600; color:var(--text-main);">@${escapeHtml(c.username)}</div>
                            ${c.name ? `<div style="font-size:11px; color:var(--text-dim);">${escapeHtml(c.name)}</div>` : ''}
                        </div>
                    </div>
                    <div>
                        <span style="background:rgba(99,102,241,0.15); color:var(--accent-glow); padding:4px 10px; border-radius:8px; font-weight:600; font-family:monospace; font-size:12px;">
                            ${Number(c.count).toLocaleString()} izleme
                        </span>
                    </div>
                </div>
            `).join('');
        }

        function filterCreators() {
            const q = document.getElementById('creator-search').value.toLowerCase().trim();
            const filtered = allCreators.filter(c => 
                c.username.toLowerCase().includes(q) || (c.name && c.name.toLowerCase().includes(q))
            );
            renderCreators(filtered);
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        window.addEventListener('DOMContentLoaded', loadDashboard);
    </script>
</body>
</html>
"""


class InstaVaultRequestHandler(BaseHTTPRequestHandler):
    """InstaVault yerel REST API ve Web Arayüzü İstek Yöneticisi."""

    db_path: Path = DEFAULT_DB_PATH

    def log_message(self, format: str, *args: Any) -> None:
        """Konsol çıktısını sessiz tut veya formatla."""
        # Sessiz ve temiz stdout
        pass

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, html_str: str, status: int = HTTPStatus.OK) -> None:
        payload = html_str.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        conn = init_db(self.db_path)

        if path == "/" or path == "/index.html":
            html = get_web_dashboard_html()
            self._send_html(html)
            return

        elif path == "/api/stats":
            data = fetch_report_data(conn)
            stats = {
                "export_count": data["export_count"],
                "date_start": data["date_start"],
                "date_end": data["date_end"],
                "video_count": data["video_count"],
                "post_count": data["post_count"],
                "saved_count": data["saved_count"],
                "follower_count": data["follower_count"],
                "following_count": data["following_count"],
                "mutual_count": data["mutual_count"],
                "unfollower_count": data["unfollower_count"],
                "fans_count": data["fans_count"],
                "night_video_count": data["night_video_count"],
                "night_ratio": data["night_ratio"],
                "peak_hour": data["peak_hour"],
                "estimated_minutes": data["estimated_minutes"],
                "estimated_hours": data["estimated_hours"],
            }
            self._send_json(stats)
            return

        elif path == "/api/unfollowers":
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT f1.username, f1.profile_url
                FROM social_connections f1
                WHERE f1.connection_type = 'following'
                AND f1.username NOT IN (
                    SELECT f2.username FROM social_connections f2 WHERE f2.connection_type = 'follower'
                )
                ORDER BY f1.username ASC
            """)
            unfollowers = [{"username": r["username"], "profile_url": r["profile_url"]} for r in cur.fetchall()]
            self._send_json(unfollowers)
            return

        elif path == "/api/timeline":
            cur = conn.cursor()
            # Hourly
            cur.execute("""
                SELECT strftime('%H', watched_at) as hr, COUNT(*) as cnt
                FROM videos_watched
                WHERE watched_at IS NOT NULL AND watched_at != ''
                GROUP BY hr
                ORDER BY hr ASC
            """)
            hourly_map = dict(cur.fetchall())
            hourly_list = [{"hour": f"{h:02d}", "count": hourly_map.get(f"{h:02d}", 0)} for h in range(24)]

            # Daily (last 30 active days)
            cur.execute("""
                SELECT substr(watched_at, 1, 10) as day, COUNT(*) as cnt
                FROM videos_watched
                WHERE watched_at IS NOT NULL AND watched_at != ''
                GROUP BY day
                ORDER BY day DESC
                LIMIT 30
            """)
            daily_list = [{"day": r["day"], "count": r["cnt"]} for r in cur.fetchall()]
            daily_list.reverse()

            self._send_json({
                "hourly": hourly_list,
                "daily": daily_list,
            })
            return

        elif path == "/api/creators":
            cur = conn.cursor()
            cur.execute("""
                SELECT owner_username, owner_name, COUNT(*) as count
                FROM videos_watched
                WHERE owner_username IS NOT NULL AND owner_username != ''
                GROUP BY owner_username
                ORDER BY count DESC
                LIMIT 50
            """)
            creators = [{"username": r["owner_username"], "name": r["owner_name"], "count": r["count"]} for r in cur.fetchall()]
            self._send_json(creators)
            return

        else:
            self._send_json({"error": "Endpoint bulunamadı"}, status=HTTPStatus.NOT_FOUND)


def run_server(
    db_path: Optional[str | Path] = None,
    host: str = "127.0.0.1",
    port: int = 4173,
) -> None:
    """Yerel web sunucusunu sadece localhost/127.0.0.1 üzerinde başlatır."""
    # Güvenlik önlemi: Sadece localhost dinlemesine izin verilir
    bind_host = "127.0.0.1" if host not in ("127.0.0.1", "localhost") else host

    target_db = Path(db_path) if db_path else DEFAULT_DB_PATH
    InstaVaultRequestHandler.db_path = target_db

    server_address = (bind_host, port)
    httpd = ThreadingHTTPServer(server_address, InstaVaultRequestHandler)
    print(f"InstaVault Web Sunucusu Başlatıldı: http://{bind_host}:{port}")
    print("Durdurmak için Ctrl+C tuşlayın.")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu kapatılıyor...")
    finally:
        httpd.server_close()
