# PRD — Klipwae Studio

**Product Requirements Document v1.0**
**Tanggal:** 10 Agustus 2026
**Status:** Aktif (produk berjalan, iterasi kontinu)

---

## 1. Ringkasan Eksekutif

**Klipwae Studio** adalah aplikasi yang mengubah episode podcast YouTube menjadi
klip vertikal 9:16 siap posting, lengkap dengan subtitle karaoke gaya viral,
deteksi segmen produk (health/fitness/beauty), dan caption affiliate siap salin.

**Value proposition:** dari 1 jam podcast -> 10-30 klip produk jadi dalam
beberapa puluh menit, otomatis penuh — tanpa edit manual.

**Arsitektur:** pipeline 6 tahap (download -> transkrip -> analisis -> klip ->
reframe -> subtitle) dengan model **worker-pull**: server API ringan di cloud
(queue + status + SSE), pipeline berat dijalankan di device pengguna (GPU
lokal), hasil disimpan di Cloudflare R2, state persist di Postgres (Supabase).

---

## 2. Problem Statement

| Pain point | Dampak |
|---|---|
| Podcast panjang (30-120 menit) berisi banyak momen produk, tapi manual cut = berjam-jam | Tidak scalable |
| Konten TikTok/Shopee butuh klip vertikal 9:16 + subtitle viral | Skill edit video + software mahal |
| Seller affiliate butuh klip + caption + hashtag per produk | Pekerjaan repetitif |
| Tidak ada cara cepat menemukan momen "produk dibahas" dalam episode | Scroll manual, sering kelewat |

**Solusi:** otomatisasi penuh — paste URL -> klip siap keranjang kuning.

---

## 3. Goals & Non-Goals

### Goals (v1)
- Pipeline 6 tahap berjalan otomatis end-to-end
- Deteksi segmen produk dengan akurasi tinggi (Gemini + preset niche)
- Output klip 9:16 dengan subtitle karaoke + animasi pop, font OFL
- Caption affiliate + hashtag per klip (siap salin ke TikTok/Shopee)
- Operasi paralel: 2+ job bersamaan, kill/retry/re-render aman
- Biaya operasional mendekati nol (free-tier infra + quota Gemini)

### Non-Goals (v1)
- Bukan editor video manual (tidak ada timeline editing)
- Bukan platform multi-user (single user / keluarga)
- Tidak mendukung input selain YouTube (vimeo, dll — roadmap)
- Bukan otomatisasi posting (upload ke TikTok/Shopee masih manual)
- Deteksi wajah multi-speaker tingkat produksi (stereo detection terbatas)

---

## 4. User Persona

### Persona utama: Seller Affiliate (Shopee/TikTok)
- Usia 18-35, bukan editor video
- Ingin konten produk harian dari podcast yang dia ikuti
- Butuh: klip + caption + hashtag + judul menarik, cepat
- Skala: 3-10 episode/minggu, 30-100 klip/minggu

### Persona kedua: Content Creator
- Punya channel/podcast sendiri
- Ingin repurpose episode -> klip shorts/reels
- Butuh: kualitas visual tinggi (reframe cinematic, subtitle viral)

### Persona ketiga: Pemilik bisnis lokal
- Ingin promosi produk dari konten orang lain (dengan izin)
- Butuh: klip produk saja, tanpa babble

---

## 5. Alur Kerja Inti (User Flow)

```
1. User paste URL YouTube (atau cari via Scraper)
2. Judul + thumbnail tampil instan (early-fetch metadata)
3. Job masuk queue -> worker device claim -> proses 6 tahap
4. UI tampilkan log live (SSE) + progress bar per tahap
5. Selesai -> daftar klip: review, tandai, reject, salin caption
6. Gaya subtitle bisa diganti + re-burn (non-blocking)
7. Render ulang kamera (snap-fixed-zoom) tanpa re-download
```

**Exit criteria per job:** minimal 1 klip dengan caption; 0 segmen -> notice
jelas "tidak ditemukan segmen produk" (bukan gagal diam-diam).

---

