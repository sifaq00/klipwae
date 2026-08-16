"""Re-render endpoint: hapus file reframed/final lalu restart pipeline.
409 kalau job jalan; 404 kalau tak ada; files_removed benar."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server
from starlette.testclient import TestClient


def _make_job(tmp_path):
    """Buat job DB + dummy files, kembalikan TestClient context + job_id."""
    from db.jobs import JobDB, init_db
    init_db()  # pastikan tabel ada (suite order tak dijamin)
    db = JobDB()
    db.create_job("rerendertest", "https://www.youtube.com/watch?v=rerendertest")
    db.close()
    # path ABSOLUT: test lain (test_analyze) bisa ganti CWD di tengah suite
    base = Path(__file__).parent.parent
    raw = base / "data" / "clips_raw"
    final = base / "data" / "clips_final"
    raw.mkdir(parents=True, exist_ok=True)
    final.mkdir(parents=True, exist_ok=True)
    (raw / "rerendertest_000_x_reframed.mp4").write_bytes(b"r")
    (raw / "rerendertest_000_x.mp4").write_bytes(b"c")
    (final / "rerendertest_000_x.mp4").write_bytes(b"f")
    (final / "rerendertest_000_x.ass").write_bytes(b"a")
    (final / "rerendertest_000_x.jpg").write_bytes(b"j")


def test_re_render_deletes_files_and_restarts(tmp_path, monkeypatch):
    _make_job(tmp_path)
    # patch runner agar tidak benar-benar men-download
    import threading
    from types import SimpleNamespace
    from unittest.mock import patch

    fake_runner = SimpleNamespace(
        thread=SimpleNamespace(is_alive=lambda: True),
        is_alive=True, kill=lambda: None,
        start=lambda: None, job_id="rerendertest", url="x",
    )
    with patch.object(server, "JobRunner", return_value=fake_runner):
        with TestClient(server.app) as client:
            r = client.post("/api/jobs/rerendertest/re-render")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["files_removed"] == 4, body  # reframed + final mp4/ass/jpg
    # reframed & final hilang, raw clip tetap
    base = Path(__file__).parent.parent
    assert not (base / "data/clips_raw/rerendertest_000_x_reframed.mp4").exists()
    assert not (base / "data/clips_final/rerendertest_000_x.mp4").exists()
    assert (base / "data/clips_raw/rerendertest_000_x.mp4").exists()
    print("OK test_re_render_deletes_files_and_restarts")


def test_re_render_404_unknown_job():
    with TestClient(server.app) as client:
        r = client.post("/api/jobs/doesnotexistxyz/re-render")
    assert r.status_code == 404, r.text
    print("OK test_re_render_404_unknown_job")


if __name__ == "__main__":
    import tempfile
    test_re_render_deletes_files_and_restarts(Path(tempfile.mkdtemp()), None)
    test_re_render_404_unknown_job()
    print("all ok")