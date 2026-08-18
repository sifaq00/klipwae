# Klipwae Studio

Turn YouTube podcast episodes into ready-to-post product clips — automatically.

Paste a podcast URL, and Klipwae downloads the episode, transcribes it, detects
product mentions (health / fitness / beauty / food / gadgets), and cuts vertical
9:16 clips with karaoke-style burned-in subtitles — ready for TikTok's product
cart.

![Pipeline](https://img.shields.io/badge/pipeline-download%20%E2%86%92%20transcribe%20%E2%86%92%20analyze%20%E2%86%92%20clip%20%E2%86%92%20reframe%20%E2%86%92%20caption-teal)

---

## Table of Contents

- [How it works](#how-it-works)
- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running](#running)
- [API Reference](#api-reference)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## How it works

```
YouTube URL
   │
   ▼
① Download      yt-dlp (720p default, bestvideo+bestaudio, merged)
   │
   ▼
② Transcribe    faster-whisper (large-v3-turbo default, CUDA/CPU, word-level timestamps)
   │
   ▼
③ Analyze       Gemini — detects product-mention segments from the transcript
   │              (health/fitness/beauty focus, confidence-scored, viral hook scoring,
   │               affiliate caption + hashtags per segment)
   ▼
④ Clip          ffmpeg — splits segments into 30–60s chunks aligned to sentence breaks
   │
   ▼
⑤ Reframe       vertical 9:16 with cinematic camera tracking:
   │              - layout detection (single / multi-speaker)
   │              - YOLO11n + ByteTrack person tracking
   │              - speaker-activity awareness + rapid-turn smoothing
   │              - adaptive headroom, deadband + EMA smoothing
   ▼
⑥ Subtitle      karaoke word-by-word burn-in (libass) with viral font pack,
                  kinetic animations, auto-emoji injection
   │
   ▼
✅ Clips ready   review / mark reviewed / reject / copy caption+hashtags / post
```

## Features

### Product detection
- **Niche presets** — Affiliate (products), Podcast & Debate, Comedy, Education,
  Storytelling — each with its own tuned analysis prompt
- **Health/fitness/beauty focus** — supplements, fitness equipment, skincare,
  bodycare; generic terms without a brand are rejected, deep discussion without
  a brand is kept
- **Per-segment metadata** — product name, topic, confidence, reason,
  viral-hook score, affiliate caption + hashtags (ready to paste)
- **Non-fatal notice** — episodes with zero product segments show a clear notice
  instead of failing silently

### Video production
- **Cinematic reframing** — smart crop to 9:16 with face tracking, speaker
  zones, push-in zoom, deadband + EMA smoothing (no jitter)
- **Viral subtitles** — karaoke highlight, pop/bounce animations, auto-emoji
  injection, 6 bundled open-source fonts (OFL), live style preview rendered by
  the same libass engine used for burn-in
- **Style presets per job** — re-burn captions non-blocking with live progress

### Operations
- **Parallel jobs** — up to `MAX_CONCURRENT_JOBS` episodes run simultaneously
  (per-thread stdout routing, GPU memory cleanup, kill-aware pipelines)
- **Kill / retry / reprocess** — stop mid-flight (kills ffmpeg/whisper
  properly), retry only repairs missing work; raw video is kept until retention
  so reprocess skips re-downloading
- **Live SSE log stream** — real-time pipeline log with auto-reconnect and
  absolute cursor (no duplicate lines across retries)
- **Retention cleanup** — stale raw files and tracks purged at startup and on
  schedule (`STORAGE_RETENTION_DAYS`)
- **Instant metadata** — title, channel and duration appear seconds after
  pasting a URL (yt-dlp metadata fetch runs parallel to the download)

## Architecture

| Layer | Tech | Notes |
|-------|------|-------|
| Backend | Python 3.11+, FastAPI, uvicorn | SSE streaming, async endpoints, thread-per-job runner |
| DB | SQLite (WAL mode) | `jobs`, `stage_runs`, `segments`, `metrics`; idempotent schema migration on startup |
| Transcription | faster-whisper | GPU (CUDA) or CPU, word-level timestamps, model singleton cache |
| Analysis | Google Gemini | chunked (20 min, 2 min overlap) + parallel calls with per-chunk retry |
| Reframe | OpenCV, Ultralytics YOLO11n, ByteTrack | chunked tracking (32 frames/batch) to bound RAM |
| Rendering | ffmpeg (NVENC or libx264 fallback) | kill-aware subprocess management |
| Frontend | React 18, Vite, Tailwind | 3s polling + SSE log stream (100ms batched), lazy-loaded style editor |

**Concurrency model:** each job runs in its own thread. `sys.stdout` is routed
per-thread into that job's log buffer (a global `redirect_stdout` would bleed
logs across concurrent jobs). ffmpeg/whisper subprocesses are registered per
thread so kill requests terminate the right process.

## Requirements

### Minimum

| Component | Version | Why |
|-----------|---------|-----|
| Python | **3.11+** (tested on 3.11.9) | Backend (FastAPI, faster-whisper) |
| Node.js | **18+** (tested on 20/22) | Frontend (Vite 5) |
| ffmpeg + ffprobe | **8.1+** (any recent 6.x also works) | All audio/video processing |
| yt-dlp | latest (2025+) | YouTube download |
| Deno | latest (2.x) | **Required by modern yt-dlp** for YouTube JS challenge/signature — without it downloads fail with `403 Forbidden` |
| Google Gemini API key | — | Transcript analysis (only paid requirement) |

### Optional: NVIDIA GPU (strongly recommended)

- **NVIDIA GPU** with at least **4 GB VRAM** (6–8 GB comfortable)
- **CUDA 12.x** drivers (any recent driver bundle works; you don't need the CUDA
  Toolkit installed separately — pip wheels bundle the runtime)
- **NVIDIA cuDNN 9** — required by faster-whisper's CTranslate2
  (`pip install nvidia-cudnn-cu12` below handles it)

With GPU: transcription ~10× faster, YOLO person tracking runs on CUDA, and
final render uses NVENC (h264_nvenc). Without GPU everything still works on CPU
(just slower) — `WHISPER_DEVICE=cpu`.

## Installation

### Step 1 — Install Python 3.11+

**Windows**

1. Download the installer: https://www.python.org/downloads/
2. During install, **check "Add python.exe to PATH"**
3. Verify in a new terminal:
   ```bat
   python --version
   ```

**Linux/macOS**
```bash
# Ubuntu/Debian
sudo apt install python3.11 python3.11-venv python3-pip
# macOS (homebrew)
brew install python@3.11
```

### Step 2 — Install ffmpeg, yt-dlp, Deno

**Windows** (winget):
```bat
winget install ffmpeg
winget install yt-dlp
winget install DenoLand.Deno
```

**Linux/macOS**:
```bash
# Ubuntu/Debian
sudo apt install ffmpeg
pip install --user yt-dlp
curl -fsSL https://deno.land/install.sh | sh        # then add ~/.deno/bin to PATH

# macOS
brew install ffmpeg yt-dlp deno
```

Verify all three are on PATH (each prints a version):
```bash
ffmpeg -version
yt-dlp --version
deno --version
```

### Step 3 — Backend (Python venv)

```bash
cd backend
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install --upgrade pip
pip install -e .
```

**GPU-only extra steps** (skip if CPU-only):

1. Install NVIDIA cuDNN 9 (required by faster-whisper on CUDA):
   ```bash
   pip install nvidia-cudnn-cu12
   ```
   If `faster-whisper` already pulled it as a dependency (check with
   `pip show faster-whisper`), skip this.

2. Install PyTorch with CUDA support (needed by YOLO person tracking on GPU;
   pip's default PyTorch is CPU-only):
   ```bash
   # Windows (CUDA 12.1):
   pip install torch --index-url https://download.pytorch.org/whl/cu121
   # Linux: cu121 or cu124 both fine
   ```

3. Verify CUDA is visible:
   ```bash
   python -c "import torch; print('CUDA:', torch.cuda.is_available())"
   python -c "import ctranslate2; print('ct2 supports cuda:', ctranslate2.get_cuda_device_count() > 0)"
   ```
   Both should print `True`.

> **No GPU?** Do nothing here. Set `WHISPER_DEVICE=cpu` in `.env` (step 5).
> The reframe stage still works — YOLO falls back to CPU, encoding uses libx264.

### Step 4 — Frontend

```bash
cd frontend
npm install
```

### Step 5 — Environment file

```bash
cd backend
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/macOS
```

Then edit `.env`:

```ini
GOOGLE_API_KEY=your_key_here     # REQUIRED — get one at https://aistudio.google.com/apikey
WHISPER_DEVICE=cuda              # change to cpu if no GPU
MAX_CONCURRENT_JOBS=2            # set 1 if 2 transcriptions OOM your GPU
```

### Step 6 — Smoke test

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests -q   # 166 passed, 6 skipped (GPU)
```

Optional: pre-download the whisper model once so the first job doesn't wait:
```bash
.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cuda'); print('model ready')"
```

## Configuration

All settings live in `backend/.env` (see `backend/.env.example` for the full
list with comments).

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | — | **Required.** Gemini key for transcript analysis |
| `ANALYZE_MODEL` / `ANALYZE_MODEL_FALLBACK` | `gemini-flash-latest` / `gemini-3.6-flash` | Gemini model + auto-fallback saat kuota 429 (free-tier 20 req/hari per model) |
| `WHISPER_MODEL` | `large-v3-turbo` | Whisper model (local dir `models/` wins if present) |
| `WHISPER_DEVICE` | `cuda` | `cuda` or `cpu` |
| `MAX_CONCURRENT_JOBS` | `2` | Parallel jobs; set `1` if 2 transcriptions OOM a 4GB GPU |
| `CONFIDENCE_THRESHOLD` | `0.6` | Min segment confidence kept |
| `VIDEO_DOWNLOAD_RESOLUTION` | `720` | Max height for the video stream |
| `STORAGE_RETENTION_DAYS` | `14` | Raw videos / tracks kept before cleanup |
| `CHUNK_DURATION_MIN` / `CHUNK_OVERLAP_MIN` | `20` / `2` | Transcript chunking for Gemini |
| `CLIP_ALIGN_SENTENCE` | `true` | Clip cuts aligned to sentence breaks |
| `REFRAME_*` | see example | Camera tracking: zoom range, head bias, EMA alpha, deadband, hold time |
| `REFRAME_TRACK_STEP` / `_IMGSZ` / `_CACHE` | `3` / `320` / `true` | YOLO tracking subsample, input size, cache |
| `LOG_LEVEL` | `INFO` | Backend log level |

## Running

### One command (Windows)

```bat
start.bat
```

Starts backend (port 8180) + frontend (port 5173) in separate windows and opens
the browser. It skips components that are already running.

### Manually

```bash
# Terminal 1 — backend
cd backend
.venv\Scripts\python.exe -m uvicorn server:app --port 8180 --reload

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open http://localhost:5173

### Usage flow

1. **Paste a YouTube URL** — title & thumbnail appear instantly
2. Pick a **niche preset** (default: Affiliate)
3. Click **Bikin Klip** — watch the live pipeline log
4. When done, open the episode → review clips → mark Reviewed/Posted,
   copy affiliate caption + hashtags, or reject (deletes the files)
5. **Gaya subtitle** — tweak font/style, preview live, re-burn non-blocking
6. **Hapus episode** — kills running work, deletes DB rows + all files

## API Reference

Base URL: `http://localhost:8180`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/jobs` | Create job `{url, preset?}` → `{job_id, status}` |
| GET | `/api/jobs` | List jobs (`?limit=&offset=`, paginated, max 200) |
| GET | `/api/jobs/{id}` | Job detail (incl. `running`, stages, notice) |
| DELETE | `/api/jobs/{id}` | Kill + delete DB rows + all files (non-blocking joins) |
| POST | `/api/jobs/{id}/kill` | Kill a running job |
| POST | `/api/jobs/{id}/retry` | Resume/repair pipeline (skips completed stages) |
| GET | `/api/jobs/{id}/log` | SSE stream of pipeline logs (cursor-based) |
| GET | `/api/jobs/{id}/segments` | Product segments |
| POST | `/api/segments/{id}/reviewed` | Toggle reviewed flag |
| POST | `/api/segments/{id}/posted` | Toggle posted flag |
| POST | `/api/segments/{id}/reject` | Delete segment + files |
| GET/PUT | `/api/settings` | App settings |
| GET | `/api/fonts` | Bundled font list |
| POST | `/api/caption-style/preview` | Render style preview (async, non-blocking) |
| GET/PUT | `/api/caption-style` | Global caption style |
| GET/PUT | `/api/jobs/{id}/caption-style` | Per-job caption style |
| POST | `/api/jobs/{id}/reburn-captions` | Re-burn subtitles with current style (non-blocking) |
| GET | `/api/jobs/{id}/reburn-status` | Reburn progress `{status, alive}` |

## Project structure

```
auto-clipper-app/
├── start.bat                  # One-click launcher (Windows)
├── backend/
│   ├── server.py              # FastAPI app, SSE, job runner, reburn
│   ├── orchestrator.py        # Pipeline orchestration, retries, kill handling
│   ├── runtime.py             # Per-thread stop events + subprocess registry
│   ├── config.py              # Pydantic settings (.env)
│   ├── db/
│   │   ├── schema.sql         # Tables + performance indexes
│   │   └── jobs.py            # JobDB, idempotent migrations
│   ├── stages/
│   │   ├── ingest.py          # yt-dlp download + metadata
│   │   ├── transcribe.py      # faster-whisper + model cache
│   │   ├── analyze.py         # Gemini chunked analysis + cost tracking
│   │   ├── clip.py            # Sentence-aligned ffmpeg cuts
│   │   ├── reframe/           # Layout detect, tracker, camera path, render
│   │   └── caption.py         # Karaoke ASS generation + libass burn-in
│   ├── utils/
│   │   ├── ffmpeg_helpers.py  # run_ffmpeg, video_encode_args (NVENC/CPU)
│   │   ├── video_info.py      # ffprobe wrapper
│   │   ├── caption_style.py   # Style defaults, font map (OFL)
│   │   └── gpu_cleanup.py     # Torch/whisper memory release
│   ├── prompts/               # Preset prompts (affiliate, podcast, …)
│   ├── assets/fonts + fonts/  # Bundled OFL fonts
│   ├── tests/                 # 166 tests (pytest)
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx            # Shell: polling, job creation, layout
│   │   ├── components/        # JobsView, JobDetail, SegmentCard, StyleEditor…
│   │   ├── lib/               # API client, stages, clipboard, caption defaults
│   │   └── main.tsx           # Entry + ErrorBoundary
│   └── package.json
```

## Testing

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests -q
# 166 passed, 6 skipped (GPU-dependent tests skip without NVIDIA hardware)

cd ../frontend
npx tsc --noEmit
```

Coverage highlights: orchestrator retry/kill semantics, SSE log sequence
survival across retries, stdout per-thread routing (2 concurrent jobs), caption
kill-awareness, ingest partial-file recovery, metadata refetch paths, tracker,
camera path, golden transcript fixtures.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| Download fails with `403 Forbidden` / JS challenge | Deno missing. Install: `winget install DenoLand.Deno`, then restart the backend |
| Studio is empty after creating a job | Backend not restarted since a code change — uvicorn `--reload` handles this; check `data/jobs.db` |
| Progress bar stuck at 0% | Old frontend cache — hard refresh (Ctrl+Shift+R); bar maps backend status → stage |
| Transcribe OOM with 2 jobs | Set `MAX_CONCURRENT_JOBS=1` |
| Reburn appears to hang | It's non-blocking now: watch the toast + per-clip progress; status endpoint `/reburn-status` |
| Clips look green in Chrome | ffmpeg NVENC + rawvideo colorspace bug — handled automatically (forced yuv420p + BT.601 tags) |
| No subtitles in final clip | Style has `enabled: false`, or the `.ass` was missing (now guarded — re-burn repairs) |
| Windows: port already in use | `start.bat` refuses and suggests a different port |

## Deployment (Vercel + HF Spaces + device worker)

Arsitektur worker-pull: UI di Vercel ($0), API ringan + queue di Hugging Face
Spaces ($0), pipeline penuh dijalankan di **device kamu** (worker.py — GPU
device dipakai, bukan server). Hasil klip disimpan di Cloudflare R2.

```
[Vercel FE] -> [HF Spaces BE: queue + status + SSE] <- claim/poll <- [device: worker.py]
                        |                                      |
                        +-- presigned PUT URL -----------------> R2 bucket "klipwae" -> UI
```

### 1. Cloudflare R2 (storage)

1. Buat bucket `klipwae` di Cloudflare R2 (sudah dibuat untuk project ini)
2. Buat API token (R2 access key) → catat `ACCOUNT_ID`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`
3. Aktifkan **public read**: R2 → bucket → Settings → Public access → `r2.dev` subdomain
   atau custom domain → catat URL-nya (`R2_PUBLIC_URL`)

### 2. Hugging Face Spaces (backend API)

1. Buat Space baru: SDK **Docker**, hardware CPU basic (free)
2. `Settings → Variables and secrets`:
   ```
   WORKER_QUEUE=true
   WORKER_TOKEN=<secret-panjang-acak>     # dipakai worker device juga
   R2_ACCOUNT_ID=...
   R2_ACCESS_KEY_ID=...
   R2_SECRET_ACCESS_KEY=...
   R2_BUCKET_NAME=klipwae
   R2_PUBLIC_URL=https://<r2-domain>     # dari langkah 1.3
   ```
3. Push `Dockerfile` (root) + `backend/` ke Space via git:
   ```bash
   git remote add space https://huggingface.co/spaces/<username>/<space-name>
   git push space main
   ```
4. Space jalan → URL: `https://<username>-<space-name>.hf.space`

> Catatan: DB SQLite ada di `/data` (persistent disk HF). Space auto-sleep saat
> idle — worker yang claim saat sleep akan retry (heartbeat 30s).

### 3. Vercel (frontend)

1. Import repo, framework **Vite**, root directory `frontend/`
2. `vercel.json` di root sudah ada — ganti destination ke URL Space kamu
3. Build: `npm run build` — tak perlu env lain (API via proxy `/api`)

### 4. Device worker (pipeline penuh)

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements-worker.txt              # whisper + YOLO + mediapipe

# .env worker (device): TIDAK butuh R2 creds — cukup token + API URL
set API_URL=https://<username>-<space-name>.hf.space/api
set WORKER_TOKEN=<secret-sama>
set WORKER_ID=pc-kantor
set GOOGLE_API_KEY=<gemini-key>                     # analyze + caption jalan di device
set WHISPER_DEVICE=cuda                             # GPU device
python worker.py
```

Worker: claim job → download → transcribe → analyze → clip → reframe →
caption → upload ke R2 (presigned) → lapor. Banyak device = banyak worker
(scalable horizontal). Satu worker proses 1 job; GPU 4GB cukup utk 1 job.

### Catatan arsitektur

- R2 credentials HANYA di server (presigned PUT utk worker)
- Worker crash → claim kedaluwarsa (120s) → worker lain ambil ulang
- `WORKER_TOKEN` = full trust (bisa mark job done) — jangan dibagi publik
- Server restart aman: queue/log/segments persist di SQLite + file

## License

Private project. Bundled fonts are SIL Open Font License; `yolo11n.pt` is AGPL
(Ultralytics) — check your distribution terms.