## 6. Fitur Detail

### 6.1 Pipeline (6 tahap)

| # | Stage | Teknologi | Output |
|---|-------|-----------|--------|
| 1 | Download | yt-dlp (bestvideo ≤720p + bestaudio, merge) | raw mp4 + metadata |
| 2 | Transkrip | faster-whisper (large-v3-turbo, word-level) | transcript JSON |
| 3 | Analisis | Gemini (chunk 20m, overlap 2m, paralel) | segments JSON |
| 4 | Klip | ffmpeg (cut window + buffer, align kalimat) | clips_raw |
| 5 | Reframe | YOLO11n + ByteTrack + camera path | clips_reframed (9:16) |
| 6 | Subtitle | libass burn-in karaoke + emoji natural | clips_final + .ass |

### 6.2 Deteksi Produk (Stage 3)
- **Preset niche:** Affiliate, Podcast & Debate, Comedy, Education, Storytelling
- **Skor confidence** (0.5-0.8 = sedang, ≥0.6 tersimpan, <0.6 = buang — `CONFIDENCE_THRESHOLD`)
- **Metadata per segmen:** produk, topik, alasan, hook score, affiliate caption,
  hashtags, virality reason
- **Fallback model:** 3.7 -> 3.6 -> 3.5 (kuota 429 per model terpisah)
- **Syarat sukses:** semua chunk gagal -> status failed dengan pesan jelas
  (bukan "0 segmen" menyesatkan)

### 6.3 Reframe (Stage 5) — mode snap-fixed-zoom
- Kamera **snap instan** ke anchor per-segmen saat ganti speaker (tanpa glide)
- **No-pan:** kamera diam selama bicara; hanya zoom in/out dari ukuran box
- Anchor = median posisi dominant speaker per window camera_path
- Fallback: anchor segmen -> zona -> center frame
- Single-shot (1 orang): snap sekali ke anchor global

### 6.4 Subtitle (Stage 6)
- **Karaoke highlight** (kata aktif membesar `\fscx106`) + pop
- **Emoji natural:** di-wrap `{\r\bord0\shad0}` — tanpa outline/color style
  (libass 0.17 tak support COLR -> emoji monokrom, didokumentasikan)
- **Font OFL bundle:** Montserrat Black, Poppins Bold/ExtraBold, Anton,
  Archivo Black, Roboto — dapat dipilih di UI (6 item); Bebas Neue + Lato
  juga ter-bundle (mapping legacy, tak ada di picker UI)
- **Preset Opus-style:** Opus Karaoke, White Box, Pink, Green Pop
- **Parity preview ≡ burn 100%** (shared `subtitle_filter_args`, backend_dir
  absolut, diverifikasi pixel-identical)

### 6.5 Scraper YouTube
- Natural-language search -> Gemini expander -> 4 variasi query -> merge + skor
- Skor relevansi: judul 2×, deskripsi 1×; filter durasi (podcast ≥15 menit)
- Fallback frasa pintar (tanpa Gemini) saat quota habis
- Cache hasil expand per query (hemat quota)

### 6.6 Operasional
- **Parallel jobs** (MAX_CONCURRENT_JOBS, default 2)
- **Kill-aware:** semua stage cek stop_requested; ffmpeg/whisper terminate
- **Retry** = repair (skip stage selesai); **re-render kamera** = hapus
  reframed+final lalu jalankan ulang
- **Retention:** raw video dipertahankan 14 hari (reprocess skip re-download)
- **Reframed cleanup:** dihapus setelah caption (hemat ~800MB/job)

### 6.7 Worker-pull (deploy cloud + device)
- Queue: atomic claim (SQLite `BEGIN IMMEDIATE` / PG `FOR UPDATE SKIP LOCKED`),
  FIFO, stale-claim recovery 120s, heartbeat 30s
- Worker: claim -> pipeline lokal (GPU device) -> upload via **presigned PUT**
  (R2 creds tak pernah di worker) -> lapor result
