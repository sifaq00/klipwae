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


def test_insert_and_get_segments_with_hook_and_affiliate():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        init_db()
        db = JobDB()
        try:
            db.create_job("j1", "url")
            from types import SimpleNamespace
            segs = [
                SimpleNamespace(
                    start="00:01:00",
                    end="00:01:30",
                    product_mentioned="Somethinc Serum",
                    topic="Review Serum Glowing",
                    confidence=0.92,
                    reason="Ulasan mendalam",
                    caption_text="Pakai serum ini langsung glowing ✨\n#racuntiktok #affiliate",
                    hook_score=95,
                    virality_reason="Efek instan 3 hari",
                    affiliate_caption="Klik keranjang kuning sekarang! ✨",
                    hashtags=["#racuntiktok", "#affiliate", "#skincare"],
                ),
            ]
            db.insert_segments("j1", segs)
            retrieved = db.get_job_segments("j1")
            assert len(retrieved) == 1
            r = retrieved[0]
            assert r["hook_score"] == 95
            assert r["virality_reason"] == "Efek instan 3 hari"
            assert r["affiliate_caption"] == "Klik keranjang kuning sekarang! ✨"
            assert r["hashtags"] == ["#racuntiktok", "#affiliate", "#skincare"]

            # Test upsert_clip_segment
            db.upsert_clip_segment(
                "j1", clip_idx=0,
                start="00:01:00", end="00:01:30",
                seg=segs[0],
                clip_path="data/clips_raw/j1_000.mp4"
            )
            db.delete_unclipped("j1")
            retrieved2 = db.get_job_segments("j1")
            assert len(retrieved2) == 1
            r2 = retrieved2[0]
            assert r2["clip_idx"] == 0
            assert r2["hook_score"] == 95
            assert r2["affiliate_caption"] == "Klik keranjang kuning sekarang! ✨"
            assert r2["hashtags"] == ["#racuntiktok", "#affiliate", "#skincare"]

            # Test updating existing clip segment via upsert_clip_segment
            updated_seg = SimpleNamespace(
                product_mentioned="Somethinc Serum",
                topic="Review",
                confidence=0.95,
                reason="Updated",
                caption_text="New text",
                hook_score=99,
                virality_reason="Mega viral",
                affiliate_caption="Beli sekarang!",
                hashtags=["#viral"],
            )
            db.upsert_clip_segment(
                "j1", clip_idx=0,
                start="00:01:00", end="00:01:30",
                seg=updated_seg,
                clip_path="data/clips_raw/j1_000.mp4"
            )
            retrieved3 = db.get_job_segments("j1")
            assert len(retrieved3) == 1
            assert retrieved3[0]["hook_score"] == 99
            assert retrieved3[0]["virality_reason"] == "Mega viral"
            assert retrieved3[0]["affiliate_caption"] == "Beli sekarang!"
            assert retrieved3[0]["hashtags"] == ["#viral"]
        finally:
            db.close()
    print("OK test_insert_and_get_segments_with_hook_and_affiliate")


def test_ensure_columns_migration(tmp_path, monkeypatch):
    monkeypatch.setenv("KLIPWAE_DB_PATH", str(tmp_path / "migrate.db"))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        # Create legacy table without new columns
        conn = get_connection()
        conn.execute("""
            CREATE TABLE segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                start_time TEXT,
                end_time TEXT,
                product_mentioned TEXT,
                topic TEXT,
                confidence REAL,
                reason TEXT
            )
        """)
        conn.commit()
        conn.close()

        # _ensure_columns now runs in init_db(), not JobDB.__init__
        from db.jobs import _ensure_columns
        db = JobDB()
        try:
            _ensure_columns(db.conn)
            cols = {r[1] for r in db.conn.execute("PRAGMA table_info(segments)").fetchall()}
            for expected in ("clip_idx", "caption_text", "hook_score", "virality_reason", "affiliate_caption", "hashtags"):
                assert expected in cols, f"Column {expected} missing after migration"
        finally:
            db.close()
    print("OK test_ensure_columns_migration")


if __name__ == "__main__":
    test_get_connection_wal()
    test_init_db()
    test_create_job()
    test_job_status_transitions()
    test_update_job_metadata()
    test_stage_runs()
    test_insert_segments_idempotent()
    test_record_metric()
    test_insert_and_get_segments_with_hook_and_affiliate()
    test_ensure_columns_migration()
    print("\nAll DB tests passed.")

