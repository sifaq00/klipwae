"""E2E otomatis: rantai ffmpeg NYATA (clip cut + window offset + burn-in)
dengan video sintetis — tanpa GPU, tanpa network. Reframe (YOLO) di-skip
(GPU-dependent, diuji terpisah via mock di test_render_switch)."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE = Path(__file__).parent.parent
JOB = "e2esynth"
_DATA = BASE / "data"


def _synth_video(path: Path, seconds: float = 12.0):
    """Video sintetis 640x360 + tone audio (encoding H.264 real)."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=640x360:rate=30",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac",
         "-shortest", str(path)],
        capture_output=True, check=True, timeout=120,
    )


def _cleanup():
    try:
        os.unlink(os.environ["KLIPWAE_DB_PATH"])
    except OSError:
        pass
    for d in ("raw", "clips_raw", "clips_final", "segments", "transcripts", "tracks"):
        for p in (_DATA / d).glob(f"{JOB}_*"):
            try:
                p.unlink()
            except OSError:
                pass


def test_e2e_clip_and_caption_chain():
    """ClipStage + CaptionStage end-to-end: segmen 2-8s dari video 12s →
    klip 7.5s (buf 1.5) → subtitle burn → final + .ass ada, durasi benar."""
    import runtime
    from db.jobs import JobDB, init_db
    from stages.base import StageStatus
    from stages.clip import ClipStage
    from stages.caption import CaptionStage

    init_db()
    _cleanup()
    old_cwd = os.getcwd()
    os.chdir(BASE)  # stage pakai path relatif data/... — test lain bisa ganti CWD

    try:
        raw = _DATA / "raw" / f"{JOB}.mp4"
        _synth_video(raw, 12.0)

        # segmen sintetis: 2-8s
        seg = {
            "start": 2.0, "end": 8.0,
            "product_mentioned": "Serum E2E", "topic": "review",
            "confidence": 0.9, "reason": "e2e",
        }
        (_DATA / "segments" / f"{JOB}.json").write_text(
            json.dumps([seg]), encoding="utf-8")

        # transcript sintetis: kata di 2.5-7.5s
        words = [{"text": f"kata{i}", "start": 2.5 + i * 0.5, "end": 3.0 + i * 0.5}
                 for i in range(10)]
        (_DATA / "transcripts" / f"{JOB}.json").write_text(
            json.dumps([{"text": " ", "start": 2.5, "end": 7.5, "words": words}]), encoding="utf-8")

        db = JobDB()
        db.create_job(JOB, "https://youtube.com/watch?v=e2esynth")
        from types import SimpleNamespace
        config = SimpleNamespace(clip_parallel=1, video_download_resolution=720)

        runtime.reset()
        try:
            # 1) CLIP: segmen 2-8 → klip 0.5-9.5 (buf 1.5) = 9s
            r1 = ClipStage().run(JOB, db, config)
            assert r1.status == StageStatus.DONE, r1.error
            clips = list((_DATA / "clips_raw").glob(f"{JOB}_*.mp4"))
            assert len(clips) == 1, f"klip: {clips}"
            clip = clips[0]
            assert "_reframed" not in clip.name

            from utils.video_info import get_video_info
            _, dur = get_video_info(clip)
            assert abs(dur - 9.0) < 0.5, f"durasi klip {dur} (harus 9s: 2-1.5 s/d 8+1.5)"

            # row segmen punya clip_start_sec (window aktual)
            rows = db.get_job_segments(JOB)
            assert rows and rows[0]["clip_start_sec"] == 0.5, rows

            # 2) CAPTION: burn ke final
            r2 = CaptionStage().run(JOB, db, config)
            assert r2.status == StageStatus.DONE, r2.error
            finals = list((_DATA / "clips_final").glob(f"{JOB}_*.mp4"))
            assert len(finals) == 1, f"final: {finals}"
            _, fdur = get_video_info(finals[0])
            assert abs(fdur - 9.0) < 0.5, f"durasi final {fdur}"
            ass = list((_DATA / "clips_final").glob(f"{JOB}_*.ass"))
            assert len(ass) == 1, "ass harus ada"

            # 3) Reframed dihapus setelah caption (cleanup storage)
            reframed = list((_DATA / "clips_raw").glob(f"{JOB}_*_reframed.mp4"))
            assert len(reframed) == 0, f"reframed harus dihapus: {reframed}"

            # 4) Reframe is_complete pakai stage_runs (bukan file)
            from stages.reframe import ReframeStage
            db.conn.execute(
                "INSERT INTO stage_runs (job_id, stage, status) VALUES (?, 'reframe', 'done')",
                (JOB,))
            db.conn.commit()
            assert ReframeStage().is_complete(JOB, db), "is_complete harus TRUE via stage_runs"
        finally:
            runtime.unregister(threading.get_ident())
            db.close()
    finally:
        os.chdir(old_cwd)
        _cleanup()
    print("OK test_e2e_clip_and_caption_chain")


if __name__ == "__main__":
    test_e2e_clip_and_caption_chain()
    print("all ok")