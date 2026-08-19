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
YouTube URL (paste / Scraper search)
   │
   ▼
① Download      yt-dlp (720p default, bestvideo+bestaudio, merged)
   │              • title/channel/duration shown INSTANTLY (parallel metadata fetch)
   ▼
② Transcribe    faster-whisper (large-v3-turbo default, CUDA/CPU, word-level timestamps)
   │
   ▼
③ Analyze       Gemini — detects product-mention segments from the transcript
   │              (health/fitness/beauty focus, confidence-scored, viral hook scoring,
   │               affiliate caption + hashtags per segment; auto model fallback on quota)
   ▼
④ Clip          ffmpeg — splits segments into 30–60s chunks aligned to sentence breaks
   │              (stores exact clip window so subtitle timing is pixel-accurate)
   ▼
⑤ Reframe       vertical 9:16 — snap-fixed-zoom camera mode:
   │              - camera SNAPS instantly to the speaker on segment change (no glide)
   │              - no-pan during speech: fixed anchor, zoom-only from box size
   │              - per-segment anchors (person may shift between segments)
   │              - YOLO11n + ByteTrack tracking with persistent cache
   ▼
⑥ Subtitle      karaoke word-by-word burn-in (libass):
   │              - viral OFL font pack (Montserrat Black, Poppins, Anton, ...)
   │              - pop animation, auto-emoji injected NATURALLY (no outline on emoji)
   │              - Opus-style presets; live preview ≡ final burn (100% parity)
   ▼
