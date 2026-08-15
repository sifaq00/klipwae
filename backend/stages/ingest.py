import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from stages.base import Stage, StageResult, StageStatus
from stages.registry import register
import runtime


def extract_video_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None


@register
class IngestStage(Stage):
    name = "ingest"
    depends_on = []

    def is_complete(self, job_id: str, db) -> bool:
        # Plan Section 4.1 bug trap: cek file AND DB row lengkap.
        # Kalau hanya cek file, proses yang mati setelah download selesai
        # tapi sebelum metadata ke-commit akan skip stage di resume,
        # dan stage downstream (clip) dapat duration_sec=None.
        raw = Path(f"data/raw/{job_id}.mp4")
        if not raw.exists():
            return False
        # Floor 1MB: metadata BISA muncul duluan dari early-fetch (POST),
        # jadi kehadiran metadata bukan lagi bukti download sukses.
        # File parsial yang nyangkut di bawah ambang ini dianggap belum
        # selesai → retry re-download.
        if raw.stat().st_size < 1024 * 1024:
            return False
        if db is None:
            return True
        row = db.conn.execute(
            "SELECT title, duration_sec, channel, downloaded FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            return False
        # downloaded=1 HANYA di-set setelah yt-dlp returncode 0 + metadata
        # lengkap ter-tulis (mark_downloaded). Metadata + file final tak cukup:
        # kill pas ffmpeg merge bisa ninggal file parsial >1MB dengan metadata
        # early-fetch → transcribe akan jalan di video terpotong (SILENT).
        return (row["title"] is not None and row["duration_sec"] is not None
                and bool(row["downloaded"]))

    def run(self, job_id: str, db, config):
        job = db.conn.execute("SELECT url FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return StageResult(status=StageStatus.FAILED, error="Job not found")
        url = job["url"]

        raw_dir = Path("data/raw")
        raw_dir.mkdir(parents=True, exist_ok=True)
        output_path = raw_dir / f"{job_id}.mp4"

        if output_path.exists():
            # Skip download HANYA kalau marker downloaded=1 — file + metadata
            # saja tak cukup: file parsial >1MB (kill pas merge) + metadata
            # early-fetch bisa keduanya hadir. downloaded=0 → re-download
            # (yt-dlp menimpa file parsial).
            row = db.conn.execute(
                "SELECT title, duration_sec, downloaded FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if (row and row["title"] is not None and row["duration_sec"] is not None
                    and row["downloaded"]):
                return StageResult(status=StageStatus.DONE, output_path=str(output_path))
            # jatuh ke download (atau ambil metadata di bawah kalau path ini
            # dipanggil dengan file partial — else branch di bawah)
        else:
            # Cek disk space sebelum download (plan Section 10.1) — podcast 2 jam
            # di 720p bisa 500MB-1GB; butuh buffer. Gagal cepat di sini lebih baik
            # daripada gagal setelah download setengah jadi.
            free = shutil.disk_usage(raw_dir).free
            if free < 2 * 1024 ** 3:
                return StageResult(
                    status=StageStatus.FAILED,
                    error=f"Disk space kurang dari 2GB: {free // (1024 ** 3)}GB free",
                )

            proc = subprocess.Popen([
                "yt-dlp",
                "--no-playlist",
                "-f", f"bestvideo[height<={config.video_download_resolution}]+bestaudio/best[height<={config.video_download_resolution}]",
                "--merge-output-format", "mp4",
                "--newline",
                "-o", str(output_path),
                url,
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            runtime.set_proc(proc)
            try:
                # Forward progress yt-dlp ke stdout (yang di-capture ke log job)
                for line in proc.stdout:
                    print(line, end="")
                proc.wait()
            finally:
                runtime.clear_proc(proc)
            if runtime.stop_requested():
                # Killed: laporkan Killed, bukan "download failed" (status jadi
                # "killed" di orchestrator, bukan "failed")
                return StageResult(status=StageStatus.FAILED, error="Killed")
            if proc.returncode != 0:
                return StageResult(status=StageStatus.FAILED, error="yt-dlp download failed")

        metadata = get_yt_metadata(url, timeout=600)
        if not metadata or metadata.get("title") is None or metadata.get("duration") is None:
            # Gagal ambil metadata — jangan mark done, supaya is_complete
            # (yang cek DB row lengkap) tidak true. File mp4 sudah ada,
            # tapi retry akan ambil metadata lagi tanpa re-download.
            return StageResult(
                status=StageStatus.FAILED,
                error="Gagal ambil metadata (title/duration) dari YouTube",
            )
        db.update_job_metadata(
            job_id,
            title=metadata.get("title"),
            duration_sec=metadata.get("duration"),
            channel=metadata.get("channel"),
        )

        return StageResult(status=StageStatus.DONE, output_path=str(output_path))


def subprocess_run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    # utf-8 + errors=replace: judul non-ASCII (mojibake) di Windows default cp1252
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def get_yt_metadata(url: str, timeout: int = 30) -> Optional[dict]:
    """Metadata YouTube tanpa download — dipakai POST /api/jobs (cepat, UI
    langsung tampil judul/channel) DAN ingest setelah download (fallback)."""
    try:
        result = subprocess_run(
            ["yt-dlp", "--dump-json", "--no-playlist", "--skip-download", url],
            timeout=timeout,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return {
            "title": data.get("title"),
            "duration": data.get("duration"),
            "channel": data.get("channel") or data.get("uploader"),
        }
    except (json.JSONDecodeError, subprocess.TimeoutExpired):
        return None
