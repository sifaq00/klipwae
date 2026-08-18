"""Worker device: jalankan pipeline penuh LOKAL (download → transcribe →
analyze → clip → reframe → caption), lapor ke server, upload hasil ke R2
via presigned URL.

Cara pakai (env):
  API_URL=http://<server>/api    WORKER_TOKEN=xxx    WORKER_ID=nama-device
  python worker.py

Pola: pull-job + heartbeat + batch-progress + presigned-upload. Server tak
pernah lihat R2 credentials worker (presigned dari server).
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

API_URL = os.environ.get("API_URL", "http://localhost:8180/api").rstrip("/")
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
WORKER_ID = os.environ.get("WORKER_ID", "worker-1")
POLL_SEC = int(os.environ.get("WORKER_POLL_SEC", "5"))
HEARTBEAT_SEC = int(os.environ.get("WORKER_HEARTBEAT_SEC", "30"))

sys.path.insert(0, str(Path(__file__).parent))

_log_buf: list[str] = []
_last_flush = time.time()


def _append_log(msg: str):
    """Append ke buffer progress (tanpa print — dipanggil proxy stdout)."""
    global _last_flush
    _log_buf.append(msg)
    if len(_log_buf) >= 20 or time.time() - _last_flush > 5:
        _flush_logs()


class _WorkerStdout:
    """Mirror server._ThreadRoutedStdout: stages print progress via
    print()/sys.stdout (analyze/clip/caption/transcribe) — tanpa proxy ini
    progress chunk/whisper/download hanya di console worker, SSE UI kosong
    (bar stuck 0%). Route ke _log → job_logs → SSE. Console worker tetap."""

    def write(self, s: str):
        sys.__stdout__.write(s)  # console tetap tampil
        if s.strip():
            _append_log(s)
        return len(s)

    def flush(self):
        sys.__stdout__.flush()
        _flush_logs()


sys.stdout = _WorkerStdout()


def _log(msg: str):
    """Log ke stdout (console) + buffer → POST batch ke server (SSE UI)."""
    sys.__stdout__.write(msg + "\n")
    sys.__stdout__.flush()
    _append_log(msg)


def _api_retry(method: str, path: str, max_tries: int = 3, **kw):
    """POST result/upload penting — at-least-once: gagal jaringan → retry,
    kalau tetap gagal job tak lapor → server re-claim (duplikat proses)."""
    last = None
    for attempt in range(max_tries):
        try:
            return _api(method, path, **kw)
        except Exception as e:
            last = e
            print(f"[worker] {path} gagal ({attempt+1}/{max_tries}): {e}", flush=True)
            time.sleep(2 * (attempt + 1))
    raise last


def _api(method: str, path: str, **kw):
    kw.setdefault("headers", {})["Authorization"] = f"Bearer {WORKER_TOKEN}"
    kw["headers"]["X-Worker-Id"] = WORKER_ID
    kw.setdefault("timeout", 60)
    r = requests.request(method, f"{API_URL}{path}", **kw)
    r.raise_for_status()
    return r.json() if r.content else {}


def _flush_logs():
    global _log_buf, _last_flush
    if not _log_buf or not _current_job:
        return
    buf, _log_buf = _log_buf, []
    try:
        _api_retry("POST", f"/jobs/{_current_job}/progress", json={"lines": buf})
        _last_flush = time.time()
    except Exception as e:
        _log_buf = buf + _log_buf  # retry di flush berikutnya
        print(f"[worker] progress gagal: {e}", flush=True)


_current_job: str | None = None


def _heartbeat_loop(job_id: str, stop: list[bool]):
    import runtime
    while not stop[0]:
        try:
            _api("POST", f"/jobs/{job_id}/heartbeat")
            # cancel channel: user kill di UI → status killed → berhenti LOKAL.
            # Scoped: kill_job(job_id, ident) — jangan kill_all (shutdown
            # global tak pernah clear → worker brick utk semua job berikutnya).
            status = _api("GET", f"/jobs/{job_id}")["status"]
            if status == "killed":
                print("[worker] job dibatalkan user — berhenti", flush=True)
                runtime.kill_job(job_id, threading.get_ident())
                stop[0] = True
                return
        except Exception:
            pass  # claim expired → worker lain ambil; kita berhenti saat pipeline selesai
        time.sleep(HEARTBEAT_SEC)


def _upload_files(job_id: str, files: dict[str, Path], kind: str) -> list[dict]:
    """Upload file ke R2 via presigned PUT. files = {r2_key: local_path}."""
    uploaded = []
    for key, path in files.items():
        ctype = "text/plain" if path.suffix == ".ass" else "video/mp4"
        put_url = _api("POST", f"/jobs/{job_id}/upload-url",
                       json={"key": key, "content_type": ctype})["put_url"]
        with open(path, "rb") as fh:
            r = requests.put(put_url, data=fh,
                             headers={"Content-Type": ctype}, timeout=600)
        r.raise_for_status()
        uploaded.append({"key": f"clips/{job_id}/{key}", "name": path.name, "kind": kind})
        _log(f"    upload {path.name} → R2")
    return uploaded


def _run_job(job: dict):
    """Proses 1 job: pipeline lokal + upload + lapor."""
    global _current_job
    job_id = job["job_id"]
    _current_job = job_id

    import runtime
    import threading
    from config import Settings
    from db.jobs import JobDB
    from orchestrator import run_pipeline
    from stages.base import StageStatus

    stop = [False]
    threading.Thread(target=_heartbeat_loop, args=(job_id, stop), daemon=True).start()

    db = JobDB()
    db.create_job(job_id, job["url"], preset=job.get("preset") or "affiliate")
    # set_job WAJIB sebelum reset: tanpa ini _job_stops[job_id] tak dibuat →
    # kill_job dari heartbeat = no-op, procs tak ter-ikat ke job → cancel
    # dari UI tak pernah berhentikan pipeline (mirror JobRunner._run).
    runtime.set_job(job_id)
    runtime.reset()
    # stop[] di-set HANYA di akhir (setelah result POST): heartbeat harus
    # hidup SELAMA upload (2-3GB > 120s stale) supaya claim tak diambil
    # worker lain + cancel channel tetap terbuka.
    try:
        try:
            result = run_pipeline(job_id, db, Settings(), log_func=_log)
        except Exception as e:
            result = None
            _log(f"[worker] pipeline exception: {e}")

        _flush_logs()

        if runtime.stop_requested():
            status, stage, err = "killed", None, "Killed"
        elif result is None:
            status, stage, err = "failed", "pipeline", "exception"
        elif result.status != StageStatus.DONE:
            status, stage, err = "failed", getattr(result, "failed_stage", None), result.error
        else:
            status, stage, err = "done", None, None
    except Exception as e:
        status, stage, err = "failed", "pipeline", str(e)[:500]

    # upload hasil final (kecuali killed total tanpa file)
    uploads = []
    if status == "done":
        try:
            final_dir = Path("data/clips_final")
            mp4s = sorted(final_dir.glob(f"{job_id}_*.mp4"))
            if mp4s:
                uploads += _upload_files(job_id, {p.name: p for p in mp4s}, "clip")
            ass = sorted(final_dir.glob(f"{job_id}_*.ass"))
            if ass:
                uploads += _upload_files(job_id, {p.name: p for p in ass}, "ass")
            seg_path = Path("data/segments") / f"{job_id}.json"
            segments = json.loads(seg_path.read_text(encoding="utf-8")) if seg_path.exists() else []
        except Exception as e:
            _log(f"[worker] upload gagal: {e}")
            status, stage, err = "failed", "upload", str(e)[:500]
            segments = []
    else:
        segments = []

    # lapor hasil (retry at-least-once) — HANYA setelah ini stop heartbeat
    body = {"status": status, "segments": segments, "uploads": uploads}
    if err:
        body["error"] = err
        body["failed_stage"] = stage
    try:
        _api_retry("POST", f"/jobs/{job_id}/result", json=body)
    except Exception as e:
        print(f"[worker] result TIDAK terkirim: {e}", flush=True)
    stop[0] = True
    _log(f"[worker] {job_id}: {status}")
    _current_job = None

    # #4: bersihkan artefak lokal setelah upload sukses — device disk
    # tumbuh ~2-3GB/job tanpa ini (raw + clips + final + tracks).
    if status == "done":
        _cleanup_job_files(job_id)


def _cleanup_job_files(job_id: str):
    """Hapus file lokal job (raw/klip/final/tracks/transcript/segments).
    Semua sudah di-upload ke R2 + laporan result — aman dibuang."""
    removed = 0
    for d in ("raw", "clips_raw", "clips_final", "tracks", "transcripts", "segments"):
        for p in (Path("data") / d).glob(f"{job_id}_*"):
            try:
                if p.is_dir():
                    import shutil
                    shutil.rmtree(p)
                else:
                    p.unlink()
                removed += 1
            except OSError:
                pass
    if removed:
        print(f"[worker] cleanup: {removed} file lokal dihapus", flush=True)


def main():
    if not WORKER_TOKEN:
        print("WORKER_TOKEN wajib di env", file=sys.stderr)
        sys.exit(1)
    _log(f"[worker] {WORKER_ID} menunggu job → {API_URL}")
    while True:
        try:
            resp = _api("POST", "/jobs/claim")
            job = resp.get("job")
            if not job:
                time.sleep(POLL_SEC)
                continue
            _log(f"[worker] claim {job['job_id']} ({job['url']})")
            _run_job(job)
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                print(f"[worker] token ditolak: {e}", file=sys.stderr)
                sys.exit(1)
            print(f"[worker] HTTP {e}", flush=True)
            time.sleep(POLL_SEC)
        except Exception as e:
            print(f"[worker] error: {e}", flush=True)
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()