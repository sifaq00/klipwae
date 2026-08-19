import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

# KLIPWAE_DB_PATH: isolasi DB utk test (server live & pytest tak boleh
# rebutan lock file yang sama). Dibaca LAZY tiap get_connection — test
# yang ganti env di tengah suite harus dapat DB yang benar.
# DATABASE_URL (Supabase/Neon): kalau ada → Postgres (prod), selain itu
# SQLite (dev/test). API kedua backend identik via wrapper db/pg.py.


def _db_path() -> Path:
    return Path(os.environ.get("KLIPWAE_DB_PATH", "data/jobs.db"))


def get_connection():
    from db.pg import pg_enabled
    if pg_enabled():
        from db.pg import get_pg_connection
        return get_pg_connection()
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: caption stage burn paralel (ThreadPoolExecutor)
    # memakai JobDB yang sama dari beberapa worker thread.
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    from db.pg import pg_enabled
    if pg_enabled():
        schema = Path(__file__).parent / "schema.pg.sql"
    else:
        schema = Path(__file__).parent / "schema.sql"
    with get_connection() as conn:
        conn.executescript(schema.read_text())
        _ensure_columns(conn)


def _ensure_columns(conn):
    """Migrasi ringan utk DB yang sudah ada — dual (sqlite/pg).
    Postgres: ALTER TABLE ADD COLUMN IF NOT EXISTS. SQLite: PRAGMA scan."""
    from db.pg import pg_enabled
    if pg_enabled():
        for table, cols in (
            ("segments", {
                "clip_idx": "INTEGER", "caption_text": "TEXT",
                "hook_score": "INTEGER", "virality_reason": "TEXT",
                "affiliate_caption": "TEXT", "hashtags": "TEXT",
                "clip_start_sec": "DOUBLE PRECISION", "clip_end_sec": "DOUBLE PRECISION",
            }),
            ("jobs", {
                "caption_style": "TEXT", "notice": "TEXT",
                "downloaded": "INTEGER NOT NULL DEFAULT 0",
                "preset": "TEXT DEFAULT 'affiliate'",
                "claimed_by": "TEXT", "claimed_at": "DOUBLE PRECISION",
                "heartbeat_at": "DOUBLE PRECISION",
            }),
        ):
            for col, ddl in cols.items():
                conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ddl}")
        conn.commit()
        return

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "segments" in tables:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(segments)").fetchall()}
        for col, ddl in {
            "clip_idx": "INTEGER",
            "caption_text": "TEXT",
            "hook_score": "INTEGER",
            "virality_reason": "TEXT",
            "affiliate_caption": "TEXT",
            "hashtags": "TEXT",
            "clip_start_sec": "REAL",  # actual window klip (caption butuh offset benar)
            "clip_end_sec": "REAL",
        }.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE segments ADD COLUMN {col} {ddl}")
        # DB lama dibuat sebelum UNIQUE(job_id, clip_idx) ada di schema.sql —
        # upsert ON CONFLICT butuh index ini (bug ketemu saat validasi e2e).
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_segments_job_clip ON segments(job_id, clip_idx)"
        )
    if "jobs" in tables:
        job_cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "caption_style" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN caption_style TEXT")
        if "notice" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN notice TEXT")
        if "downloaded" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN downloaded INTEGER NOT NULL DEFAULT 0")
        if "preset" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN preset TEXT DEFAULT 'affiliate'")
        for col, ddl in {
            "claimed_by": "TEXT",
            "claimed_at": "REAL",
            "heartbeat_at": "REAL",
        }.items():
            if col not in job_cols:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
    conn.commit()


