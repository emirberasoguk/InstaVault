# InstaVault: Yerel Instagram Veri Kasası ve Analitik

> Meta'nın periyodik olarak verdiği Instagram veri arşivlerini (HTML) yerelde toplayan,
> işleyen ve içerik üretici / power user için anlamlı içgörüye dönüştüren açık kaynak araç.
>
> **Durum:** tasarım aşaması (v0.0.0). Bu README bağlayıcı teknik karar içermez.
> Teknoloji ve yapı değişebilir. Netleşen tek şey ilkelerdir: **yerellik + gizlilik + denetlenebilirlik.**

**Geliştirici:** Emir Bera Soğuk
**Lisans:** MIT (planlanan)
**Önceki not:** `../instadash.md` bu projenin ilk fikridir, hükmü bu README'ye devredilmiştir.

---

## 1. Ne yapacağız? (Ne)

Her hafta Meta'dan gelen Instagram arşivlerini tek bir yerel veritabanında biriktirip
şu sorulara cevap vereceğiz:

1. Beni kim takip etti / bıraktı? Karşılıksız takipler kimler?
2. Ne izliyorum vs neye gerçekten değer veriyorum? (izlenen reels vs kaydedilenler)
3. İlgi haritam ne? (teknoloji, futbol, mizah, backend... kümeleri)
4. Reklamcılar beni nasıl görüyor? Verim kimlere gitmiş?
5. Arama -> izleme -> kaydetme hunim nasıl çalışıyor?
6. Gece kaydırma, story yığılması gibi alışkanlıklarım neler?

### 1.1 Fikir havuzu (aday, öncelikli değil)

antigravity-cli önerilerinden süzülenler, duygu analizi hariç çoğu yapılabilir:

- **Dijital yorgunluk skoru:** ardışık izleme oturumları (örn: gap > 15 dk = yeni oturum),
  gece (00-05) yığılması, oturum uzunluğu -> tek skor. Psikolojik etkiyi sayıya döker.
- **Gerçek arkadaşlık skoru:** `following/followers` + `messages/chats` + `liked_posts` +
  `story_likes` çaprazı. "Sadece takipçi" vs "gerçek etkileşim" ağ grafiği (PageRank).
- **Unutulma hakkı (GDPR) denetçisi:** sildiğin sandıkların (`deleted_content`,
  arama geçmişi) `ad_preferences / advertisers_using` içinde hâlâ duruyor mu?
- **Gölge profil ipuçları:** `friend_map + locations_of_interest + off_meta` üzerinden
  Meta'nın seni kimlerle eşleştirdiği. Veri seyrek (friend_map'te tek kişi var),
  o yüzden "harita" değil "ipucu paneli" olur.
- **Duygu/kategori etiketleme:** şüpheli. Türkçe, kısa, argolu caption'larda sözlük
  tabanlı duygu analizi çok gürültülü; gömülü model ister ve yine de rage-bait /
  mizah ayrımı zor. Faz-4 araştırma maddesi, söz vermiyoruz.

Çıktı 3 arayüzde olacak (öncelik sırasıyla):

1. **TUI** - terminalden hızlı bakış (önce bu)
2. **Statik HTML/Markdown rapor** - paylaşılabilir, internetsiz açılır tek dosya
3. **Tam interaktif yerel web** - tıklanabilir küme grafiği, filtreli tablo, ML run karşılaştırma.
   Sadece `127.0.0.1` dinler, dışarı port açmaz.

Kapsam dışı (ilk fazda): DM gövdesi okuma, otomatik unfollow/takip etme, buluta veri gönderme.

## 2. Neden yapıyoruz? (Neden)

- Instagram'ın kendi analitiği yüzeysel ve geçmişi tutmuyor.
- Haftalık arşivler `delta` geliyor (örn: `followers_1.html` sadece o haftanın gelenleri).
  Tek tek bakınca bir şey ifade etmiyor, birikince ediyor.
- Veriler dağınık: 8 haftada 61 farklı HTML tipi, en büyüğü 4.7 MB (`stories_viewed`),
  haftada 668 video + 518 post + 2251 story izleme var. Elle takip imkansız.
