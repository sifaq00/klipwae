import asyncio
import io
import logging
import logging.handlers
import os
import sys
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

import runtime
from config import Settings
from db.jobs import JobDB, init_db
from orchestrator import run_pipeline
from stages.base import StageStatus
from stages.ingest import extract_video_id
from utils.url_validator import is_valid_youtube_url


init_db()

DATA_DIR = Path(__file__).parent / "data"


def _setup() -> Settings:
    config = Settings()

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        str(log_dir / f"clipper_{date.today().isoformat()}.log"),
        maxBytes=10 * 1024 * 1024, backupCount=7, encoding="utf-8",
    )

    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    # _setup dipanggil per request (create_job/retry) — jangan nambah handler
    # baru tiap kali, nanti baris log ke-duplikat & handler bocor.
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        root.addHandler(file_handler)
    if config.log_level:
        root.setLevel(config.log_level.upper())
    return config

JOB_RUNNERS: dict[str, "JobRunner"] = {}


def _cleanup_stale_files():
    """Retention: buang artefak yang lewat STORAGE_RETENTION_DAYS.
    Raw video sekarang DISIMPAN (reprocess gak download ulang) — tapi tidak
    boleh menumpuk selamanya: hapus yang mtime-nya lebih tua dari retention."""
    import time as _t
    try:
        from config import Settings
        days = Settings().storage_retention_days or 14
        cutoff = _t.time() - days * 86400
        for dirpath in ("raw", "clips_raw", "clips_final", "tracks"):
            d = DATA_DIR / dirpath
            if not d.exists():
                continue
            for p in d.iterdir():
                try:
                    if p.is_file() and p.stat().st_mtime < cutoff:
                        p.unlink(missing_ok=True)
                except OSError:
                    pass
    except Exception:
        pass
_REBURN: dict[str, threading.Thread] = {}
_REBURN_STATUS: dict[str, str] = {}
# Counter log ABSOLUT per job — PERSISTEN antar retry/runner. Runner baru
# me-reset buffer, tapi klien SSE pakai sejak absolut: tanpa ini, retry
# langsung bikin SSE klien beku (sejak nembus buffer baru yang kosong).
_JOB_LOG_SEQ: dict[str, int] = {}
_JOB_LOG_LOCK = threading.Lock()  # seq bump + append harus atomik antar worker thread

JOB_LOG_DIR = Path(__file__).parent / "data" / "job_logs"


def _job_log_path(job_id: str) -> Path:
    return JOB_LOG_DIR / f"{job_id}.log"


class _LogStream(io.TextIOBase):
    """Stream per thread job — progress whisper/yt-dlp/stages masuk ke
    SSE + file log job-nya (bukan hilang di console)."""

    def __init__(self, log):
        self._log = log
        self._buf = ""

    def write(self, s: str):
        self._buf += s
        lines = self._buf.split("\n")
        self._buf = lines.pop()
        for line in lines:
            if line.strip():
                self._log(line.rstrip())
        return len(s)

    def flush(self):
        if self._buf.strip():
            self._log(self._buf.rstrip())
            self._buf = ""


class _ThreadRoutedStdout(io.TextIOBase):
    """sys.stdout global — tapi route per-thread ke log job masing-masing.
    Tanpa ini 2 job jalan bareng race: redirect_stdout menimpa sys.stdout
    global, print job A bocor ke buffer/SSE job B (progress bar saling
    tumpang tindih). Thread tanpa stream jatuh ke console."""

    def __init__(self, fallback):
        self._fallback = fallback

    def write(self, s: str) -> int:
        stream = JobRunner._thread_streams.get(threading.get_ident())
        if stream is not None:
            return stream.write(s)
        return self._fallback.write(s)

    def flush(self):
        stream = JobRunner._thread_streams.get(threading.get_ident())
        if stream is not None:
            stream.flush()
        else:
            self._fallback.flush()


def _install_stdout_proxy():
    """Pasang sekali per proses: semua output stdout lewat proxy, bukan
    redirect global yang di-race antar thread job."""
    global _STDOUT_PROXY
    if _STDOUT_PROXY is None:
        _STDOUT_PROXY = _ThreadRoutedStdout(sys.stdout)
        sys.stdout = _STDOUT_PROXY


