"""Worker-pull E2E: create → queued → claim → progress → result → UI data."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["KLIPWAE_DB_PATH"] = str(Path(__file__).parent / "test_queue_e2e.db")


def _cleanup():
    try:
        os.unlink(os.environ["KLIPWAE_DB_PATH"])
    except OSError:
        pass
    for p in (Path(__file__).parent.parent / "data" / "segments").glob("qj_*.json"):
        try:
            p.unlink()
        except OSError:
            pass


def test_worker_pull_flow(tmp_path, monkeypatch):
    # env DI SET DI SINI: test lain (test_config) bisa hapus di tengah suite
    monkeypatch.setenv("WORKER_QUEUE", "true")
    monkeypatch.setenv("WORKER_TOKEN", "testtoken123")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("R2_PUBLIC_URL", "https://klipwae.example")
    from db.jobs import init_db
    init_db()  # DB test_queue_e2e.db fresh (server sudah ter-import utk DB lain)
    _cleanup()
    import server
    from starlette.testclient import TestClient

    server._uploads_cache.clear()
    with TestClient(server.app) as client:
        # 1) create → queued (worker mode)
        r = client.post("/api/jobs", json={"url": "https://www.youtube.com/watch?v=qj123456789"})
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        assert r.json()["status"] == "queued"

        # 2) claim tanpa token → 401
        assert client.post("/api/jobs/claim").status_code == 401

        # 3) claim dengan token → job
        h = {"Authorization": "Bearer testtoken123", "X-Worker-Id": "w-test"}
        r = client.post("/api/jobs/claim", headers=h)
        assert r.status_code == 200
        assert r.json()["job"]["job_id"] == job_id
        assert r.json()["job"]["preset"] == "affiliate"

        # claim kedua → None (atomic)
        r2 = client.post("/api/jobs/claim", headers=h)
        assert r2.json()["job"] is None

        # 4) heartbeat salah worker → 409
        h_bad = {"Authorization": "Bearer testtoken123", "X-Worker-Id": "w-lain"}
        assert client.post(f"/api/jobs/{job_id}/heartbeat", headers=h_bad).status_code == 409
        assert client.post(f"/api/jobs/{job_id}/heartbeat", headers=h).status_code == 200

        # 5) progress → log tersimpan (SSE replay)
        r = client.post(f"/api/jobs/{job_id}/progress", headers=h,
                        json={"lines": ["download 50%", "download done"], "status": "downloading"})
        assert r.status_code == 200
        db_logs = server.JobDB().read_job_logs(job_id, 0)
        assert db_logs == ["download 50%", "download done"]

        # 6) upload-url presigned (R2 belum dikonfigurasi → 503; set minimal)
        os.environ["R2_ACCOUNT_ID"] = "acct"
        os.environ["R2_ACCESS_KEY_ID"] = "key"
        os.environ["R2_SECRET_ACCESS_KEY"] = "sec"
        r = client.post(f"/api/jobs/{job_id}/upload-url", headers=h,
                        json={"key": "qj123456789_000_x.mp4", "content_type": "video/mp4"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "put_url" in body and "X-Amz-Signature" in body["put_url"]
        assert body["public_url"].startswith("https://klipwae.example/clips/")

        # 7) result → done + segments + uploads URL
        segs = [{"clip_idx": 0, "start_time": "00:00:01", "end_time": "00:00:02",
                 "product_mentioned": "Serum X", "topic": "review", "confidence": 0.9}]
        r = client.post(f"/api/jobs/{job_id}/result", headers=h, json={
            "status": "done", "segments": segs,
            "uploads": [
                {"key": "clips/qj123456789/qj123456789_000_x.mp4", "name": "qj123456789_000_x.mp4", "kind": "clip"},
            ],
        })
        assert r.status_code == 200

        # 8) UI: status done + segments dgn URL klip R2
        j = client.get(f"/api/jobs/{job_id}").json()
        assert j["status"] == "done"
        segs_ui = client.get(f"/api/jobs/{job_id}/segments").json()
        assert len(segs_ui) == 1
        assert segs_ui[0]["clip_url"].startswith("https://klipwae.example/clips/")
        assert segs_ui[0]["product_mentioned"] == "Serum X"

    _cleanup()
    print("OK test_worker_pull_flow")


if __name__ == "__main__":
    test_worker_pull_flow(Path("."), None)
    print("all ok")