- Gizlilik: bu veride telefon, e-posta, konum, IP, mesaj listesi var.
  Bunu üçüncü parti bir servise / yapay zekâ API'sine vermek istemiyoruz.

## 3. Niçin yapıyoruz? (Niçin / amaç)

- **Veri sahipliği:** veri Meta'da kalmasın, kendi diskimizde biriksin.
- **Öz-farkındalık:** algoritma bana ne dayatıyor, ben ne seçiyorum?
- **Hijyen:** hangi reklamveren verimi almış, hangi uygulama bağlı, hangi arama iz bırakmış?
- **Öğrenme projesi:** küçük ama gerçek bir veri boru hattı + yerel ML + TUI/web pratiği.

## 4. Nasıl yapacağız? (Nasıl)

### 4.1 İlkeler (değişmez)

1. Analiz %100 yerelde. Yapay zekâ API'sine, telemetriye veri gitmez.
2. Network sadece kullanıcının kendi kaynaklarına: Google Drive, e-posta (IMAP).
   Default kapalı, `--enable-drive / --enable-mail` ile açılır.
3. Ham klasöre yazma yok (read-only ingest). Her dosya `sha256` ile izlenir.
4. Çıktı ayrı dizinde: `~/.local/share/instavault/` (db + rapor).
5. Hassas alanlar default maskeli (`+90 542 *** ** 30`, mesaj gövdesi yok).
   Hamını görmek için `--include-private` gerekir.
6. Tekrarlanabilirlik: aynı veri + aynı tohum = aynı sonuç. Her ML deneyi loglanır.

### 4.2 Boru hattı + sağlamlık kuralları

```
Topla (Local dir -> Drive -> Mail*) -> Oku -> Parse -> Biriktir (vault)
  -> Analiz (kural + ML) -> Sun (TUI / statik / web)
* Mail Faz-3, interface bugünden hazır tutulur.
```

**Parser kuralı (antigravity-cli notu, doğru):** Meta obfuskeli class'lara
(`_a6-p` vb.) güvenme. Yarın `xyz-1` olur, sistem kırılır. Sıralama:

1. Semantik çapalar: `<title>`, `<h1>`, `<time datetime="">`, `a[href*="instagram.com/"]`
2. Yapı: tag sırası / XPath (`main > div > div > a + div`), class sadece zayıf sinyal
3. Her parser için fixture: `tests/fixtures/*.html` + beklenen kayıt. Class değişince
   test kızarır, sessizce yanlış veri işlenmez. Regex ile HTML parse yok.

**Delta/UPSERT kuralı:** her arşiv sadece o haftayı kapsar
(`September 17 to September 24` başlığı). Mükerrer engellemek için doğal anahtar:

- watches/likes/saves: `(url + ts + owner)`
- follows: `(username + ts + action)`
- `INSERT ... ON CONFLICT DO NOTHING / UPDATE` zorunlu. Dosya hash'i (`sha256`)
  işlenen export'ları işaretler, tekrar scan aynı veriyi katmaz.

Kaynak soyutlaması:

```text
trait Source { list() -> [arşiv]; fetch(id) -> zip; }
LocalDirSource (şimdi) | DriveSource (Faz-2) | EmailSource (Faz-3)
```

### 4.3 Veri envanteri (özet, detay taramadan)

`~/Desktop/İnstagram Ham Veri/` içinde 27 Tem - 24 Eyl 2026 arası 8 export var.
Format JSON değil, HTML + medya. Dolu olanlar:

- Tüketim: `videos_watched, posts_viewed, stories_viewed, ads_viewed, ads_clicked`
- Etkileşim: `liked_posts, liked_comments, story_likes, polls, reposts, notes, instants`
- Sosyal: `following, followers_1, recently_unfollowed, pending, recent_requests, friend_map`
- Arama: `profile_searches, recent_searches, word_or_phrase_searches`
- Reklam: `advertisers_using_*, other_categories, ad_preferences, off_meta_technologies`
- Güvenlik/üretim: `login_activity, profile_activity, stories, other_content, deleted_content`

Boş (`no-data`): `comments (kısmi), events, ai, subscriptions, shared_access` - export tipine göre değişir.

### 4.4 Analiz vizyonu (titiz ML, acele yok)

