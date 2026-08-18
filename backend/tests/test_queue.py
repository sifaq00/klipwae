"""Worker-pull queue: atomic claim, heartbeat/stale recovery, job_logs."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.jobs import JobDB, init_db


def test_claim_returns_queued_job_and_marks_claimed(tmp_path, monkeypatch):
    monkeypatch.setenv("KLIPWAE_DB_PATH", str(tmp_path / "q.db"))
    init_db()
    db = JobDB()
    db.enqueue_job("j1", "https://youtube.com/watch?v=1")
    db.enqueue_job("j2", "https://youtube.com/watch?v=2")
    job = db.claim_job("worker-a")
    assert job and job["id"] == "j1"  # FIFO
    row = db.get_job("j1")
    assert row["status"] == "claimed"
    assert row["claimed_by"] == "worker-a"
    # job kedua tidak bisa di-claim worker lain
    assert db.claim_job("worker-b")["id"] == "j2"  # j2 masih queued → ter-claim
    db.close()
    print("OK test_claim_returns_queued_job_and_marks_claimed")


def test_claim_atomic_no_double_assign(tmp_path, monkeypatch):
    monkeypatch.setenv("KLIPWAE_DB_PATH", str(tmp_path / "q2.db"))
    init_db()
    db = JobDB()
    db.enqueue_job("j1", "https://youtube.com/watch?v=1")
    assert db.claim_job("w1") is not None
    # kedua kalinya: tak ada job queued → None
    assert db.claim_job("w2") is None
    db.close()
    print("OK test_claim_atomic_no_double_assign")


def test_stale_claim_recoverable(tmp_path, monkeypatch):
    monkeypatch.setenv("KLIPWAE_DB_PATH", str(tmp_path / "q3.db"))
    init_db()
    db = JobDB()
    db.enqueue_job("j1", "https://youtube.com/watch?v=1")
    db.claim_job("w1")
    # heartbeat tua (>120s) → job bisa di-claim ulang (crash recovery)
    db.conn.execute("UPDATE jobs SET heartbeat_at=? WHERE id='j1'",
                    (time.time() - 300,))
    db.conn.commit()
    job = db.claim_job("w2")
    assert job and job["id"] == "j1"
    assert db.get_job("j1")["claimed_by"] == "w2"
    db.close()
    print("OK test_stale_claim_recoverable")


def test_heartbeat_updates(tmp_path, monkeypatch):
    monkeypatch.setenv("KLIPWAE_DB_PATH", str(tmp_path / "q4.db"))
    init_db()
    db = JobDB()
    db.enqueue_job("j1", "https://youtube.com/watch?v=1")
    db.claim_job("w1")
    db.heartbeat("j1", "w1")
    row = db.get_job("j1")
    assert row["heartbeat_at"] is not None
    assert abs(float(row["heartbeat_at"]) - time.time()) < 5
    # heartbeat salah worker → tak di-update (guard)
    before = row["heartbeat_at"]
    db.heartbeat("j1", "w2")
    assert db.get_job("j1")["heartbeat_at"] == before
    db.close()
    print("OK test_heartbeat_updates")


def test_job_logs_append_and_read(tmp_path, monkeypatch):
    monkeypatch.setenv("KLIPWAE_DB_PATH", str(tmp_path / "q5.db"))
    init_db()
    db = JobDB()
    db.append_job_log("j1", ["line 1", "line 2"])
    db.append_job_log("j1", ["line 3"])
    logs = db.read_job_logs("j1", since=0)
    assert logs == ["line 1", "line 2", "line 3"]
    # cursor lanjutan
    tail = db.read_job_logs("j1", since=2)
    assert tail == ["line 3"]
    db.close()
    print("OK test_job_logs_append_and_read")


if __name__ == "__main__":
    d = Path(tempfile.mkdtemp())
    test_claim_returns_queued_job_and_marks_claimed(d, None)
    test_claim_atomic_no_double_assign(d, None)
    test_stale_claim_recoverable(d, None)
    test_heartbeat_updates(d, None)
    test_job_logs_append_and_read(d, None)
    print("all ok")