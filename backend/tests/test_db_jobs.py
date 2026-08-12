import os
import sys
import sqlite3
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.jobs import get_connection, init_db, JobDB


def test_get_connection_wal():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        conn = get_connection()
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()
    print("OK test_get_connection_wal")


def test_init_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        init_db()
        conn = get_connection()
        try:
            tables = [
                r["name"] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            for t in ("jobs", "stage_runs", "segments", "metrics", "schema_version"):
                assert t in tables, f"Table {t} missing"
        finally:
            conn.close()
    print("OK test_init_db")


def test_create_job():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        init_db()
        db = JobDB()
        try:
            db.create_job("abc", "https://youtube.com/watch?v=abc")
            row = db.conn.execute("SELECT * FROM jobs WHERE id=?", ("abc",)).fetchone()
            assert row["id"] == "abc"
            assert row["url"] == "https://youtube.com/watch?v=abc"
            assert row["status"] == "pending"
            db.create_job("abc", "https://youtube.com/watch?v=abc")
            count = db.conn.execute("SELECT COUNT(*) FROM jobs WHERE id=?", ("abc",)).fetchone()[0]
            assert count == 1
        finally:
            db.close()
    print("OK test_create_job")


def test_job_status_transitions():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        init_db()
        db = JobDB()
        try:
            db.create_job("j1", "url")
            db.mark_job_status("j1", "running")
            assert db.conn.execute("SELECT status FROM jobs WHERE id=?", ("j1",)).fetchone()[0] == "running"
            db.mark_job_status("j1", "done")
            assert db.conn.execute("SELECT status FROM jobs WHERE id=?", ("j1",)).fetchone()[0] == "done"
        finally:
            db.close()
    print("OK test_job_status_transitions")


def test_update_job_metadata():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        init_db()
        db = JobDB()
        try:
            db.create_job("j1", "url")
            db.update_job_metadata("j1", title="Test Video", duration_sec=600, channel="Test Channel")
            row = db.conn.execute("SELECT * FROM jobs WHERE id=?", ("j1",)).fetchone()
            assert row["title"] == "Test Video"
            assert row["duration_sec"] == 600
            assert row["channel"] == "Test Channel"
            assert row["updated_at"] is not None
        finally:
            db.close()
    print("OK test_update_job_metadata")


def test_stage_runs():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        init_db()
        db = JobDB()
        try:
            db.create_job("j1", "url")
            db.log_stage_start("j1", "ingest", attempt=1)
            rows = db.conn.execute(
                "SELECT * FROM stage_runs WHERE job_id=? AND stage=?",
                ("j1", "ingest"),
            ).fetchall()
            assert len(rows) == 1
            assert rows[0]["status"] == "running"

            from stages.base import StageResult, StageStatus
            result = StageResult(status=StageStatus.DONE)
            db.log_stage_end("j1", "ingest", result)
            rows = db.conn.execute(
                "SELECT * FROM stage_runs WHERE job_id=? AND stage=?",
                ("j1", "ingest"),
            ).fetchall()
            assert rows[0]["status"] == "done"
            assert rows[0]["duration_ms"] >= 0
        finally:
            db.close()
    print("OK test_stage_runs")


def test_insert_segments_idempotent():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        init_db()
        db = JobDB()
        try:
            db.create_job("j1", "url")
            from types import SimpleNamespace
            segs = [
                SimpleNamespace(start="00:01:00", end="00:01:10",
                                product_mentioned="serum", topic="skincare",
                                confidence=0.85, reason="good"),
            ]
            db.insert_segments("j1", segs)
            assert len(db.conn.execute("SELECT * FROM segments WHERE job_id=?", ("j1",)).fetchall()) == 1
            # Re-run should replace, not duplicate
            db.insert_segments("j1", segs)
            assert len(db.conn.execute("SELECT * FROM segments WHERE job_id=?", ("j1",)).fetchall()) == 1
        finally:
            db.close()
    print("OK test_insert_segments_idempotent")


def test_record_metric():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        init_db()
        db = JobDB()
        try:
            db.create_job("j1", "url")
            db.record_metric("j1", "analyze", cost_usd=0.31, extra={"segments_found": 5})
            row = db.conn.execute("SELECT * FROM metrics WHERE job_id=?", ("j1",)).fetchone()
            assert row["stage"] == "analyze"
            assert abs(row["cost_usd"] - 0.31) < 0.001
            assert '"segments_found": 5' in row["extra_json"]
        finally:
            db.close()
    print("OK test_record_metric")


if __name__ == "__main__":
    test_get_connection_wal()
    test_init_db()
    test_create_job()
    test_job_status_transitions()
    test_update_job_metadata()
    test_stage_runs()
    test_insert_segments_idempotent()
    test_record_metric()
    print("\nAll DB tests passed.")