- Cancel: user kill -> status `killed` -> worker poll -> stop scoped
- Result fencing: done hanya diterima dari worker pemilik claim
- Log: batch POST -> job_logs -> SSE replay (persist lintas restart)

### 6.8 Fitur Pelengkap (terverifikasi di kode)

- **Auto-emoji injection** — emoji ditambahkan otomatis ke caption
  (`auto_emoji`, dict konten-context) sebelum di-render natural
- **Reburn auto-reframe** — reframed dihapus setelah caption (~800MB/job);
  saat re-burn, reframe dijalankan ulang otomatis (skip yang masih ada)
  supaya hasil tetap 9:16, bukan landscape
- **Reburn status lengkap** — running/done/killed/skipped (style nonaktif)/
  failed (reframe tak lengkap -> gagal lantang, bukan done palsu)
- **Worker local cleanup** — file lokal device (raw/klip/final/tracks)
  dihapus setelah upload sukses (~2-3GB/job)
- **JobsView load-more** — list bertambah 50 per klik (API pagination
  limit/offset, clamp 200)
- **Retention purge saat startup** — raw/tracks basi dibersihkan tiap
  server start (bukan hanya jadwal)
- **Per-job caption style override** — `style_for_job` merge: default ->
  global -> per-job

### 6.9 Real-time UI
- **SSE** log stream per job (cursor-based, replay-done marker — progress bar
  tak glitch saat hard refresh)
- **Polling 3s** utk status list
- Progress bar per stage (STATUS_TO_STAGE map — backend status ↔ stage key)
- Thumbnail YouTube (mqdefault — 16:9 native, tanpa letterbox)

---

## 7. Non-Functional Requirements

| Aspek | Requirement |
|---|---|
| **Kinerja** | 1 jam audio -> transkrip GPU < 10 menit; reframe 9 klip < 5 menit (track cache); klip paralel 3 worker |
| **Ketersediaan** | API toleran downtime singkat (worker-pull by design); job persist di DB |
| **Keandalan** | Kill/retry/re-render tidak korup state; status whitelist; fencing worker |
| **Keamanan** | WORKER_TOKEN bearer; R2 creds hanya di server (presigned); CORS whitelist; path traversal guard di key upload |
| **Skalabilitas** | Worker horizontal (N device); query ter-index; claim atomic |
| **Biaya** | Target $0/bln: Gemini free-tier (20 req/hari/model + fallback), infra free-tier, R2 10GB |
| **Encoding** | Semua file UTF-8 no BOM; ASCII policy utk kode (hindari mojibake) |
| **Testing** | 208 test (pytest) + tsc; E2E sintetis tanpa GPU/network; parity pixel test |

### Batas & Limitasi yang didokumentasikan
- Whisper: 1 model di VRAM (cache singleton) — 2 job transcribe butuh VRAM cukup
- Gemini free: 20 req/hari/model — fallback rantai 3.7->3.6->3.5
- libass 0.17: emoji monokrom (no COLR)
- yt-dlp: butuh Deno (JS challenge YouTube)
- Free-tier hosting: auto-sleep / ephemeral FS / kuota deploy

---

## 8. Arsitektur

```
[FE React/Vite] ── SSE+poll ──► [BE FastAPI (queue, status, log, presign)]
                                      │
                        claim ◄───────┘ heartbeat/progress/result
                                      ▼
                              [Worker(s) device: pipeline penuh]
                                      │ presigned PUT
                                      ▼
                              [R2 "klipwae" (public read)] ◄── UI klip URL

DB: SQLite (dev) / Postgres Supabase (prod) — dual-backend via DATABASE_URL
```

- **Satu codebase**: `server.py` (API) + `worker.py` (pipeline) + `stages/`
- **Import ringan server**: `stages/__init__.py` tanpa auto-import berat —
  pipeline di-import eksplisit saat run
- **Dual-backend DB**: wrapper `db/pg.py` API-kompatibel sqlite3; `?`->`%s`,
  DictCursor, commit-only context manager

---

## 9. Data Model (ringkas)

