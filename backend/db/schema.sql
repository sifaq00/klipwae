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
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stage_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         TEXT REFERENCES jobs(id),
    stage          TEXT NOT NULL,
    status         TEXT NOT NULL,
    attempt        INTEGER DEFAULT 1,
    started_at     TIMESTAMP,
    finished_at    TIMESTAMP,
    duration_ms    INTEGER,
    error_message  TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id             TEXT REFERENCES jobs(id),
    clip_idx           INTEGER,
    start_time         TEXT,
    end_time           TEXT,
    product_mentioned  TEXT,
    topic              TEXT,
    confidence         REAL,
    reason             TEXT,
    layout_type        TEXT,
    camera_path_json   TEXT,
    clip_path          TEXT,
    caption_path       TEXT,
    caption_text       TEXT,
    hook_score         INTEGER,
    virality_reason    TEXT,
    affiliate_caption  TEXT,
    hashtags           TEXT,
    reviewed           BOOLEAN DEFAULT 0,
    posted             BOOLEAN DEFAULT 0,
    UNIQUE(job_id, clip_idx)
);

CREATE TABLE IF NOT EXISTS metrics (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         TEXT REFERENCES jobs(id),
    stage          TEXT,
    duration_ms    INTEGER,
    cost_usd       REAL,
    extra_json     TEXT,
    recorded_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