✅ Clips ready   review / mark reviewed / reject / copy caption+hashtags / post
```

> **Worker-pull architecture:** the heavy pipeline runs on YOUR device (worker.py —
> uses your GPU), while a lightweight API server handles the job queue, status and
> live logs. State persists in SQLite (local) or Postgres (Supabase) via
> `DATABASE_URL`. Clips are uploaded to Cloudflare R2 through presigned URLs —
> storage credentials never leave the server.

## Features

### Product detection
- **Niche presets** — Affiliate (products), Podcast & Debate, Comedy, Education,
  Storytelling — each with its own tuned analysis prompt
- **Health/fitness/beauty focus** — supplements, fitness equipment, skincare,
  bodycare; generic terms without a brand are rejected, deep discussion without
  a brand is kept
- **Per-segment metadata** — product name, topic, confidence, reason,
  viral-hook score, affiliate caption + hashtags (ready to paste)
- **Quota resilience** — Gemini model auto-fallback chain (3.7 → 3.6 → 3.5)
  when free-tier daily quota is exhausted per model
- **Non-fatal notice** — episodes with zero product segments show a clear notice
  instead of failing silently; all-chunks-failed surfaces a clear error instead
  of a misleading "0 segments"

### YouTube Scraper
- **Natural-language search** — describe what you want ("podcast indonesia yang
  bahas produk skincare sponsor") → Gemini expands to 4 queries → merged + deduped
- **Relevance scoring** — keyword matches: title 2×, description 1×; sorted by score
- **Podcast filter** — hide short videos (< 15 min) with one toggle
- **Add to Studio** — multi-select results → create jobs in one click
- **Smart fallback** — when Gemini is rate-limited, a keyword-split fallback keeps
  search working (no hard dependency on the API)

### Video production
- **Snap-fixed-zoom reframing** — camera SNAPS instantly to the active speaker on
  segment change (no glide from the side), then stays fixed (no pan) while the
  person talks — only zoom follows body size. Per-segment anchors keep the
  speaker centered even if they shift between segments.
- **Viral subtitles** — karaoke highlight with pop animation, auto-emoji injected
  NATURALLY (emoji rendered without subtitle outline/color), bundled OFL font pack
  (Montserrat Black, Poppins, Anton, Archivo Black, Roboto, Bebas Neue, Lato)
- **Opus-style presets** — Opus Karaoke, Opus White Box, Opus Pink, Opus Green Pop
- **Live preview ≡ final burn (100% parity)** — preview and burn share the exact
  same subtitle filter/engine (pixel-verified), so what you see is what you get
- **Style presets per job** — re-burn captions non-blocking with live progress
- **Render ulang kamera** — one-click re-render reframe+caption without re-downloading

### Operations
- **Parallel jobs** — up to `MAX_CONCURRENT_JOBS` episodes run simultaneously
  (per-thread stdout routing, GPU memory cleanup, kill-aware pipelines)
- **Worker-pull queue** — heavy pipeline runs on your device (`worker.py`):
  atomic job claim, heartbeat with stale-recovery, batch progress logs,
  result fencing (only the claiming worker can report), cancel via status poll
- **Kill / retry / re-render** — stop mid-flight (kills ffmpeg/whisper properly),
  retry repairs missing work; raw video kept until retention so reprocess skips
  re-download
- **Live SSE log stream** — real-time pipeline log with auto-reconnect, absolute
  cursor (no duplicates), and replay-done marker (progress bar never glitches on
  refresh)
- **Storage hygiene** — reframed intermediates auto-deleted after caption
  (~800MB/job); stale raw/tracks purged by retention; worker cleans local files
  after upload
- **Instant metadata** — title, channel and duration appear seconds after
  pasting a URL (yt-dlp metadata fetch runs parallel to the download)

## Architecture

| Layer | Tech | Notes |
|-------|------|-------|
| Backend | Python 3.11+, FastAPI, uvicorn | SSE streaming, async endpoints, queue API |
| DB | SQLite / Postgres (dual-backend) | SQLite local & tests; `DATABASE_URL` (Supabase) in prod; atomic claims (`SKIP LOCKED`) |
| Storage | Cloudflare R2 | server issues presigned PUT URLs — workers upload without seeing secrets |
| Transcription | faster-whisper | GPU (CUDA) or CPU, word-level timestamps, model singleton cache |
| Analysis | Google Gemini | chunked (20 min, 2 min overlap) + parallel calls, model fallback chain on quota |
| Reframe | OpenCV, Ultralytics YOLO11n, ByteTrack | chunked tracking (32 frames/batch), persistent cache |
| Rendering | ffmpeg (NVENC or libx264 fallback) | kill-aware subprocess management, VBR cap 6M |
| Worker | `worker.py` (device) | claim → local pipeline (your GPU) → presigned upload → report |
| Frontend | React 18, Vite, Tailwind | 3s polling + SSE log stream (100ms batched), lazy-loaded style editor |

**Concurrency model (local runner):** each job runs in its own thread.
`sys.stdout` is routed per-thread into that job's log buffer (a global
`redirect_stdout` would bleed logs across concurrent jobs). ffmpeg/whisper
subprocesses are registered per thread so kill requests terminate the right
process.

**Worker-pull model (deploy):** the API server is intentionally LIGHT — it
never downloads/transcribes/renders. `worker.py` on your device polls for jobs,
runs the full pipeline, streams progress, uploads results to R2 (presigned),
and reports completion. Multiple workers = horizontal scaling.

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
.venv\Scripts\python.exe -m pytest tests -q   # 208 passed, 6 skipped (GPU)
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
| `GOOGLE_API_KEY` | — | Gemini key for analysis (required on the DEVICE running the pipeline) |
| `ANALYZE_MODEL` / `ANALYZE_MODEL_FALLBACK` | `gemini-flash-latest` / `gemini-3.6-flash` | Gemini model + auto-fallback on quota 429 (free-tier 20 req/day per model) |
| `WHISPER_MODEL` | `large-v3-turbo` | Whisper model (local dir `models/` wins if present) |
| `WHISPER_DEVICE` | `cuda` | `cuda` or `cpu` |
| `MAX_CONCURRENT_JOBS` | `2` | Parallel jobs; set `1` if 2 transcriptions OOM a 4GB GPU |
| `CONFIDENCE_THRESHOLD` | `0.6` | Min segment confidence kept |
| `VIDEO_DOWNLOAD_RESOLUTION` | `720` | Max height for the video stream |
| `STORAGE_RETENTION_DAYS` | `14` | Raw videos / tracks kept before cleanup |
| `CHUNK_DURATION_MIN` / `CHUNK_OVERLAP_MIN` | `20` / `2` | Transcript chunking for Gemini |
| `REFRAME_*` | see example | Camera: zoom range, head bias, snap-fixed-zoom anchors |
| `REFRAME_TRACK_STEP` / `_IMGSZ` / `_CACHE` | `3` / `320` / `true` | YOLO tracking subsample, input size, cache |
| `WORKER_QUEUE` | `false` | Job queue mode (server does NOT run pipeline — workers claim jobs) |
| `WORKER_TOKEN` | `""` | Bearer token for worker endpoints (claim/progress/result) |
| `DATABASE_URL` | `""` | Postgres (e.g. Supabase) for prod queue; empty = SQLite (local/dev/test) |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | — | Cloudflare R2 credentials (server-side only — workers use presigned URLs) |
| `R2_PUBLIC_URL` | `""` | Public R2 domain so the UI can load clip URLs |
| `FRONTEND_ORIGINS` | `http://localhost:5173` | CORS allowlist (comma-separated) |
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