- `jobs`: id, url, title, duration, channel, status, preset, claimed_by,
  claimed_at, heartbeat_at, notice, downloaded, caption_style, error
- `job_logs`: (job_id, seq) PK, line — replay SSE
- `stage_runs`: job, stage, status, attempt, duration_ms, error
- `segments`: job, clip_idx, window (clip_start/end_sec), produk, topik,
  confidence, reason, hook_score, caption_text, affiliate_caption, hashtags,
  reviewed, posted, clip_path
- `metrics`: job, stage, duration_ms, cost_usd, extra_json (biaya Gemini)

---

## 10. Endpoint API Utama

| Method | Path | Deskripsi |
|---|---|---|
| POST | /api/jobs | Create (mode runner lokal / queue) |
| GET | /api/jobs, /api/jobs/{id} | List / detail |
| DELETE | /api/jobs/{id} | Kill + hapus DB + file |
| POST | /api/jobs/{id}/kill · /retry · /re-render | Kontrol |
| POST | /api/jobs/claim · /{id}/heartbeat · /progress · /result · /upload-url | Worker |
| GET | /api/jobs/{id}/log (SSE) · /segments · /uploads · /reburn-status | Real-time + data |
| POST | /api/jobs/{id}/reburn-captions | Re-burn subtitle (non-blocking; auto re-reframe dulu kalau reframed hilang) |
| GET | /api/jobs/{id}/reburn-status | Status reburn: running/done/killed/skipped/failed |
| POST | /api/jobs/{id}/kill | Kill job ATAU reburn aktif (routing otomatis) |
| POST | /api/segments/{id}/reviewed · /posted · /reject | Toggle review/posted · hapus segmen + file |
| GET/PUT | /api/settings | Pengaturan aplikasi |
| GET | /api/scrape | Scraper (q / url, min_duration) |
| GET/PUT | /api/caption-style, /api/jobs/{id}/caption-style, /api/fonts, /api/caption-style/preview | Styling |
| GET | /api/health | Health |

---

## 11. Metrics Keberhasilan (v1)

- **Pipeline success rate** ≥ 90% (job -> done tanpa retry manual)
- **Segmen berguna** ≥ 60% (klip yang ditandai reviewed)
- **Time-to-first-clip** < 15 menit utk episode 1 jam (GPU device)
- **Nol data loss** pada kill/retry/re-render (state konsisten)
- **Biaya operasional** ≤ $1/bln (target $0)

---

## 12. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Kuota Gemini habis (20/hari/model) | Analisis gagal | Fallback rantai model + pesan jelas + cache scraper |
| YouTube blokir download | Pipeline gagal di stage 1 | yt-dlp + Deno + retry; error jelas |
| Free hosting mati/suspend | API down | Worker-pull toleran; DB persist; migrasi cepat (Dockerfile siap) |
| Kartu user ditolak platform | Tidak bisa bayar hosting | Jalur $0 (Colab+tunnel / VPS PayPal) |
| Emoji monokrom (libass) | Kualitas visual | Dokumentasi; opsi bundle font emoji COLR di roadmap |
| Reframe off-center | Klip jelek | Anchor per-segmen + fallback chain + parity test |
| Mojibake encoding | UI aneh | ASCII policy + scan test + UTF-8 no BOM di mana-mana |

---

## 13. Roadmap

### v1.x (saat ini — sebagian sudah live)
- [x] Pipeline 6 tahap end-to-end
- [x] Worker-pull + queue + R2 + Supabase
- [x] Snap-fixed-zoom + per-segmen anchor
- [x] Opus-style presets + emoji natural + parity preview
- [x] Scraper (Gemini expander + skor relevansi)
- [ ] Deploy stabil (hosting final diputuskan: Colab+tunnel / VPS / GCloud)

### v2 (backlog)
- Upload otomatis TikTok/Shopee (API partner)
- Multi-user + akun/izin
- Dukungan input non-YouTube
- Font emoji COLR bundle
- A/B tuning preset subtitle (hook, panjang klip)
- Analitik performa klip (views dari TikTok API)

---

## 14. Konfigurasi (.env)