Faz-1 deterministik: frekans, owner/hashtag sayımı, saat histogramı,
`ilgi skoru = save/like/comment/watch ağırlıklı + zaman-decay + Bayes düzeltme`.

Faz-2 yerel unsupervised (internetsiz):
Türkçe normalize (I/İ kuralı, snowball-tr, stopword) -> TF-IDF (+hashtag x2)
-> KMeans++ (k=4..12, silhouette + Davies-Bouldin + bootstrap ARI ile seç)
-> co-watch PMI + Louvain + PageRank.
Validasyon: 6 hafta train / 2 hafta test (zamansal split), tohum sabit,
`ml_runs` tablosunda params+metrics+data_hash saklanır.
Her küme açıklanabilir olmalı: top terim + top owner + örnek caption.

Gömülü model (MiniLM ONNX vb.) ancak gerekirse, offline dosya olarak. İlk fazda yok.

## 5. Demo şema (aday teknolojiler - değişebilir!)

> Aşağıdakiler **kesin karar değildir**, sadece şu anki adaylardır.
> Değişirse bu bölüm güncellenir, ilkeler bakidir.

```text
                       +------------------+
                       |  Kaynaklar       |
                       | Local / Drive* / |
                       | Mail* (*opt-in)  |
                       +--------+---------+
                                | zip/html (salt-okunur)
                       +--------v---------+
                       |  Parse           |
                       | aday: Rust       |
                       | (scraper/tl)     |
                       | alt: Go/Python   |
                       +--------+---------+
                                |
                       +--------v---------+
                       |  vault           |
                       |  aday A: SQLite  |
                       |  (WAL, sistem    |
                       |  kaydı, basit)   |
                       |  aday B: DuckDB  |
                       |  (analitik,      |
                       |  kolonlu, OLAP)  |
                       |  exports,persons |
                       |  watches,likes,  |
                       |  saves,searches, |
                       |  ads,ml_runs     |
                       +--+---+---+------+
```

**DB notu (DuckDB önerisi):** antigravity-cli DuckDB önerdi, haklı olduğu yer var.
SQLite = olgun, tek dosya, yazma/işlemsel yükte sağlam, Rust binding sorunsuz.
DuckDB = analitik sorgularda (histogram, zaman serisi, küme ön-agregasyon) vektörize
ve hızlı, parquet ile iyi geçinir. Bizim ölçekte (onlarca MB) ikisi de yeter.
Eğilim: **SQLite sistem kaydı (source of truth), DuckDB opsiyonel analitik katman**
(read-only attach / parquet export). Faz-0 SQLite ile başlar, şema DuckDB'ye
taşınabilir tutulur. Karar Faz-2'de verilir.
                          |   |   |
              +-----------v+  |  ++------------+
              | TUI (aday:  |  |  | Web (aday:  |
              | ratatui)   |  |  | axum 127.0.0.1|
              |            |  |  | + D3 vendored|
              +------------+  |  +--------------+  +--------------+
                              |                   | Statik rapor |
                              +------------------>| (tek .html)  |
                                                  +--------------+
```

Aday dil notu: hız için Rust, sadelik için Go, prototipleme için Python düşünülüyor.
C, güvensiz HTML parse + gizli veri kombinasyonunda bellek güvenliği nedeniyle elendi.
ML olgunluğu tek başına karar vermez; bu ölçekte (MB'lar) deterministik + hafif ML yeterlidir.

## 6. Yol haritası (taslak)

- [ ] Faz-0: `scan + parse (videos_watched/saved/following) + vault.db + test`
- [ ] Faz-1: TUI + statik rapor
- [ ] Faz-2: Drive pull + systemd timer + interaktif web (küme grafiği)
- [ ] Faz-3: Mail ingest + ML kümeleri + run karşılaştırma
- [ ] Faz-4: PII dashboard, shop/müzik zevki, gece skoru

## 7. Hızlı başlangıç (ileride doldurulacak)

```bash
# planlanan CLI, henüz yok
vault scan  --input ~/Desktop/İnstagram\ Ham\ Veri
vault tui
vault report --format html -o rapor.html
vault serve  --bind 127.0.0.1:4173
```

---

Not: bu dosya yaşayan belgedir. Teknoloji değişirse şema güncellenir, ilkeler değişmez.