### Worker-pull mode (pipeline on your device)

Run the API server (lightweight) anywhere, then run the worker on the machine
that has the GPU:

```bash
# Terminal 1 — API server (env: WORKER_QUEUE=true, WORKER_TOKEN=..., DATABASE_URL=...)
.venv\Scripts\python.exe -m uvicorn server:app --port 8180

# Terminal 2 — device worker (env: API_URL, WORKER_TOKEN, GOOGLE_API_KEY, WHISPER_DEVICE=cuda)
.venv\Scripts\python.exe worker.py
```

The worker claims jobs, runs the full pipeline locally, uploads results to R2
via presigned URLs, and reports progress — the API server never touches heavy
compute.

### Usage flow

1. **Paste a YouTube URL** — title & thumbnail appear instantly
2. Pick a **niche preset** (default: Affiliate)
3. Click **Bikin Klip** — watch the live pipeline log
4. When done, open the episode → review clips → mark Reviewed/Posted,
   copy affiliate caption + hashtags, or reject (deletes the files)
5. **Gaya subtitle** — tweak font/style, preview live (≡ final burn), re-burn non-blocking
6. **Render ulang kamera** — re-run reframe+caption with current camera mode
7. **Hapus episode** — kills running work, deletes DB rows + all files

## API Reference