| Key | Default | Fungsi |
|---|---|---|
| GOOGLE_API_KEY | "" | Gemini — wajib di worker |
| ANALYZE_MODEL / _FALLBACK | flash-latest / 3.6-flash | Rantai fallback kuota |
| WHISPER_MODEL / _DEVICE | large-v3-turbo / cuda | Transkrip |
| MAX_CONCURRENT_JOBS | 2 | Paralelisme |
| CONFIDENCE_THRESHOLD | 0.6 | Minimum confidence segmen |
| MIN_HOLD_SEC | 1.2 | Hold minimum antar segmen |
| VIDEO_DOWNLOAD_RESOLUTION | 720 | Kualitas download |
| STORAGE_RETENTION_DAYS | 14 | Retensi raw |
| CHUNK_DURATION_MIN / OVERLAP | 20 / 2 | Chunking Gemini |
| REFRAME_ZOOM_MIN/MAX/FIT/IDLE/EASE/DEADBAND | 1.15/2.0/0.6/1.05/0.04/0.05 | Parameter kamera snap-fixed-zoom |
| REFRAME_HEAD_BIAS | 0.22 | Bias head anchor |
| REFRAME_TRACK_STEP/IMGSZ/CACHE | 3/320/true | YOLO tracking |
| WORKER_QUEUE / WORKER_TOKEN | false / "" | Mode worker-pull |
| DATABASE_URL | "" | Postgres (prod); kosong = SQLite |
| R2_ACCOUNT_ID / ACCESS_KEY / SECRET | - | Server-side only (presigned utk worker) |
| R2_PUBLIC_URL | "" | Domain publik klip |
| FRONTEND_ORIGINS | localhost:5173 | CORS whitelist |
| LOG_LEVEL | INFO | Logging |

> Catatan: WORKER_QUEUE/WORKER_TOKEN/R2_* di `.env.worker-server.example`;
> DATABASE_URL/FRONTEND_ORIGINS didukung config.py (belum ada di file contoh —
> set manual di env platform).

---

## 15. Lampiran: Referensi Kode Kunci

| Komponen | File |
|---|---|
| API + queue | `backend/server.py` |
| Worker device | `backend/worker.py` |
| DB dual-backend | `backend/db/jobs.py`, `backend/db/pg.py` |
| Orchestrator | `backend/orchestrator.py` |
| Stages | `backend/stages/{ingest,transcribe,analyze,clip,caption}.py`, `reframe/` |
| R2 | `backend/utils/r2.py` |
| Subtitles | `backend/stages/caption.py` (ASS + parity) |
| Frontend | `frontend/src/` |

---

## 16. Acceptance Criteria per Stage (DoD)

| Stage | Definition of Done |
|---|---|
| Download | File raw ≥1MB valid (ffprobe ok), metadata (title/duration/channel) terisi, marker `downloaded=1` |
| Transkrip | JSON lengkap dgn kata ber-timestamp (word-level), ≥95% durasi audio ter-cover |
| Analisis | Segmen ≥1 dgn confidence ≥ threshold ATAU notice jelas; semua-chunk-gagal -> status failed + pesan kuota |
| Klip | Window aktual (clip_start/end_sec) tersimpan benar; durasi klip = window ±0.5s |
| Reframe | Output 9:16 (rasio ±0.05); anchor per-segmen; durasi terjaga; track cache dipakai saat ada |
| Subtitle | Final + .ass ada; preview ≡ burn (pixel diff <1.0); emoji natural; timing kata ±0.1s |

---

## 17. Recovery & Monitoring

### Backup
- **DB:** queue/status/log di Postgres (Supabase) — otomatis backup platform
  (15 hari); SQLite lokal = worker-scope (tak perlu backup)
- **Aset:** R2 = storage utama (tak ada data lain yang perlu backup); bucket
  versioning bisa diaktifkan utk proteksi overwrite
- **Config:** `.env` + `render.yaml`/Dockerfile di git (secret tak ikut)

