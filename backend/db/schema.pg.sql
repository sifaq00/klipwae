-- PostgreSQL (Supabase/Neon) — prod. SQLite version di schema.sql (dev/test).
CREATE TABLE IF NOT EXISTS jobs (
    id             TEXT PRIMARY KEY,
    url            TEXT NOT NULL,
    title          TEXT,
    duration_sec   INTEGER,
    channel        TEXT,
    status         TEXT DEFAULT 'pending',
    failed_stage   TEXT,
    error_message  TEXT,
    notice         TEXT,
    downloaded     INTEGER NOT NULL DEFAULT 0,
    preset         TEXT DEFAULT 'affiliate',
    claimed_by     TEXT,
    claimed_at     DOUBLE PRECISION,
    heartbeat_at   DOUBLE PRECISION,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_logs (
    job_id         TEXT NOT NULL,
    seq            INTEGER NOT NULL,
    line           TEXT NOT NULL,
    ts             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, seq)
);

CREATE TABLE IF NOT EXISTS stage_runs (
    id             BIGSERIAL PRIMARY KEY,
    job_id         TEXT REFERENCES jobs(id),
    stage          TEXT NOT NULL,
    status         TEXT NOT NULL,
    attempt        INTEGER DEFAULT 1,
    started_at     TIMESTAMP,
    finished_at    TIMESTAMP,
    duration_ms    INTEGER,
    error_message  TEXT
);

CREATE INDEX IF NOT EXISTS idx_stage_runs_job ON stage_runs(job_id, stage, status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);

CREATE TABLE IF NOT EXISTS metrics (
    id             BIGSERIAL PRIMARY KEY,
    job_id         TEXT REFERENCES jobs(id),
    stage          TEXT,
    duration_ms    INTEGER,
    cost_usd       REAL,
    extra_json     TEXT,
    recorded_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_metrics_job ON metrics(job_id, stage);

CREATE TABLE IF NOT EXISTS segments (
    id               BIGSERIAL PRIMARY KEY,
    job_id           TEXT REFERENCES jobs(id),
    clip_idx         INTEGER,
    start_time       TEXT,
    end_time         TEXT,
    clip_start_sec   DOUBLE PRECISION,
    clip_end_sec     DOUBLE PRECISION,
    product_mentioned TEXT,
    topic            TEXT,
    confidence       DOUBLE PRECISION,
    reason           TEXT,
    layout_type      TEXT,
    camera_path_json TEXT,
    clip_path        TEXT,
    caption_path     TEXT,
    caption_text     TEXT,
    hook_score       INTEGER,
    virality_reason  TEXT,
    affiliate_caption TEXT,
    hashtags         TEXT,
    reviewed         BOOLEAN DEFAULT FALSE,
    posted           BOOLEAN DEFAULT FALSE,
    UNIQUE(job_id, clip_idx)
);

CREATE INDEX IF NOT EXISTS idx_segments_job ON segments(job_id);