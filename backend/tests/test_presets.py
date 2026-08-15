import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.jobs import JobDB, init_db, _ensure_columns
from stages.analyze import AnalyzeStage, get_preset_prompt


PRESET_NAMES = ["affiliate", "podcast", "comedy", "education", "storytelling"]


def test_get_preset_prompt_all_presets():
    """Semua 5 preset AI niche dapat diload dan tidak kosong."""
    for name in PRESET_NAMES:
        prompt = get_preset_prompt(name)
        assert prompt, f"Prompt for preset '{name}' is empty"
        assert "segments" in prompt, f"Preset '{name}' missing 'segments' in schema"
        assert "hook_score" in prompt, f"Preset '{name}' missing 'hook_score'"
        assert "virality_reason" in prompt, f"Preset '{name}' missing 'virality_reason'"


def test_get_preset_prompt_fallback():
    """Preset tidak dikenal atau kosong fallback dengan aman ke default affiliate."""
    p_default = get_preset_prompt()
    assert p_default
    assert "affiliate" in p_default or "produk" in p_default

    p_unknown = get_preset_prompt("non_existent_preset_xyz")
    assert p_unknown, "Should fallback to affiliate or product_detection prompt"

    p_case = get_preset_prompt("  PODCAST  ")
    assert p_case == get_preset_prompt("podcast")


def test_db_preset_column_default(tmp_path):
    """Job baru otomatis memiliki preset default 'affiliate'."""
    db_file = tmp_path / "test_jobs.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    schema = (Path(__file__).parent.parent / "db" / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    _ensure_columns(conn)

    # Insert job tanpa eksplisit preset
    conn.execute("INSERT INTO jobs (id, url) VALUES (?, ?)", ("job_def", "https://youtube.com/watch?v=123"))
    conn.commit()

    row = conn.execute("SELECT * FROM jobs WHERE id=?", ("job_def",)).fetchone()
    assert row["preset"] == "affiliate"
    conn.close()


def test_db_create_and_get_job_presets(tmp_path, monkeypatch):
    """create_job dan get_job menyimpan dan mengembalikan preset dengan benar."""
    import db.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "DB_PATH", tmp_path / "jobs.db")
    init_db()
    db = JobDB()

    # Test default
    db.create_job("j_aff", "https://youtube.com/watch?v=aff")
    j_aff = db.get_job("j_aff")
    assert j_aff is not None
    assert j_aff["preset"] == "affiliate"

    # Test custom presets
    for p in ["podcast", "comedy", "education", "storytelling"]:
        db.create_job(f"j_{p}", f"https://youtube.com/watch?v={p}", preset=p)
        res = db.get_job(f"j_{p}")
        assert res is not None
        assert res["preset"] == p

    # Test get_job non-existent
    assert db.get_job("non_existent") is None
    db.close()


def test_ensure_columns_migration_preset(tmp_path):
    """_ensure_columns otomatis menambahkan kolom preset jika belum ada di DB lama."""
    db_file = tmp_path / "old_jobs.db"
    conn = sqlite3.connect(str(db_file))
    # Buat schema jobs lama tanpa kolom preset
    conn.execute("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.execute("INSERT INTO jobs (id, url) VALUES ('old_job', 'https://youtube.com/watch?v=old')")
    conn.commit()

    _ensure_columns(conn)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "preset" in cols, "Kolom 'preset' harus ditambahkan oleh _ensure_columns"

    row = conn.execute("SELECT * FROM jobs WHERE id='old_job'").fetchone()
    conn.row_factory = sqlite3.Row
    row_dict = dict(conn.execute("SELECT * FROM jobs WHERE id='old_job'").fetchone())
    assert row_dict["preset"] == "affiliate"
    conn.close()


def test_analyze_stage_uses_job_preset(tmp_path, monkeypatch):
    """AnalyzeStage.run membaca preset dari db.get_job dan memilih prompt yang tepat."""
    import stages.analyze as analyze_mod
    import runtime

    transcript = [
        {"text": "Momen paling lucu pas kita jatuh dari sepeda", "start": 0.0, "end": 10.0, "words": []},
    ]
    t_dir = tmp_path / "data" / "transcripts"
    t_dir.mkdir(parents=True)
    (t_dir / "job_comedy.json").write_text(json.dumps(transcript), encoding="utf-8")

    # Mock DB
    mock_db = MagicMock()
    mock_db.get_job.return_value = {"id": "job_comedy", "url": "https://...", "preset": "comedy"}

    captured_prompt = []

    def mock_analyze_chunk(client, system_prompt, chunk_text, model, fallback_model=None):
        captured_prompt.append(system_prompt)
        seg = analyze_mod.Segment(
            start="00:00:00", end="00:00:10",
            product_mentioned=None, topic="Jatuh dari sepeda",
            confidence=0.9, reason="Lucu banget",
            hook_score=95, virality_reason="Komedi slapstick",
            affiliate_caption="Ngakak parah 😂 Tag temenmu!",
            hashtags=["#komedi", "#ngakak"]
        )
        return [seg], {"input_tokens": 10, "output_tokens": 10}

    monkeypatch.setattr(analyze_mod, "analyze_chunk", mock_analyze_chunk)

    config = SimpleNamespace(
        google_api_key="fake_key",
        analyze_model="gemini-2.5-flash",
        chunk_duration_min=20,
        chunk_overlap_min=2,
        confidence_threshold=0.6,
    )

    old_cwd = Path.cwd()
    import os
    os.chdir(tmp_path)
    try:
        # Run stage
        stage = AnalyzeStage()
        runtime.reset()
        res = stage.run("job_comedy", mock_db, config)
        assert res.status.value == "done"
        assert len(captured_prompt) == 1
        # Verifikasi prompt yang digunakan adalah preset komedi
        assert "lucu" in captured_prompt[0] or "ngakak" in captured_prompt[0] or "komedi" in captured_prompt[0].lower()
    finally:
        os.chdir(old_cwd)