### Monitoring (manual saat ini)
- Log container (uvicorn + structlog) utk debug
- Health check `/api/health` (platform free-tier sudah auto-check)
- Notifikasi: belum ada alerting otomatis — roadmap: error telemetry
  (analyze/caption/scrape failure ke log terstruktur + dashboard)

### Recovery skenario
| Skenario | Recovery |
|---|---|
| API down (hosting/suspend) | Job persist di Supabase; worker retry claim -> lanjut otomatis |
| Worker crash | Claim stale 120s -> worker lain (atau device sama) ambil ulang |
| R2 error | Upload gagal -> status failed (bukan done palsu); retry manual |
| Deploy baru | Rolling restart; DB eksternal tak terpengaruh |
| Database hilang (force) | Queue hilang, R2 file tetap; re-create job utk klip ulang |

---

## 18. Hak & Kepatuhan Konten

- **Hak cipta:** klip dibuat dari konten pihak ketiga (podcast YouTube).
  Pengguna bertanggung jawab memastikan hak pakai (lisensi channel, izin,
  fair use). Aplikasi hanya alat produksi.
- **Disclosure affiliate:** caption memakai hashtag/#ads sesuai kebijakan
  platform tempat posting (TikTok/Shopee/IG) — tanggung jawab pengguna.
- **ToS platform:** free-tier (Colab/Gemini/hosting) punya batas pemakaian —
  penggunaan normal personal aman; hindari 24/7-abuse.
- **Privasi:** aplikasi single-user, tanpa akun publik; data (URL, transkrip,
  klip) hanya milik pengguna di infra milik pengguna.

---

## 19. Glosarium

| Istilah | Definisi |
|---|---|
| Stage | Satu tahap pipeline (download -> subtitle) |
| Job | Satu episode yang diproses |
| Segmen | Satu momen produk terdeteksi (-> 1+ klip) |
| Klip | Potongan video mentah (30-60s) |
| Reframed | Klip yang sudah 9:16 (perantara, dihapus setelah subtitle) |
| Final | Klip siap posting (subtitle ter-burn) |
| Notice | Info non-fatal (mis. "tidak ada segmen produk") |
| Worker-pull | Worker ambil job dari queue (bukan server push) |
| Presigned PUT | URL upload sementara ke R2 (tanpa expose secret) |
| Anchor | Posisi kamera tetap per segmen (mode snap-fixed-zoom) |
| Parity | Kesetaraan visual preview vs hasil burn |

---

## 20. Kontribusi & Model Kolaborasi

- **Multi-contributor:** project terbuka utk kontributor lain — setiap fitur
  dikerjakan di **feature branch** + review (subagent/code review) sebelum
  merge ke main
- **Standar kontribusi:** TDD utk backend (test-first), `tsc --noEmit` utk
  frontend, ASCII policy (hindari mojibake), dokumentasi di file terkait
- **Milestone:** per fitur (1-2 minggu); rilis stabil saat 90% pipeline
  success + hosting selalu-on + alerting terpasang

---

## 21. Open Questions (belum diputuskan)

| # | Pertanyaan | Opsi | Implikasi |
|---|---|---|---|
| 1 | Hosting API final | Colab+tunnel / VPS / GCloud e2-micro | Downtime vs biaya vs kartu |
| 2 | Emoji warna penuh | Bundle font COLR (Noto Color Emoji) | +~20MB image; libass support masih terbatas |
| 3 | Multi-user | Akun + izin | Perlu auth (supabase auth), RBAC — v2 |
| 4 | Upload otomatis platform | TikTok/Shopee API partner | Izin partner, quota API, ToS platform |
| 5 | Backup R2 | Versioning aktif / backup periodik | Biaya storage tambahan |

---

## 22. Changelog

| Tanggal | Versi | Perubahan |
|---|---|---|
| 10 Agu 2026 | v1.0 | Dokumen awal (fitur inti + arsitektur worker-pull) |
| 19 Agu 2026 | v1.1 | Tambah DoD per stage, recovery & monitoring, kepatuhan konten, glosarium, kontribusi; owner/timeline diganti model kolaborasi |
