# Clip Quality Tuning — Design

Tanggal: 2026-08-12
Status: Approved (user: "oke gass A")
Tujuan: hasil klip mendekati standar Opus Clip (kamera halus follow pembicara, subtitle karaoke sinkron, deteksi produk akurat), terukur lewat A/B terhadap 70 file baseline di `data/clips_final/`.

Keputusan user: tuning menyeluruh (semua area) · gaya Opus Clip · konten campuran (solo + split-screen) · prioritas kualitas di atas speed.

Kendala hardware: **RTX 2050 4GB VRAM**. Konsekuensi:
- Whisper cuda harus `compute_type="int8_float16"` (bukan float16) — float16 besar-besaran OOM di 4GB. int8_float16 kualitas hampir setara, VRAM ~1.3GB.
- `MAX_CONCURRENT_JOBS=2` risiko OOM kalau 2 job transcribe bareng di 1 GPU 4GB → default tetap 2, tapi `.env.example` + README kasih catatan: set 1 kalau transcribe OOM. Tanpa perubahan kode concurrency.

## 1. Fix bug (TDD dulu, implementasi setelah)

### 1a. Diarization fallback salah arah (`stages/reframe/diarization.py:82`)

Kode mati `if False else (s, e, "left")` — saat MAR gagal (tidak ada data bibir), semua speaker dipetakan ke sisi `"left"`. Kamera split-screen ikut orang kiri terus walau yang bicara kanan.

Fix: fallback return `(s, e, "previous")` untuk semua segmen diarization — `build_camera_path` sudah handle `"previous"` (lanjut sisi aktif). Hapus kode mati.

Test (`tests/test_reframe.py`, baru):
- `map_speakers_to_sides(diar=[...], mar=None)` → semua side `"previous"`.
- `map_speakers_to_sides(diar=[...], mar=[])` → semua side `"previous"`.
- Kasus normal tetap: side mayoritas dari MAR overlap.

### 1b. Wrap subtitle overflow (`stages/caption.py:109`)

`_wrap(max_chars=38)` tetap 38 untuk semua font size. Pada `size=96` (≈48px/char), 38 char ≈ 1824px > 1080 lebar → libass wrap ulang sendiri → tinggi baris tidak terprediksi, risiko tabrakan antar baris.

Fix: `max_chars` dinamis: `floor((1080 - margin_l - margin_r) / (size * 0.5))` dengan margin 2×40px → `floor(1000 / (size * 0.5))`. Pada 96px ≈ 20 char.

Test: `generate_ass` dengan size berbeda → semua baris hasil wrap ≤ batas char dinamis, dan konsisten antar dialogue baris yang sama.

## 2. Transkripsi

### 2a. Model default `large-v3-turbo` + compute type aman 4GB

Model sudah terdownload di `backend/models/whisper-large-v3-turbo/` (lihat `transcribe.py:72-73` — sudah otomatis pakai local path kalau ada). Ganti default di `config.py` (`whisper_model: str = "large-v3-turbo"`) dan `.env.example`.

`transcribe.py:78` compute type: `"int8" if device == "cpu" else "float16"` → ganti cuda jadi `"int8_float16"` (RTX 2050 4GB — float16 OOM). Refactor ke helper `whisper_compute_type(device) -> str` supaya bisa unit-test.

Verifikasi: 1 episode pendek — word timestamps akurat (tidak ada kata terlewat, boundary kalimat masuk akal), tidak ada OOM.

### 2b. Bahasa auto-detect + initial prompt

`transcribe.py:85` hardcoded `language="id"` — nama produk Inggris ditranskrip fonetik Indonesia.

Fix: `language=None` (auto-detect) + `initial_prompt` dari config baru `whisper_initial_prompt: str = ""` (default kosong). Kalau kosong, parameter di-skip (biar API whisper tidak dapat string kosong — faster-whisper terima `initial_prompt=None`).

Config baru: `WHISPER_INITIAL_PROMPT` di `.env`/`.env.example`.

Verifikasi: transkrip segmen yang mengandung brand Inggris ("Somethinc", "Creatine") mengeja benar.

## 3. Clip boundary align ke kalimat

`CLIP_BUFFER_SEC=1.5` fixed — segmen yang mulai/tengah kalimat → klip potong kalimat.

Fix di `stages/clip.py`:
- Sebelum potong, cari jeda bicara (gap ≥ 0.5s antar word, dari `_load_words`) terakhir sebelum `start_sec` dan pertama sesudah `end_sec`.
- Kalau ketemu jeda dalam jendela ±3 detik dari boundary: align ke sana. Kalau tidak (bicara terus): tetap buffer 1.5s.
- Config baru `clip_align_sentence: bool = True` (env `CLIP_ALIGN_SENTENCE`).
- Berlaku untuk range pertama & terakhir tiap segmen (range tengah dari `split_segment_ranges` tetap di jeda bicara — sudah ada `best_gap`).

Catatan: `_load_words` sudah tersedia; align pakai data yang sama. Subtitle (`caption.py`) ambil kata dalam `[start-1.5, end+1.5]` — align hanya menggeser potongan video, kata tetap kebawa karena window subtitle ≥ clip window. Konsisten: window subtitle harus tetap ≥ durasi klip (tidak berubah).

Test (`tests/test_clip.py`): fungsi baru `align_to_gap(words, sec, direction)` — kasus: gap ada di jendela → geser; gap di luar jendela → return asal; kata kosong → return asal.