Base URL: `http://localhost:8180`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/jobs` | Create job `{url, preset?}` → `{job_id, status}` |
| GET | `/api/jobs` | List jobs (`?limit=&offset=`, paginated, max 200) |
| GET | `/api/jobs/{id}` | Job detail (incl. `running`, stages, notice) |
| DELETE | `/api/jobs/{id}` | Kill + delete DB rows + all files (non-blocking joins) |
| POST | `/api/jobs/{id}/kill` | Kill a running job (also routes to active re-burn) |
| POST | `/api/jobs/{id}/retry` | Resume/repair pipeline (skips completed stages) |
| POST | `/api/jobs/{id}/re-render` | Delete reframed+final, re-run reframe & caption |
| GET | `/api/jobs/{id}/log` | SSE stream of pipeline logs (cursor-based, worker-mode replay) |
| GET | `/api/jobs/{id}/segments` | Product segments (worker-mode: R2 URLs merged) |
| POST | `/api/segments/{id}/reviewed` | Toggle reviewed flag |
| POST | `/api/segments/{id}/posted` | Toggle posted flag |
| POST | `/api/segments/{id}/reject` | Delete segment + files |
| GET | `/api/scrape?q=&min_duration=` | YouTube search (Gemini expander + relevance scoring) |
| POST | `/api/jobs/claim` | Worker: claim next queued job (atomic, stale-recoverable) |
| POST | `/api/jobs/{id}/heartbeat` | Worker: extend claim (owner-only) |
| POST | `/api/jobs/{id}/progress` | Worker: batch log lines + status |
| POST | `/api/jobs/{id}/upload-url` | Worker: presigned PUT URL for R2 |
| POST | `/api/jobs/{id}/result` | Worker: report done/failed/killed + segments + uploads |
| GET | `/api/jobs/{id}/uploads` | Upload list with public R2 URLs |
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
│   │   ├── r2.py              # R2 presigned PUT + public URLs
│   │   └── gpu_cleanup.py     # Torch/whisper memory release
│   ├── worker.py              # Device worker: claim → pipeline → upload → report
│   ├── db/
│   │   ├── jobs.py            # JobDB (SQLite) + queue methods (atomic claim)
│   │   ├── pg.py              # Postgres wrapper (DATABASE_URL) — same API
│   │   ├── schema.sql         # SQLite schema
│   │   └── schema.pg.sql      # Postgres schema
│   ├── prompts/               # Preset prompts (affiliate, podcast, …)
│   ├── assets/fonts + fonts/  # Bundled OFL fonts
│   ├── tests/                 # 208 tests (pytest) incl. E2E synthetic + queue
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx            # Shell: polling, job creation, layout
│   │   ├── components/        # JobsView, JobDetail, SegmentCard, StyleEditor…
│   │   ├── lib/               # API client, stages, clipboard, caption defaults
│   │   └── main.tsx           # Entry + ErrorBoundary
│   └── package.json
├── Dockerfile                 # Container build (API server — lightweight)
└── .dockerignore
```

## Testing

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests -q
# 208 passed, 6 skipped (GPU-dependent tests skip without NVIDIA hardware)

cd ../frontend
npx tsc --noEmit
```

Coverage highlights: orchestrator retry/kill semantics, SSE log sequence
survival across retries + replay-done marker, stdout per-thread routing
(2 concurrent jobs), caption kill-awareness + emoji natural rendering +
preview/burn parity, ingest partial-file recovery, queue claim atomicity
(claim/heartbeat/stale recovery), worker-pull API flow (claim → progress →
presigned upload → result), E2E clip→caption chain with synthetic video,
tracker + camera anchors, golden transcript fixtures.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| Download fails with `403 Forbidden` / JS challenge | Deno missing. Install: `winget install DenoLand.Deno`, then restart the backend |
| Studio is empty after creating a job | Backend not restarted since a code change — uvicorn `--reload` handles this; check DB (`data/jobs.db` or `DATABASE_URL`) |
| Progress bar stuck at 0% | Old frontend cache — hard refresh (Ctrl+Shift+R); bar maps backend status → stage |
| Progress bar glitches on refresh | Fixed — SSE `replay-done` marker; progress is only parsed from live lines |
| Transcribe OOM with 2 jobs | Set `MAX_CONCURRENT_JOBS=1` |
| Analyze reports "0 segments" but video clearly has products | Check server logs for Gemini 429 quota — all-chunks-failed now shows a clear error, not a fake 0 |
| Reburn appears to hang | It's non-blocking: watch toast + per-clip progress; status at `/reburn-status` |
| Reburn result became landscape | Reframed was cleaned up → re-burn auto re-frames first (fixed); re-run via "Render ulang kamera" if needed |
| Subtitle doesn't match preview | Should be impossible (shared filter engine, pixel-verified) — update backend if you still see drift |
| Emojis look plain white | libass 0.17 renders emoji monochrome (no COLR) — outline removed on purpose; document as limitation |
| Clips look green in Chrome | ffmpeg NVENC + rawvideo colorspace bug — handled automatically (forced yuv420p + BT.601 tags) |
| No subtitles in final clip | Style has `enabled: false`, or the `.ass` was missing (now guarded — re-burn repairs) |
| Windows: port already in use | `start.bat` refuses and suggests a different port |

## License

Private project. Bundled fonts are SIL Open Font License; `yolo11n.pt` is AGPL
(Ultralytics) — check your distribution terms.
