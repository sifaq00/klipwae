# 🔍 Audit Optimasi Klipwae — Temuan & Rekomendasi

Hasil audit menyeluruh frontend + backend. Diurutkan berdasarkan **dampak nyata** terhadap performa, stabilitas, dan pengalaman pengguna.

---

## 🔴 P0 — Bug Kritis (Harus Diperbaiki)

| # | Masalah | Dampak | Lokasi |
|---|---------|--------|--------|
| 1 | **`delete_job` memblokir event loop** — `thread.join(10)` dipanggil sync di dalam `async def`, membekukan seluruh API + SSE selama 10–20 detik | Semua request & live log berhenti | [`server.py:435, 489`](file:///D:/Project/auto-clipper-app/backend/server.py#L435) |
| 2 | **`render_tracked.py` hardcode `h264_nvenc`** — tidak pakai `video_encode_args()`, langsung crash di mesin tanpa GPU Nvidia | Reframe gagal total di CPU/macOS/AMD | [`render_tracked.py:89`](file:///D:/Project/auto-clipper-app/backend/stages/reframe/render_tracked.py#L89) |
| 3 | **Dependency hilang di `pyproject.toml`** — `opencv-python`, `numpy`, `python-dotenv` dipakai tapi tidak di-declare | Fresh install dari pyproject gagal | [`pyproject.toml:6-23`](file:///D:/Project/auto-clipper-app/backend/pyproject.toml#L6) |
| 4 | **SQL injection vector di `_toggle_segment`** — field name langsung di-interpolasi ke query tanpa whitelist | Potensi eksploitasi database | [`server.py:680`](file:///D:/Project/auto-clipper-app/backend/server.py#L680) |

---

## 🟠 P1 — Performa Tinggi (Dampak Besar)

### Backend

| # | Masalah | Dampak | Lokasi |
|---|---------|--------|--------|
| 5 | **Whisper model di-load ulang tiap job** — `WhisperModel(...)` baca disk 5–15 detik setiap transcribe | Buang waktu 5–15 detik/job | [`transcribe.py:114`](file:///D:/Project/auto-clipper-app/backend/stages/transcribe.py#L114) |
| 6 | **6–7 video decode pass di reframe** — detect_layout, face_regions, speaker_activity, tracker, render masing-masing buka video sendiri | CPU/GPU kerja 6× lipat per klip | [`reframe/__init__.py`](file:///D:/Project/auto-clipper-app/backend/stages/reframe/__init__.py) |
| 7 | **Missing DB indexes** — `stage_runs`, `metrics`, `segments`, `jobs` tanpa index, full table scan | Query makin lambat seiring data tumbuh | [`schema.sql`](file:///D:/Project/auto-clipper-app/backend/db/schema.sql) |
| 8 | **`_ensure_columns()` jalan tiap `JobDB()` dibuat** — DDL inspection di setiap API call | Overhead SQLite yang tidak perlu | [`jobs.py:64`](file:///D:/Project/auto-clipper-app/backend/db/jobs.py#L64) |
| 9 | **Tracker load semua frame ke RAM** — 600 frame uncompressed (~1.6GB) dalam list Python | Risiko OOM / crash di video panjang | [`tracker.py:96`](file:///D:/Project/auto-clipper-app/backend/stages/reframe/tracker.py#L96) |
| 10 | **yt-dlp dipanggil 3× per job** — metadata awal, download, metadata ulang | Lambat + risiko rate-limit YouTube | [`ingest.py:90, 113`](file:///D:/Project/auto-clipper-app/backend/stages/ingest.py#L90) |

### Frontend

| # | Masalah | Dampak | Lokasi |
|---|---------|--------|--------|
| 11 | **SSE log stream → re-render storm** — setiap baris log memicu `setLogs`, re-render seluruh `JobDetail` 20–60×/detik | UI lag / jank saat pipeline jalan | [`JobDetail.tsx:68`](file:///D:/Project/auto-clipper-app/frontend/src/components/JobDetail.tsx#L68) |
| 12 | **Card tanpa `React.memo`** — `SegmentCard` & `JobCard` re-render tiap 3 detik polling | Wasted render cycles | [`SegmentCard.tsx:13`](file:///D:/Project/auto-clipper-app/frontend/src/components/SegmentCard.tsx#L13) |
| 13 | **Polling interval leak saat reburn** — `setInterval` tidak di-cleanup kalau user navigasi balik | Memory leak, phantom API calls | [`JobDetail.tsx:166`](file:///D:/Project/auto-clipper-app/frontend/src/components/JobDetail.tsx#L166) |

---

## 🟡 P2 — Polish & Reliability

| # | Masalah | Dampak | Lokasi |
|---|---------|--------|--------|
| 14 | **Tidak ada Error Boundary** — error rendering = blank putih, user bingung | UX buruk saat crash | `main.tsx` |
| 15 | **PlayerModal overflow di mobile** — `max-h-[76vh]` + controls > 100vh, tombol terpotong | Mobile unusable | [`JobDetail.tsx:605`](file:///D:/Project/auto-clipper-app/frontend/src/components/JobDetail.tsx#L605) |
| 16 | **`stageLabel` bug** — status `"downloading"` tidak di-map, tampil raw string | Label progress jelek | [`JobDetail.tsx:496`](file:///D:/Project/auto-clipper-app/frontend/src/components/JobDetail.tsx#L496) |
| 17 | **Duplikat `STATUS_TO_STAGE`** — copy-paste di `JobsView.tsx` padahal sudah ada di `stages.tsx` | Code bloat | [`JobsView.tsx:14`](file:///D:/Project/auto-clipper-app/frontend/src/components/JobsView.tsx#L14) |
| 18 | **Duplikat clipboard formatting** — logika salin caption identik di 2 file | Maintenance risk | `SegmentCard.tsx:30`, `JobDetail.tsx:587` |
| 19 | **Spinner thread leak di transcribe** — kalau Whisper crash, thread spinner jalan selamanya | Background thread zombie | [`transcribe.py:131`](file:///D:/Project/auto-clipper-app/backend/stages/transcribe.py#L131) |
| 20 | **`reburn_captions` blokir HTTP** — request tetap terbuka selama proses reburn berjalan | Gateway timeout | [`server.py:943`](file:///D:/Project/auto-clipper-app/backend/server.py#L943) |
| 21 | **Missing ARIA labels** — tombol icon-only tanpa `aria-label`, toggle tanpa `role="switch"` | Accessibility gagal | Seluruh komponen |
| 22 | **Native `confirm()` dialog** — `window.confirm` membekukan thread, tidak bisa di-theme | UX kuno | `App.tsx:78`, `JobDetail.tsx:190` |

---

## 🟢 P3 — Nice-to-Have

| # | Masalah | Lokasi |
|---|---------|--------|
| 23 | Dead code: no-op `.replace()` di log viewer | `JobDetail.tsx:413` |
| 24 | Unused CSS class `.input-glass` | `index.css:59` |
| 25 | Unused Tailwind animations `shimmer`, `scan` | `tailwind.config.js` |
| 26 | Dead `Settings` interface di `types.ts` | `types.ts:30` |
| 27 | Redundant re-export shims `detect_layout.py`, `diarize.py` | `reframe/` |
| 28 | Duplikat `_get_video_info` (ffprobe vs ffmpeg -f null) | `reframe/__init__.py` vs `render.py` |
| 29 | Lazy-load `StyleEditor` (~26KB) | `App.tsx`, `JobDetail.tsx` |
| 30 | API pagination (hardcoded `LIMIT 50`) | `server.py:389` |

---

## 📋 Rekomendasi Fase Kerja

### Fase A — Critical Fixes (P0) ⏱️ ~30 menit
> Fix bug kritis yang bisa bikin crash / security hole

1. Fix `delete_job` → `asyncio.to_thread(thread.join, 10)`
2. Fix `render_tracked.py` → pakai `video_encode_args()`
3. Tambah missing deps di `pyproject.toml`
4. Whitelist field di `_toggle_segment`

### Fase B — Performance Wins (P1) ⏱️ ~1–2 jam
> Optimasi yang langsung terasa dampaknya

5. Whisper model caching (singleton)
6. DB indexes di `schema.sql`
7. Pindah `_ensure_columns()` ke `init_db()`
8. Throttle SSE log stream (buffer + RAF)
9. `React.memo` pada card components
10. Fix reburn polling cleanup

### Fase C — UX & Reliability (P2) ⏱️ ~1 jam
> Polish yang bikin app lebih robust

11. Error Boundary
12. Mobile PlayerModal fix
13. Fix `stageLabel` mapping
14. Deduplikasi code (STATUS_TO_STAGE, clipboard)
15. ARIA accessibility labels

### Fase D — Cleanup & Architecture (P3) ⏱️ ~30 menit
> Housekeeping, dead code removal

16–30. Dead code, lazy loading, API pagination, dll.

---

> [!TIP]
> **Rekomendasi**: Mulai dari **Fase A** (P0 critical fixes) karena ada security hole dan crash potential. Lalu lanjut **Fase B** untuk performa yang paling terasa.
