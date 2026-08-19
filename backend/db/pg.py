"""Postgres connection wrapper — API kompatibel sqlite3 yang dipakai
db/jobs.py (execute/executescript/commit/close/row_factory/with).

Aktif kalau env DATABASE_URL ada (Supabase/Neon); selain itu SQLite lokal
(dev/test). Placeholder `?` di-rewrite ke `%s` otomatis.
"""
import os

import psycopg2
import psycopg2.extras


def pg_enabled() -> bool:
    return bool(os.environ.get("DATABASE_URL", "").strip())


class _PgConn:
    def __init__(self):
        self.conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10)
        self.conn.autocommit = False

    def execute(self, sql: str, params=None):
        # ? -> %s (sqlite vs psycopg2 placeholder). Aman: query kita tak
        # memakai '?' literal di dalam string.
        sql = sql.replace("?", "%s")
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(sql, params or ())
        return cur

    def executescript(self, sql: str):
        cur = self.conn.cursor()
        cur.execute(sql)  # libpq dukung multi-statement
        cur.close()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


def get_pg_connection() -> _PgConn:
    return _PgConn()