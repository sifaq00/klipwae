"""Pytest fixture global: DB terisolasi untuk SEMUA test — server live
(8180) menulis data/jobs.db, pytest tak boleh rebutan lock. Env dibaca
db/jobs.py saat import → set di sini SEBELUM modul apa pun di-import."""
import os
from pathlib import Path

_DB = Path(__file__).parent / "test_jobs.db"
os.environ["KLIPWAE_DB_PATH"] = str(_DB)


def pytest_sessionstart(session):
    """Sesi baru = DB bersih (run sebelumnya bisa meninggalkan tabel)."""
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(_DB) + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass