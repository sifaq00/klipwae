import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.analyze import (
    Segment,
    chunk_transcript,
    format_chunk_for_prompt,
    merge_and_dedupe,
    overlap_ratio,
)
from utils.time_helpers import sec_to_hms


def _seg(start_sec: float, end_sec: float, text: str = "x") -> SimpleNamespace:
    return SimpleNamespace(text=text, start=start_sec, end=end_sec)


def test_chunk_transcript_empty():
    assert chunk_transcript([]) == []
    print("OK test_chunk_transcript_empty")


def test_chunk_transcript_overlap_guard():
    try:
        chunk_transcript([_seg(0, 10)], chunk_min=5, overlap_min=5)
        assert False, "Should raise ValueError"
    except ValueError:
        pass
    print("OK test_chunk_transcript_overlap_guard")


def test_chunk_transcript_basic():
    # Transkrip 30 menit, chunk 20 min, overlap 2 min
    segments = [_seg(i * 60, i * 60 + 30) for i in range(30)]
    chunks = chunk_transcript(segments, chunk_min=20, overlap_min=2)
    assert len(chunks) >= 2, f"Expected >=2 chunks, got {len(chunks)}"
    # Chunk pertama mulai dari 0
    assert chunks[0][0].start == 0
    # Tidak ada chunk kosong
    for c in chunks:
        assert len(c) > 0
    print(f"OK test_chunk_transcript_basic ({len(chunks)} chunks)")


def test_format_chunk_for_prompt():
    chunk = [_seg(842.0, 875.0, "halo dunia")]
    out = format_chunk_for_prompt(chunk)
    assert out == "[00:14:02] halo dunia", f"Got: {out!r}"
    print("OK test_format_chunk_for_prompt")


def _pyd_seg(start: str, end: str, conf: float = 0.5) -> Segment:
    return Segment(start=start, end=end, product_mentioned="x", topic="t", confidence=conf, reason="r")


def test_overlap_ratio():
    a = _pyd_seg("00:01:00", "00:02:00")  # 60-120
    b = _pyd_seg("00:01:30", "00:02:30")  # 90-150
    # overlap = 30s, shorter = 60s → 0.5
    assert abs(overlap_ratio(a, b) - 0.5) < 0.01
    # No overlap
    c = _pyd_seg("00:03:00", "00:04:00")
    assert overlap_ratio(a, c) == 0.0
    print("OK test_overlap_ratio")


def test_merge_and_dedupe():
    # Dua segmen overlap >70%, confidence beda → ambil yang lebih tinggi
    a = _pyd_seg("00:01:00", "00:02:00", conf=0.7)
    b = _pyd_seg("00:01:10", "00:02:10", conf=0.9)  # overlap ~50/60 = 0.83 > 0.7
    merged = merge_and_dedupe([a, b])
    assert len(merged) == 1, f"Expected 1, got {len(merged)}"
    assert merged[0].confidence == 0.9
    # Tidak overlap → tetap dua
    c = _pyd_seg("00:10:00", "00:11:00", conf=0.5)
    merged2 = merge_and_dedupe([a, b, c])
    assert len(merged2) == 2
    print("OK test_merge_and_dedupe")


def test_analyze_stage_with_mock(tmp_path: Path):
    """End-to-end AnalyzeStage dengan mock Gemini — verifikasi file output,
    DB insert, metric recording, is_complete."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Setup: buat transcript, prompts, .env
        Path("data/transcripts").mkdir(parents=True)
        Path("prompts").mkdir()
        Path("prompts/product_detection.txt").write_text("test prompt", encoding="utf-8")
        Path("prompts/caption_generator.txt").write_text("test caption prompt", encoding="utf-8")

        transcript = [
            {"text": "Aku pakai serum vitamin C tiap pagi", "start": 842.0, "end": 845.5, "words": []},
            {"text": "Efeknya kulit lebih cerah dalam 3 minggu", "start": 846.0, "end": 850.0, "words": []},
        ]
        Path("data/transcripts/job1.json").write_text(
            json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
        )

        # Mock DB
        import sqlite3
        from db.jobs import init_db, JobDB
        init_db()
        db = JobDB()
        db.create_job("job1", "https://youtube.com/watch?v=job1")

        # Mock analyze_chunk
        fake_segments = [Segment(
            start="00:14:02", end="00:14:10",
            product_mentioned="Serum Vitamin C",
            topic="skincare routine",
            confidence=0.85,
            reason="detail",
        )]

        from stages import analyze
        analyze.analyze_chunk = lambda client, sp, ct, model: (fake_segments, {"input_tokens": 100, "output_tokens": 50})
        analyze.generate_captions = lambda client, sp, segs, model: {0: "Hook! \n#skincare #fyp"}

        # Mock config
        from types import SimpleNamespace
        config = SimpleNamespace(
            google_api_key="fake",
            analyze_model="gemini-2.5-flash",
            chunk_duration_min=20,
            chunk_overlap_min=2,
            confidence_threshold=0.6,
        )

        result = analyze.AnalyzeStage().run("job1", db, config)
        assert result.status.value == "done", f"status={result.status}"
        assert result.metadata["segments_found"] == 1

        # Verify file output
        out = Path("data/segments/job1.json")
        assert out.exists(), "Output file tidak ditulis"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["product_mentioned"] == "Serum Vitamin C"
        assert data[0]["caption_text"] == "Hook! \n#skincare #fyp"

        # Verify DB segments
        rows = db.conn.execute("SELECT * FROM segments WHERE job_id=?", ("job1",)).fetchall()
        assert len(rows) == 1, f"DB segments: {len(rows)}"
        assert rows[0]["confidence"] == 0.85
        assert rows[0]["caption_text"] == "Hook! \n#skincare #fyp"

        # Verify metrics
        m = db.conn.execute("SELECT * FROM metrics WHERE job_id=? AND stage='analyze'", ("job1",)).fetchall()
        assert len(m) == 1

        # Verify is_complete
        assert analyze.AnalyzeStage().is_complete("job1", db) is True

        # Verify idempotent re-run (no duplicate segments)
        analyze.AnalyzeStage().run("job1", db, config)
        rows2 = db.conn.execute("SELECT * FROM segments WHERE job_id=?", ("job1",)).fetchall()
        assert len(rows2) == 1, f"Re-run caused duplicates: {len(rows2)}"

        db.close()
        print("OK test_analyze_stage_with_mock")
    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    test_chunk_transcript_empty()
    test_chunk_transcript_overlap_guard()
    test_chunk_transcript_basic()
    test_format_chunk_for_prompt()
    test_overlap_ratio()
    test_merge_and_dedupe()
    with tempfile.TemporaryDirectory() as tmp:
        test_analyze_stage_with_mock(Path(tmp))
    print("\nAll analyze tests passed.")
