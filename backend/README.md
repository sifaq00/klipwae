# Auto Clipper CLI

Podcast YouTube → Klip Vertikal Fokus Produk → Siap Post TikTok.

## Prasyarat

- Python ≥ 3.11
- `ffmpeg` ≥ 6.0
- `yt-dlp`

## Instalasi

```bash
# 1. Clone & masuk folder
cd clipper-cli

# 2. Install dependensi + clipper sebagai CLI
pip install -e .

# 3. Copy & isi konfigurasi
cp .env.example .env
# Isi GOOGLE_API_KEY di .env (dapat dari aistudio.google.com)

# 4. Validasi setup
clipper config validate
```

## Cara Pakai

```bash
# Proses 1 video
clipper run "https://youtube.com/watch?v=xxx"

# Atau batch dari file (1 URL/baris)
clipper batch urls.txt --concurrency 3

# Lihat status semua job
clipper status

# Lihat klip yang siap direview
clipper review

# Tandai klip sudah dicek
clipper mark-reviewed 42

# Retry job yang gagal (lanjut dari stage gagal)
clipper retry abc123

# Export klip final
clipper export abc123 --to ~/Desktop/siap-post
```

## Pipeline

```
Input URL → ingest (yt-dlp) → transcribe (faster-whisper + VAD) →
analyze (Gemini) → clip (ffmpeg) → reframe (center-crop 9:16) →
caption (.ass karaoke burn-in) → clips_final/
```

Setiap stage idempotent — job gagal bisa di-retry tanpa ulang dari nol.

## Data Flow

| Direktori | Isi |
|---|---|
| `data/raw/` | Video asli hasil download |
| `data/transcripts/` | JSON transkrip (word-level timestamp) |
| `data/segments/` | JSON segmen produk hasil analisis |
| `data/clips_raw/` | Potongan video per segmen |
| `data/clips_final/` | Output final + subtitle burn-in |
| `logs/` | JSON lines per hari (structlog) |

Lihat `implementation-plan-auto-clipper-v2.md` untuk detail arsitektur & roadmap.