## 4. Reframe parameter → config + A/B

### 4a. Konstanta jadi Settings

`stages/reframe/render_tracked.py` — semua konstanta kunci jadi config (env):

| Konstanta | Default baru | Nama config |
|---|---|---|
| `ZOOM_MIN` | 1.15 | `reframe_zoom_min` |
| `ZOOM_MAX` | 2.0 | `reframe_zoom_max` |
| `ZOOM_FIT` | 0.6 | `reframe_zoom_fit` |
| `HEAD_BIAS` | 0.30 | `reframe_head_bias` |
| `SMOOTH_ALPHA` | 0.12 | `reframe_smooth_alpha` |
| `DEADBAND` | 0.006 | `reframe_deadband` |
| `HOLD_SEC` | 0.5 | `reframe_hold_sec` |
| `ZOOM_IDLE` | 1.05 | `reframe_zoom_idle` |
| `ZOOM_EASE` | 0.06 | `reframe_zoom_ease` |
| `TARGET_ALPHA` | 0.35 | `reframe_target_alpha` |

`render_tracked()` terima param config (default = nilai sekarang kalau config tidak diset, biar test lama tetap hijau). `ReframeStage.run` baca dari `config`.

Pendekatan ini: A/B tuning tanpa edit kode — cukup ubah `.env` + restart server.

### 4b. A/B manual

- Pilih 2-3 klip dari `data/clips_raw/` (representasi solo + split-screen).
- Render versi lama (nilai konstanta asli) vs baru (default baru).
- Frame compare: framing kepala (`HEAD_BIAS`), ukuran orang (`ZOOM_FIT`), kecepatan pan (`SMOOTH_ALPHA`), switch sisi saat ganti pembicara.
- Hasil: set angka final di `.env`.

### 4c. Zoom terbatas (opsional, kalau A/B menunjukkan orang kecil)

`ZOOM_MIN=1.1` lama — kalau orang kecil di frame tetap kecil setelah A/B, naik cap + turun `ZOOM_FIT` bertahap. Keputusan setelah data A/B, bukan sekarang.

## 5. Caption geometri

### 5a. Margin bawah TikTok safe zone

`utils/caption_style.py` DEFAULT_STYLE `margin_v: 100` → `240`. Berlaku untuk gaya global + preview. Job lama tidak terpengaruh (style tersimpan per job / di JSON global — file `data/caption_style.json` kalau ada harus di-update manual atau dihapus biar ke-reset).

Catatan: `_ass_header` pakai `margin_v` langsung. Cek juga `position=top` case (margin tetap 240, jarak dari atas).

### 5b. Pop scale turun

`stages/caption.py:157` `\fscx112\fscy112` → `\fscx106\fscy106` (kurangi jitter kata aktif saat animasi z-order).

Verifikasi: preview `/api/caption-style/preview` — tidak ada kedipan/goyang antar baris.

## 6. Analyze golden tests

3 fixture baru di `tests/fixtures/golden_transcripts/`:
- `006_daftar_cepat.json` — host menyebut beberapa produk cepat dalam satu daftar (expected: produk dengan pembahasan berarti saja).
- `007_promo_read.json` — host baca materi iklan monoton (expected: negatif, kecuali ada ulasan).
- `008_bandingkan_dua.json` — host bandingkan 2 produk (expected: 2 segmen, masing-masing jelas).

Tiap fixture: transcript sintetis + `expected_segments` + `min_confidence`. Ikuti pola fixture 001-005 (cek `test_golden.py` harness — mock `analyze_chunk`, overlap ratio ≥ 0.7).

## 7. Validasi akhir

1. `pytest backend/tests` — semua hijau (jalankan dari `backend/`).
2. Frontend typecheck/build: `npm run build` di `frontend/` (tidak ada perubahan frontend yang direncanakan, tapi verifikasi).
3. E2E: 1 episode pendek end-to-end via API (POST `/api/jobs`) → review klip final vs baseline lama: subtitle sync, framing kamera, sisi split-screen benar, kalimat tidak terpotong.

## Ruang lingkup

DALAM: config.py, .env.example, stages/transcribe.py, stages/clip.py, stages/caption.py, stages/reframe/diarization.py, stages/reframe/render_tracked.py, stages/reframe/__init__.py, utils/caption_style.py, tests (reframe, clip, caption, golden fixtures).

LUAR: refactor render pipeline (GPU), UI frontend, multi-bahasa penuh, audio enhancement (EQ/noise), konfigurasi retensi storage, prompt rewrite besar Gemini.

## Risiko

- `large-v3-turbo` int8_float16 butuh ~1.3GB VRAM — aman di 4GB. Kalau tetap OOM (GPU dipakai aplikasi lain): fallback tetap `medium` via config, bukan kode.
- 2 job transcribe bareng di GPU 4GB bisa OOM — set `MAX_CONCURRENT_JOBS=1` kalau terjadi (dokumentasi di `.env.example`, tanpa kode concurrency baru).
- `language=None` bisa deteksi bahasa lain di podcast campuran — acceptable; initial prompt mengarahkan.
- Ubah `margin_v` default: `data/caption_style.json` lama menimpa default — instruksi hapus/update file saat implementasi.
- A/B reframe subjektif — pakai 2-3 klip tetap + kriteria framing/zoom/pan yang jelas di 4b.