_STDOUT_PROXY = None


class JobRunner:
    _thread_streams: dict[int, _LogStream] = {}  # thread ident → stream job-nya

    def __init__(self, job_id: str, url: str, preset: str = "affiliate"):
        self.job_id = job_id
        self.url = url
        self.preset = preset or "affiliate"
        self.thread: threading.Thread | None = None
        self.log_buffer: deque[tuple[int, str]] = deque(maxlen=500)
        self._log_event = threading.Event()
        self._done = threading.Event()

    def start(self):
        config = _setup()
        self.thread = threading.Thread(
            target=self._run, args=(config,), daemon=True
        )
        self.thread.start()

    def _run(self, config: Settings):
        db = JobDB()
        stream = _LogStream(self._log)
        JobRunner._thread_streams[threading.get_ident()] = stream
        _install_stdout_proxy()
        try:
            runtime.set_job(self.job_id)
            db.create_job(self.job_id, self.url, preset=self.preset)
            run_pipeline(self.job_id, db, config, log_func=self._log)
        finally:
            JobRunner._thread_streams.pop(threading.get_ident(), None)
            db.close()
            runtime.clear_job(self.job_id)
            runtime.unregister(self.thread.ident)
            # Runner selesai (done/failed/killed) — pop dari registry biar tidak
            # menumpuk: log job tetap kebaca via file (stream_log fallback disk).
            if JOB_RUNNERS.get(self.job_id) is self:
                JOB_RUNNERS.pop(self.job_id, None)
        self._done.set()
        self._log_event.set()

    def _log(self, msg: str):
        # Lock: _log dipanggil dari banyak worker thread (clip/caption pool)
        # bareng → get+set seq tak atomik, dua baris bisa share seq/terbalik.
        with _JOB_LOG_LOCK:
            seq = _JOB_LOG_SEQ.get(self.job_id, 0) + 1
            _JOB_LOG_SEQ[self.job_id] = seq
            self.log_buffer.append((seq, msg))
        self._log_event.set()
        # Persist per job — log tetap kebaca setelah server restart
        try:
            JOB_LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(_job_log_path(self.job_id), "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except OSError:
            pass

    def kill(self):
        # Stop thread job INI + terminate semua subprocess-nya (termasuk
        # ffmpeg worker) — job lain yang berjalan bareng tidak tersentuh.
        if self.thread is not None and self.thread.ident:
            runtime.kill_job(self.job_id, self.thread.ident)
        # Jangan timpa status FINAL (done/failed) yang sudah ditulis pipeline —
        # kill setelah selesai = no-op status (window: pipeline belum set _done
        # tapi sudah nulis status final; kecil & percaya pada final).
        if not self._done.is_set():
            self._job_status("killed")
        self._done.set()

    def _job_status(self, status: str):
        db = JobDB()
        try:
            db.mark_job_status(self.job_id, status)
        finally:
            db.close()

    @property
    def is_alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def recent_logs(self, since: int = 0) -> list[str]:
        """Baris sejak index ABSOLUT `since` (exclusive). Buffer cuma 500
        terakhir, index persisten per job lintas retry/runner. Klien yang
        ketinggalan jauh (since di bawah window) di-replay seluruh buffer —
        dulu slice kosong → SSE beku diam-diam."""
        buf = list(self.log_buffer)
        if not buf:
            return []
        if since < buf[0][0]:
            return [m for _, m in buf]
        return [m for s, m in buf if s > since]


# ─── Lifespan ────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _cleanup_stale_files()
    yield
    for runner in JOB_RUNNERS.values():
        if runner.is_alive:
            runner.kill()


app = FastAPI(title="Auto-Clipper API", lifespan=lifespan)
# Self-use tool: hanya izinkan origin frontend dev. Jangan "*" — API ini
# bisa menjalankan job berat & menulis .env.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_store(request, call_next):
    """API selalu fresh — tanpa ini Chrome heuristik-cache GET segments,
    polling progress re-burn nemu data basi (0/10 terus sampai cache expire)."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response
app.mount("/clips", StaticFiles(directory=str(DATA_DIR)), name="clips")


# ─── Models ──────────────────────────────────────────────────────────────────


class JobCreate(BaseModel):
    url: str
    preset: str = "affiliate"


CreateJobRequest = JobCreate


class SettingsUpdate(BaseModel):
    whisper_model: str | None = None
    whisper_device: str | None = None
    google_api_key: str | None = None


# --- Helpers -------------------------------------------------------------


def _job_json(job: dict) -> dict:
    if not job.get("preset"):
        job["preset"] = "affiliate"
    return job


# --- Endpoints -----------------------------------------------------------


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/scrape")
async def scrape_links(q: str = "", url: str = "", limit: int = 50, min_duration: int = 0):
    """Scraper: natural-language search (q) atau channel/playlist (url) →
    daftar video YouTube (metadata saja, cepat, tanpa download).

    Mode q: Gemini expand query → multi-query → skor relevansi → urutkan
    (Lapis 1+3). min_duration > 0: filter video pendek (podcast = panjang).
    """
    from utils.scraper import scrape_channel, scrape_multi
    try:
        if url:
            if not is_valid_youtube_url(url):
                raise HTTPException(400, "Invalid YouTube URL")
            items = scrape_channel(url, limit=limit)
        elif q.strip():
            items = scrape_multi(q.strip(), limit=limit, min_duration=min_duration)
        else:
            raise HTTPException(400, "Param 'q' (search) atau 'url' (channel/playlist) wajib")
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    return {"items": items, "count": len(items)}


@app.post("/api/jobs")
async def create_job(body: JobCreate):
    if not is_valid_youtube_url(body.url):
        raise HTTPException(400, "Invalid YouTube URL")
    video_id = extract_video_id(body.url)
    if not video_id:
        raise HTTPException(400, "Cannot extract video ID")
    if video_id in JOB_RUNNERS and JOB_RUNNERS[video_id].is_alive:
        raise HTTPException(409, "Job already running")

    config = _setup()
    active = sum(1 for r in JOB_RUNNERS.values() if r.is_alive)
    if active >= config.max_concurrent_jobs:
        raise HTTPException(
            429,
            f"Masih ada {active} job berjalan (maks {config.max_concurrent_jobs}). Tunggu selesai atau kill dulu.",
        )

    preset = body.preset or "affiliate"
    runner = JobRunner(video_id, body.url, preset=preset)
    JOB_RUNNERS[video_id] = runner
    # INSERT dulu: _fetch_meta_early (UPDATE) tak boleh kalah sama INSERT
    # runner thread ? kalau 0 rows, title awal diam-diam hilang.
    db0 = JobDB()
    try:
        db0.create_job(video_id, body.url, preset=preset)
    finally:
        db0.close()
    runner.start()
    # Judul/channel/duration langsung dari YouTube (tanpa download) — UI
    # menampilkan judul + thumbnail sejak menit pertama, bukan nunggu
    # download selesai. Ingest tetap ambil metadata lagi setelah download
    # (fallback konsisten, update idempoten).
    threading.Thread(target=_fetch_meta_early, args=(video_id, body.url), daemon=True).start()
    return {"job_id": video_id, "status": "started", "preset": preset}


def _fetch_meta_early(job_id: str, url: str):
    """Judul/channel/duration langsung dari YouTube (tanpa download) — UI
    menampilkan judul + thumbnail sejak menit pertama, bukan nunggu download
    selesai. Ingest tetap ambil metadata lagi setelah download (fallback
    konsisten, update idempoten)."""
    from stages.ingest import get_yt_metadata
    try:
        meta = get_yt_metadata(url, timeout=30)
        if not meta or meta.get("title") is None or meta.get("duration") is None:
            return
        db = JobDB()
        try:
            db.update_job_metadata(
                job_id,
                title=meta.get("title"),
                duration_sec=meta.get("duration"),
                channel=meta.get("channel"),
            )
        finally:
            db.close()
    except Exception:
        logging.getLogger(__name__).debug("fetch_meta_early failed", exc_info=True)


@app.get("/api/jobs")
async def list_jobs(limit: int = 50, offset: int = 0):
    db = JobDB()
    try:
        rows = db.conn.execute(
            "SELECT j.*, (SELECT COUNT(*) FROM segments s WHERE s.job_id = j.id) AS segment_count "
            "FROM jobs j ORDER BY j.created_at DESC LIMIT ? OFFSET ?",
            (min(max(limit, 1), 200), max(offset, 0)),
        ).fetchall()
        result = []
        for r in rows:
            job = _job_json(dict(r))
            runner = JOB_RUNNERS.get(job["id"])
            job["running"] = runner is not None and runner.is_alive
            result.append(job)
        return result
    finally:
        db.close()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    db = JobDB()
    try:
        row = db.conn.execute(
            "SELECT * FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        job = _job_json(dict(row))
        runner = JOB_RUNNERS.get(job_id)
        job["running"] = runner is not None and runner.is_alive
        stages = db.conn.execute(
            "SELECT * FROM stage_runs WHERE job_id=? ORDER BY started_at",
            (job_id,),
        ).fetchall()
        job["stages"] = [dict(s) for s in stages]
        return job
    finally:
        db.close()


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    """Hapus episode total: kill kalau jalan, DB rows, semua file terkait."""

    async def _join_quiet(thread) -> None:
        # asyncio.to_thread: thread.join sync TIDAK boleh nge-blok event loop
        # (semua SSE stream & request ikut beku 10-20s).
        try:
            await asyncio.to_thread(thread.join, 10)
        except Exception:
            pass

    runner = JOB_RUNNERS.get(job_id)
    if runner and runner.is_alive:
        runner.kill()
        # Jangan langsung hapus file: thread yang masih jalan bisa nulis
        # ulang file yang baru dihapus (zombie). Tunggu thread berhenti.
        await _join_quiet(runner.thread)

    # Reburn masih jalan untuk job ini? terminate + tunggu berhenti dulu
    reburn = _REBURN.get(job_id)
    if reburn and reburn.is_alive():
        runtime.kill_job(job_id, reburn.ident)
        await _join_quiet(reburn)
    _REBURN.pop(job_id, None)
    _REBURN_STATUS.pop(job_id, None)

    db = JobDB()
    try:
        # Anak dulu baru parent (FK constraint)
        for t in ("metrics", "stage_runs", "segments"):
            db.conn.execute(f"DELETE FROM {t} WHERE job_id=?", (job_id,))
        db.conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        db.conn.commit()
    finally:
        db.close()

    # Hapus file: raw, transcript, segments, clips (raw+reframed), final, thumb, ass, log.
    # Pass kedua: kalau thread masih hidup setelah join(10) (mis. whisper), dia bisa
    # menulis ulang file yang baru dihapus — tunggu dia mati lalu hapus lagi.
    def _delete_files() -> int:
        removed = 0
        patterns = [
            DATA_DIR / "raw" / f"{job_id}.*",
            DATA_DIR / "transcripts" / f"{job_id}.*",
            DATA_DIR / "segments" / f"{job_id}.*",
            DATA_DIR / "clips_raw" / f"{job_id}_*",
            DATA_DIR / "clips_final" / f"{job_id}_*",
            DATA_DIR / "tracks" / f"{job_id}_*",
            JOB_LOG_DIR / f"{job_id}.log",
        ]
        for pattern in patterns:
            for p in pattern.parent.glob(pattern.name) if "*" in pattern.name else [pattern]:
                try:
                    if p.exists() and p.name != "_style_preview.png":
                        p.unlink()
                        removed += 1
                except OSError:
                    pass
        return removed

    removed = _delete_files()
    if (runner and runner.is_alive) or (reburn and reburn.is_alive()):
        for t in (runner, reburn):
            thread = t.thread if hasattr(t, "thread") and t.thread else t
            if thread and thread.is_alive():
                await _join_quiet(thread)
        removed += _delete_files()
    JOB_RUNNERS.pop(job_id, None)
    return {"status": "deleted", "files_removed": removed}


@app.post("/api/jobs/{job_id}/kill")
async def kill_job(job_id: str):
    runner = JOB_RUNNERS.get(job_id)
    if not runner:
        raise HTTPException(404, "Job tidak sedang jalan")
    runner.kill()
    return {"status": "kill_requested"}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    if job_id in JOB_RUNNERS and JOB_RUNNERS[job_id].is_alive:
        raise HTTPException(409, "Job already running")

    db = JobDB()
    try:
        row = db.conn.execute(
            "SELECT * FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        db.mark_job_status(job_id, "pending", failed_stage=None, error=None)
        row_dict = dict(row)
        preset = row_dict.get("preset") or "affiliate"
    finally:
        db.close()

    runner = JobRunner(job_id, row_dict["url"], preset=preset)
    JOB_RUNNERS[job_id] = runner
    runner.start()
    return {"job_id": job_id, "status": "restarted"}


@app.get("/api/jobs/{job_id}/log")
async def stream_log(job_id: str, since: int = 0):
    runner = JOB_RUNNERS.get(job_id)
    if not runner:
        # Job lama / server restart: baca log persisten dari disk
        log_path = _job_log_path(job_id)
        lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
        lines = lines[since:]

        async def replay():
            for line in lines:
                yield {"event": "log", "data": line}
                await asyncio.sleep(0)
            yield {"event": "done", "data": ""}

        return EventSourceResponse(replay())

    async def event_generator():
        idx = since
        replay_done = False
        while True:
            logs = runner.recent_logs(idx)
            for line in logs:
                yield {"event": "log", "data": line}
                await asyncio.sleep(0)
            idx += len(logs)
            if not replay_done and len(logs) == 0:
                # Buffer replay selesai — frontend skip parseProgress selama
                # replay (hard refresh: baris progress LAMA bikin bar menari
                # download→…→reframe). Baris berikutnya = LIVE.
                yield {"event": "replay-done", "data": ""}
                replay_done = True
            if not runner.is_alive:
                remaining = runner.recent_logs(idx)
                for line in remaining:
                    yield {"event": "log", "data": line}
                if not replay_done:
                    # Runner mati bisa break sebelum marker sempat keluar —
                    # pastikan marker tetap terkirim sebelum done.
                    yield {"event": "replay-done", "data": ""}
                yield {"event": "done", "data": ""}
                break
            try:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, runner._log_event.wait, 1
                    ),
                    timeout=5,
                )
                runner._log_event.clear()
            except (asyncio.TimeoutError, Exception):
                pass

    return EventSourceResponse(event_generator())


@app.get("/api/jobs/{job_id}/segments")
async def get_segments(job_id: str):
    db = JobDB()
    try:
        rows = db.conn.execute(
            "SELECT * FROM segments WHERE job_id=? ORDER BY id", (job_id,)
        ).fetchall()
        return [_segment_json(dict(r)) for r in rows]
    finally:
        db.close()


def _resolve_clip_path(clip_path: str) -> Path:
    """clip_path di DB relatif terhadap backend dir — normalisasi ke absolut
    supaya cek file & relative_to(DATA_DIR) konsisten."""
    clip = Path(clip_path)
    if not clip.is_absolute():
        clip = Path(__file__).parent / clip
    return clip


def _segment_json(seg: dict) -> dict:
    if isinstance(seg.get("hashtags"), str):
        try:
            seg["hashtags"] = json.loads(seg["hashtags"])
        except Exception:
            seg["hashtags"] = []
    elif seg.get("hashtags") is None:
        seg["hashtags"] = []
    if seg.get("hook_score") is None:
        seg["hook_score"] = 85
    clip_path = seg.get("clip_path")
    if clip_path:
        clip = _resolve_clip_path(clip_path)
        reframed = clip.with_name(clip.stem + "_reframed.mp4")
        final = DATA_DIR / "clips_final" / clip.name
        if final.exists():
            seg["preview_url"] = f"/clips/clips_final/{clip.name}"
            seg["caption_url"] = f"/clips/clips_final/{clip.stem}.ass"
            thumb = final.with_suffix(".jpg")
            if thumb.exists():
                seg["thumb_url"] = f"/clips/clips_final/{thumb.name}"
        elif reframed.exists():
            seg["preview_url"] = f"/clips/{reframed.relative_to(DATA_DIR).as_posix()}"
        elif clip.exists():
            seg["preview_url"] = f"/clips/{clip.relative_to(DATA_DIR).as_posix()}"
    return seg


@app.post("/api/segments/{segment_id}/reviewed")
async def mark_segment_reviewed(segment_id: int):
    return _toggle_segment(segment_id, "reviewed")


@app.post("/api/segments/{segment_id}/posted")
async def mark_segment_posted(segment_id: int):
    return _toggle_segment(segment_id, "posted")


@app.post("/api/segments/{segment_id}/reject")
async def reject_segment(segment_id: int):
    """Buang klip: hapus row segmen + semua file terkait (raw, reframed, final, .ass)."""
    db = JobDB()
    try:
        # Cek aktivitas DULU — kalau job masih proses, jangan hapus apa pun
        found = db.conn.execute(
            "SELECT job_id FROM segments WHERE id=?", (segment_id,)
        ).fetchone()
        if not found:
            raise HTTPException(404, "Segment not found")
        jid = found["job_id"]
        runner = JOB_RUNNERS.get(jid)
        reburn = _REBURN.get(jid)
        if (runner and runner.is_alive) or (reburn and reburn.is_alive()):
            raise HTTPException(409, "Job masih memproses — tunggu selesai dulu")
        row = db.delete_segment(segment_id)
    finally:
        db.close()
    removed = []
    for p in _segment_files(row):
        try:
            if p.exists():
                p.unlink()
                removed.append(p.name)
        except OSError:
            pass
    return {"id": segment_id, "status": "rejected", "files_removed": removed}


def _segment_files(seg: dict) -> list[Path]:
    files = []
    clip_path = seg.get("clip_path")
    if clip_path:
        clip = _resolve_clip_path(clip_path)
        files.append(clip)
        files.append(clip.with_name(clip.stem + "_reframed.mp4"))
        final = Path(__file__).parent / "data" / "clips_final" / clip.name
        files.append(final)
        files.append(Path(__file__).parent / "data" / "clips_final" / Path(clip.name).with_suffix(".ass"))
        files.append(final.with_suffix(".jpg"))  # thumbnail dari _make_thumb — kalau tidak, yatim
    return files


def _toggle_segment(segment_id: int, field: str) -> dict:
    _ALLOWED_TOGGLE = {"reviewed", "posted"}
    if field not in _ALLOWED_TOGGLE:
        raise HTTPException(400, f"Invalid toggle field: {field}")
    db = JobDB()
    try:
        row = db.conn.execute(
            f"SELECT {field} FROM segments WHERE id=?", (segment_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Segment not found")
        new_val = 0 if row[0] else 1
        db.conn.execute(
            f"UPDATE segments SET {field}=? WHERE id=?",
            (new_val, segment_id),
        )
        db.conn.commit()
        return {"id": segment_id, field: bool(new_val)}
    finally:
        db.close()


@app.get("/api/settings")
async def get_settings():
    config = _setup()
    return {
        "whisper_model": config.whisper_model,
        "whisper_device": config.whisper_device,
        "video_download_resolution": config.video_download_resolution,
    }


@app.put("/api/settings")
async def update_settings(body: SettingsUpdate):
    env_path = Path(__file__).parent / ".env"
    if body.whisper_model:
        _set_env(env_path, "WHISPER_MODEL", body.whisper_model)
    if body.whisper_device:
        _set_env(env_path, "WHISPER_DEVICE", body.whisper_device)
    return {"status": "updated"}


def _set_env(path: Path, key: str, value: str):
    lines = []
    found = False
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip().startswith(f"{key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")


# ─── Subtitle style ────────────────────────────────────────────────


FONT_DIRS = [
    Path(__file__).parent / "assets" / "fonts",
    Path(__file__).parent / "fonts",  # bundle project (Poppins, Montserrat, dll)
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
]
_fonts_cache: list[str] | None = None


def _font_families() -> list[str]:
    """Scan font terinstall + bundle → daftar nama family.

    Bundle project: nameID1 sudah dinormalisasi (mis. "Poppins ExtraBold").
    Sistem: nameID 16 dulu (variable font kadang nameID1 = "Montserrat Thin").
    Cache per proses.
    """
    global _fonts_cache
    if _fonts_cache is not None:
        return _fonts_cache
    from fontTools.ttLib import TTFont

    families = set()
    for d in FONT_DIRS:
        if not d.exists():
            continue
        bundled = d in (FONT_DIRS[0], FONT_DIRS[1])
        for f in list(d.glob("*.ttf")) + list(d.glob("*.otf")):
            try:
                with TTFont(str(f), fontNumber=0, lazy=True) as tt:
                    if bundled:
                        name = tt["name"].getDebugName(1)
                    else:
                        name = tt["name"].getDebugName(16) or tt["name"].getDebugName(1)
                if name and name.strip() and not name.startswith((".", "{")):
                    families.add(name.strip())
            except Exception:
                pass
    _fonts_cache = sorted(families)
    return _fonts_cache


@app.get("/api/fonts")
async def list_fonts():
    from utils.caption_style import AVAILABLE_FONTS
    return {
        "fonts": _font_families(),
        "available_fonts": AVAILABLE_FONTS,
    }


@app.post("/api/caption-style/preview")
async def caption_style_preview(body: dict):
    """Render preview REAL via libass — engine yang sama dengan burn-in.
    Gambar contoh 1080x1920 dengan gaya yang diminta → URL gambar."""
    import time as _time
    from stages.caption import generate_ass
    from utils.caption_style import DEFAULT_STYLE
    from utils.ffmpeg_helpers import run_ffmpeg

    style = {k: body.get(k, v) for k, v in DEFAULT_STYLE.items()}
    sample_words = [
        {"text": "Halo,", "start": 0.0, "end": 0.8},
        {"text": "kamu", "start": 0.8, "end": 1.4},
        {"text": "suka", "start": 1.4, "end": 2.0},
        {"text": "produk", "start": 2.0, "end": 2.7},
        {"text": "ini?", "start": 2.7, "end": 3.4},
        {"text": "Coba", "start": 3.4, "end": 4.0},
        {"text": "deh", "start": 4.0, "end": 4.6},
        {"text": "sekali", "start": 4.6, "end": 5.3},
    ]
    ass = generate_ass(sample_words, style=style.get("style", "highlight"), style_cfg=style)

    tmp_dir = DATA_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ass_path = tmp_dir / "style_preview.ass"
    ass_path.write_text(ass, encoding="utf-8")

    out_dir = DATA_DIR / "clips_final"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Path relatif + cwd: hindari escape colon drive (D\:) yang rusak di
    # filter subtitles saat input lavfi. Path absolut + escape tetap jalan
    # di burn-in (input video), tapi tidak di sini.
    # run_in_executor: ffmpeg sync (up to 60s) di thread pool — kalau
    # dieksekusi inline, SEMUA SSE stream (log job, progress) ikut beku.
    def _render() -> int:
        fonts_opt = ""
        # Pilih dir font TERBANYAK — assets/fonts cuma sisa Montserrat,
        # pack OFL lengkap di backend/fonts (lihat caption.py).
        candidates = [DATA_DIR.parent / "assets" / "fonts", DATA_DIR.parent / "fonts"]
        fonts_dir = max(
            (d for d in candidates if d.exists() and any(d.iterdir())),
            key=lambda d: sum(1 for _ in d.glob("*.ttf")),
            default=None,
        )
        if fonts_dir is not None:
            fonts_opt = f":fontsdir={fonts_dir.relative_to(DATA_DIR.parent).as_posix()}"

        return run_ffmpeg([
            "-f", "lavfi", "-i", "color=c=0x0d0d18:s=1080x1920:r=30:d=4",
            "-vf", f"subtitles={ass_path.relative_to(DATA_DIR.parent).as_posix()}{fonts_opt}",
            "-frames:v", "1",
            str((out_dir / "_style_preview.png").relative_to(DATA_DIR.parent).as_posix()),
        ], timeout=60, cwd=str(DATA_DIR.parent)).returncode

    loop = asyncio.get_running_loop()
    returncode = await loop.run_in_executor(None, _render)
    if returncode != 0:
        raise HTTPException(500, "Preview render failed")
    return {"url": f"/clips/clips_final/_style_preview.png?v={int(_time.time() * 1000)}"}


@app.get("/api/caption-style")
async def get_caption_style():
    from utils.caption_style import load_global
    return load_global()


@app.put("/api/caption-style")
async def put_caption_style(body: dict):
    from utils.caption_style import save_global, validate
    clean = validate(body)
    if clean is None:
        raise HTTPException(422, "Nilai gaya subtitle tidak valid")
    return save_global(clean)


@app.get("/api/jobs/{job_id}/caption-style")
async def get_job_caption_style(job_id: str):
    db = JobDB()
    try:
        from utils.caption_style import style_for_job
        return style_for_job(db.get_job_style(job_id))
    finally:
        db.close()


@app.put("/api/jobs/{job_id}/caption-style")
async def put_job_caption_style(job_id: str, body: dict):
    import json as _json
    from utils.caption_style import validate
    clean = validate(body)
    if clean is None:
        raise HTTPException(422, "Nilai gaya subtitle tidak valid")
    db = JobDB()
    try:
        row = db.conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        db.set_job_style(job_id, _json.dumps(clean, ensure_ascii=False))
    finally:
        db.close()
    return {"status": "saved"}


@app.post("/api/jobs/{job_id}/reburn-captions")
async def reburn_captions(job_id: str):
    """Regenerate subtitle dengan style terbaru + burn ulang semua klip final."""
    import json as _json

    if job_id in _REBURN and _REBURN[job_id].is_alive():
        raise HTTPException(409, "Reburn sudah berjalan untuk episode ini")

    def _do():
        from config import Settings
        from stages.caption import CaptionStage
        # Hapus final + thumbnail dulu supaya stage benar-benar re-burn dan
        # thumbnail di-generate ulang dengan gaya baru (bukan yang basi).
        final_dir = DATA_DIR / "clips_final"
        for p in list(final_dir.glob(f"{job_id}_*")):
            if p.name == "_style_preview.png":
                continue
            try:
                p.unlink()
            except OSError:
                pass
        db = JobDB()
        try:
            return CaptionStage().run(job_id, db, Settings())
        finally:
            db.close()

    def _wrapped():
        runtime.set_job(job_id)  # ffmpeg worker ter-ikat ke job ? ikut ke-kill
        runtime.reset()
        try:
            if runtime.stop_requested(job_id):
                _REBURN_STATUS[job_id] = "killed"
                return
            jdb = JobDB()
            try:
                from utils.caption_style import style_for_job
                enabled = style_for_job(jdb.get_job_style(job_id)).get("enabled", True)
            finally:
                jdb.close()
            if not enabled:
                _REBURN_STATUS[job_id] = "skipped"
                return
            result = _do()
            if runtime.stop_requested(job_id):
                _REBURN_STATUS[job_id] = "killed"
            elif result.status != StageStatus.DONE:
                # Bukan "done" palsu: stage FAILED (mis. transcript hilang) ?
                # frontend harusnya kasih toast gagal, bukan sukses.
                _REBURN_STATUS[job_id] = "failed"
            else:
                _REBURN_STATUS[job_id] = "done"
        except Exception as e:
            # Kalau tak di-catch, status tetap "running" ? frontend poll
            # selamanya (modal wedged). Laporkan sebagai failed.
            logging.getLogger(__name__).exception("reburn failed for %s", job_id)
            _REBURN_STATUS[job_id] = "failed"
        finally:
            runtime.clear_job(job_id)
            # JANGAN pop di sini: delete_job butuh ref thread utk join/kill
            # selama masih hidup. Entry mati di-replace saat reburn berikutnya.

    _REBURN[job_id] = threading.Thread(target=_wrapped, daemon=True)
    _REBURN_STATUS[job_id] = "running"
    _REBURN[job_id].start()

    # #20: JANGAN blokir request sampai thread selesai (gateway timeout).
    # Frontend poll /reburn-status sampai terminal.
    return {"status": "running"}


@app.get("/api/jobs/{job_id}/reburn-status")
async def reburn_status(job_id: str):
    t = _REBURN.get(job_id)
    return {
        "status": _REBURN_STATUS.get(job_id, "idle"),
        "alive": bool(t and t.is_alive()),
    }


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("BACKEND_PORT", "8180"))
    uvicorn.run(app, host="0.0.0.0", port=port)