class JobDB:
    def __init__(self):
        self.conn = get_connection()

    def close(self):
        self.conn.close()

    def create_job(self, job_id: str, url: str, preset: str = "affiliate"):
        self.conn.execute(
            "INSERT INTO jobs (id, url, preset) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET preset=coalesce(excluded.preset, jobs.preset)",
            (job_id, url, preset or "affiliate"),
        )
        self.conn.commit()

    def get_job(self, job_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if not d.get("preset"):
            d["preset"] = "affiliate"
        return d

    def update_job_metadata(self, job_id: str, title: Optional[str] = None, duration_sec: Optional[int] = None, channel: Optional[str] = None):
        self.conn.execute(
            "UPDATE jobs SET title=?, duration_sec=?, channel=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (title, duration_sec, channel, job_id),
        )
        self.conn.commit()

    def mark_job_status(self, job_id: str, status: str, failed_stage: str = None, error: str = None):
        self.conn.execute(
            "UPDATE jobs SET status=?, failed_stage=?, error_message=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, failed_stage, error, job_id),
        )
        self.conn.commit()

    def set_notice(self, job_id: str, notice: str | None):
        """Info non-fatal buat user (mis. 'tidak ditemukan segmen produk').
        Notice di-cover saat job di-retry ulang."""
        self.conn.execute(
            "UPDATE jobs SET notice=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (notice, job_id),
        )
        self.conn.commit()

    def mark_downloaded(self, job_id: str):
        """Ditandai HANYA setelah yt-dlp sukses + metadata lengkap ter-tulis.
        is_complete butuh flag ini: metadata bisa muncul duluan dari
        early-fetch (POST), file final >1MB bisa parsial (kill pas merge) —
        keduanya bukan bukti download sukses."""
        self.conn.execute(
            "UPDATE jobs SET downloaded=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (job_id,),
        )
        self.conn.commit()

    # ---- Worker-pull queue ----

    def enqueue_job(self, job_id: str, url: str, preset: str = "affiliate"):
        """Job masuk antrean worker (bukan di-proses server lokal)."""
        self.conn.execute(
            "INSERT INTO jobs (id, url, preset, status) VALUES (?, ?, ?, 'queued') "
            "ON CONFLICT(id) DO UPDATE SET status='queued', preset=excluded.preset, "
            "claimed_by=NULL, claimed_at=NULL, heartbeat_at=NULL",
            (job_id, url, preset or "affiliate"),
        )
        self.conn.commit()

    def claim_job(self, worker_id: str, stale_after: float = 120.0) -> dict | None:
        """Atomic claim FIFO. Job yang di-claim worker lain tapi heartbeat-nya
        basi (>stale_after detik) dianggap crash → bisa di-claim ulang."""
        now = time.time()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT id, url, preset FROM jobs "
                "WHERE status='queued' "
                "   OR (status='claimed' AND (heartbeat_at IS NULL OR ? - heartbeat_at > ?)) "
                "ORDER BY created_at ASC, id ASC LIMIT 1",
                (now, stale_after),
            ).fetchone()
            if not row:
                self.conn.commit()
                return None
            self.conn.execute(
                "UPDATE jobs SET status='claimed', claimed_by=?, claimed_at=?, "
                "heartbeat_at=?, error_message=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (worker_id, now, now, row["id"]),
            )
            self.conn.commit()
            return dict(row)
        except Exception:
            self.conn.rollback()
            raise

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        """Perpanjang claim (hanya oleh worker pemilik)."""
        cur = self.conn.execute(
            "UPDATE jobs SET heartbeat_at=? WHERE id=? AND claimed_by=?",
            (time.time(), job_id, worker_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def append_job_log(self, job_id: str, lines: list[str]):
        """Append log worker ke tabel job_logs (replay SSE lintas restart)."""
        if not lines:
            return
        base = self.conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM job_logs WHERE job_id=?", (job_id,)
        ).fetchone()[0]
        with self.conn:
            for i, line in enumerate(lines, 1):
                self.conn.execute(
                    "INSERT INTO job_logs (job_id, seq, line) VALUES (?, ?, ?)",
                    (job_id, base + i, line),
                )

    def read_job_logs(self, job_id: str, since: int = 0) -> list[str]:
        rows = self.conn.execute(
            "SELECT line FROM job_logs WHERE job_id=? AND seq > ? ORDER BY seq",
            (job_id, since),
        ).fetchall()
        return [r["line"] for r in rows]

    def log_stage_start(self, job_id: str, stage: str, attempt: int = 1):
        self.conn.execute(
            "INSERT INTO stage_runs (job_id, stage, status, attempt, started_at) VALUES (?, ?, 'running', ?, CURRENT_TIMESTAMP)",
            (job_id, stage, attempt),
        )
        self.conn.commit()

    def log_stage_end(self, job_id: str, stage: str, result):
        # Update hanya row running TERBARU untuk (job_id, stage). Tanpa LIMIT,
        # kalau ada stale 'running' row dari attempt sebelumnya (mis. proses
        # di-kill sebelum log_stage_end), multiple row ke-update sekaligus.
        self.conn.execute(
            """UPDATE stage_runs SET status=?, finished_at=CURRENT_TIMESTAMP,
               duration_ms=(strftime('%s','now') - strftime('%s',started_at))*1000,
               error_message=?
               WHERE id = (
                   SELECT id FROM stage_runs
                   WHERE job_id=? AND stage=? AND status='running'
                   ORDER BY id DESC LIMIT 1
               )""",
            (result.status.value, result.error, job_id, stage),
        )
        self.conn.commit()

    def insert_segments(self, job_id: str, segments: list):
        # Idempotent: DELETE dulu supaya re-run stage analyze (mis. setelah
        # prompt di-tune) tidak menyebabkan duplikat segmen di DB.
        self.conn.execute("DELETE FROM segments WHERE job_id=?", (job_id,))
        for seg in segments:
            hashtags_val = getattr(seg, "hashtags", None)
            if isinstance(hashtags_val, list):
                hashtags_json = json.dumps(hashtags_val, ensure_ascii=False)
            elif isinstance(hashtags_val, str):
                hashtags_json = hashtags_val
            else:
                hashtags_json = json.dumps([])

            start_time = getattr(seg, "start", getattr(seg, "start_time", None))
            end_time = getattr(seg, "end", getattr(seg, "end_time", None))

            self.conn.execute(
                """INSERT INTO segments (
                    job_id, start_time, end_time, product_mentioned, topic,
                    confidence, reason, caption_text, hook_score,
                    virality_reason, affiliate_caption, hashtags
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    start_time,
                    end_time,
                    getattr(seg, "product_mentioned", None),
                    getattr(seg, "topic", None),
                    getattr(seg, "confidence", 0.0),
                    getattr(seg, "reason", None),
                    getattr(seg, "caption_text", None),
                    getattr(seg, "hook_score", 85),
                    getattr(seg, "virality_reason", ""),
                    getattr(seg, "affiliate_caption", ""),
                    hashtags_json,
                ),
            )
        self.conn.commit()

    def upsert_clip_segment(self, job_id: str, clip_idx: int, start: str, end: str, seg, clip_path: str,
                            clip_start_sec: float | None = None, clip_end_sec: float | None = None):
        """Insert/update segmen hasil split di stage clip. Idempotent per (job_id, clip_idx)."""
        hashtags_val = getattr(seg, "hashtags", None)
        if isinstance(hashtags_val, list):
            hashtags_json = json.dumps(hashtags_val, ensure_ascii=False)
        elif isinstance(hashtags_val, str):
            hashtags_json = hashtags_val
        else:
            hashtags_json = json.dumps([])

        self.conn.execute(
            """INSERT INTO segments (
                job_id, clip_idx, start_time, end_time, clip_start_sec, clip_end_sec,
                product_mentioned, topic, confidence, reason, caption_text, clip_path,
                hook_score, virality_reason, affiliate_caption, hashtags
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(job_id, clip_idx) DO UPDATE SET
              start_time=excluded.start_time, end_time=excluded.end_time,
              clip_start_sec=excluded.clip_start_sec, clip_end_sec=excluded.clip_end_sec,
              caption_text=excluded.caption_text, clip_path=excluded.clip_path,
              hook_score=excluded.hook_score, virality_reason=excluded.virality_reason,
              affiliate_caption=excluded.affiliate_caption, hashtags=excluded.hashtags""",
            (
                job_id, clip_idx, start, end, clip_start_sec, clip_end_sec,
                getattr(seg, "product_mentioned", None),
                getattr(seg, "topic", None),
                getattr(seg, "confidence", 0.0),
                getattr(seg, "reason", None),
                getattr(seg, "caption_text", None),
                clip_path,
                getattr(seg, "hook_score", 85),
                getattr(seg, "virality_reason", ""),
                getattr(seg, "affiliate_caption", ""),
                hashtags_json,
            ),
        )
        self.conn.commit()

    def delete_unclipped(self, job_id: str):
        """Buang row segmen yang belum punya clip (gagal di-clip / segmen induk
        yang sudah di-split jadi sub-klip)."""
        self.conn.execute(
            "DELETE FROM segments WHERE job_id=? AND clip_path IS NULL", (job_id,)
        )
        self.conn.commit()

    def get_job_segments(self, job_id: str) -> list:
        rows = self.conn.execute(
            "SELECT * FROM segments WHERE job_id=? ORDER BY id", (job_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("hashtags"):
                try:
                    d["hashtags"] = json.loads(d["hashtags"]) if isinstance(d["hashtags"], str) else d["hashtags"]
                except Exception:
                    d["hashtags"] = []
            else:
                d["hashtags"] = []
            result.append(d)
        return result

    def get_segments(self, job_id: str) -> list:
        return self.get_job_segments(job_id)


    def get_job_style(self, job_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT caption_style FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        return row["caption_style"] if row else None

    def set_job_style(self, job_id: str, style_json: str):
        self.conn.execute(
            "UPDATE jobs SET caption_style=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (style_json, job_id),
        )
        self.conn.commit()

    def delete_segment(self, segment_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM segments WHERE id=?", (segment_id,)
        ).fetchone()
        if not row:
            return None
        self.conn.execute("DELETE FROM segments WHERE id=?", (segment_id,))
        self.conn.commit()
        return dict(row)

    def update_segment_by_id(self, segment_id: int, **kwargs):
        cols = ", ".join(f"{k}=?" for k in kwargs)
        self.conn.execute(
            f"UPDATE segments SET {cols} WHERE id=?",
            list(kwargs.values()) + [segment_id],
        )
        self.conn.commit()

    def record_metric(self, job_id: str, stage: str, cost_usd: float = 0.0, extra: dict = None):
        self.conn.execute(
            "INSERT INTO metrics (job_id, stage, cost_usd, extra_json) VALUES (?, ?, ?, ?)",
            (job_id, stage, cost_usd, json.dumps(extra) if extra else None),
        )
        self.conn.commit()
