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
    deduplicate_overlapping_segments,
    fallback_caption,
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


def test_deduplicate_overlapping_segments():
    # Empty list
    assert deduplicate_overlapping_segments([]) == []

    # Non-overlapping: chronological order is restored
    a = _pyd_seg("00:01:00", "00:02:00", conf=0.7)
    b = _pyd_seg("00:03:00", "00:04:00", conf=0.8)
    res = deduplicate_overlapping_segments([b, a])
    assert len(res) == 2
    assert res[0].start == "00:01:00"
    assert res[1].start == "00:03:00"

    # Overlapping (>0.65 overlap) - higher confidence kept
    s1 = _pyd_seg("00:01:00", "00:02:00", conf=0.6)
    s2 = _pyd_seg("00:01:10", "00:02:00", conf=0.9)
    res2 = deduplicate_overlapping_segments([s1, s2])
    assert len(res2) == 1
    assert res2[0].confidence == 0.9

    # Overlapping (>0.65 overlap) - hook_score takes precedence over confidence
    s3 = _pyd_seg("00:01:00", "00:02:00", conf=0.95)
    s4 = _pyd_seg("00:01:05", "00:02:05", conf=0.60)
    setattr(s3, "hook_score", 5)
    setattr(s4, "hook_score", 9)
    res3 = deduplicate_overlapping_segments([s3, s4])
    assert len(res3) == 1
    assert getattr(res3[0], "hook_score") == 9

    # Partial overlap under threshold (20s overlap / 60s min dur = 0.33 <= 0.65)
    s5 = _pyd_seg("00:01:00", "00:02:00", conf=0.7)
    s6 = _pyd_seg("00:01:40", "00:02:40", conf=0.8)
    res4 = deduplicate_overlapping_segments([s5, s6])
    assert len(res4) == 2
    print("OK test_deduplicate_overlapping_segments")


def test_analyze_stage_with_mock(tmp_path: Path):
    """End-to-end AnalyzeStage dengan mock Gemini — verifikasi file output,
    DB insert, metric recording, is_complete."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Setup: buat transcript, prompts, .env
        Path("data/transcripts").mkdir(parents=True)
        Path("prompts/presets").mkdir(parents=True)
        Path("prompts/presets/affiliate.txt").write_text("test prompt", encoding="utf-8")
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
        orig_analyze_chunk = analyze.analyze_chunk
        orig_generate_captions = analyze.generate_captions
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
        # Restore mock — tanpa ini, lambda keleak ke test lain dan
        # analyze_chunk/analyze.generate_captions tidak pernah raise.
        analyze.analyze_chunk = orig_analyze_chunk
        analyze.generate_captions = orig_generate_captions
        os.chdir(old_cwd)


if __name__ == "__main__":
    test_chunk_transcript_empty()
    test_chunk_transcript_overlap_guard()
    test_chunk_transcript_basic()
    test_format_chunk_for_prompt()
    test_overlap_ratio()
    test_merge_and_dedupe()
    test_deduplicate_overlapping_segments()
    with tempfile.TemporaryDirectory() as tmp:
        test_analyze_stage_with_mock(Path(tmp))
    print("\nAll analyze tests passed.")


def test_analyze_chunk_retries_3x_then_raises(monkeypatch):
    """Bug: try/except di dalam analyze_chunk menelan exception → tenacity retry
    tidak pernah jalan. Harus retry 3x lalu raise ke caller."""
    from unittest.mock import MagicMock

    import tenacity.nap as nap
    from stages.analyze import analyze_chunk

    monkeypatch.setattr(nap, "sleep", lambda s: None)  # percepat backoff
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("boom")

    from tenacity import RetryError
    try:
        analyze_chunk(client, "sys", "text", "gemini-x")
        assert False, "Harus raise setelah 3 attempt"
    except RetryError:
        assert client.models.generate_content.call_count == 3, \
            f"Expected 3 attempts, got {client.models.generate_content.call_count}"


def test_generate_captions_batch_split_and_partial_failure(monkeypatch):
    """Caption dipecah per 8 segmen: 10 segmen = 2 call. Batch 2 gagal →
    caption batch 1 tetap ada (bukan semua kosong)."""
    import json as _json
    from types import SimpleNamespace

    import tenacity.nap as nap
    from stages.analyze import Segment, generate_captions

    monkeypatch.setattr(nap, "sleep", lambda s: None)

    segs = [
        Segment(start=f"00:0{i}:00", end=f"00:0{i}:30",
                product_mentioned=f"Produk{i}", topic="skincare",
                confidence=0.8, reason="r")
        for i in range(10)
    ]

    # batch 1 = 8 segmen (selalu gagal → 3x retry → skip), batch 2 = 2 segmen
    # (sukses). Bukti: idx GLOBAL tetap benar + batch lain tidak ikut hilang.
    def flaky(model, contents, config):
        payload = _json.loads(contents)
        if len(payload) > 5:
            raise RuntimeError("gemini down")
        return SimpleNamespace(parsed=SimpleNamespace(
            captions=[SimpleNamespace(idx=p["idx"], caption=f"cap{p['idx']}")
                      for p in payload]))

    client2 = SimpleNamespace()
    client2.models = SimpleNamespace(generate_content=flaky)
    caps = generate_captions(client2, "sys", segs, "model")
    # Hanya batch 2 (idx global 8,9) yang selamat; caption ber-INDEX LOCAL
    # batch-nya (model menjawab per posisi batch), mapping global di kunci.
    assert sorted(caps) == [8, 9], f"got {sorted(caps)}"
    assert caps[8] == "cap0" and caps[9] == "cap1", "kunci global harus konsisten"


def test_generate_captions_batch_2_failure_keeps_batch_1(monkeypatch):
    import json as _json
    from types import SimpleNamespace

    import tenacity.nap as nap
    from stages.analyze import Segment, generate_captions

    monkeypatch.setattr(nap, "sleep", lambda s: None)

    segs = [
        Segment(start=f"00:0{i}:00", end=f"00:0{i}:30",
                product_mentioned=f"P{i}", topic="s",
                confidence=0.8, reason="r")
        for i in range(10)
    ]

    def always_fail(model, contents, config):
        raise RuntimeError("down")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=always_fail))
    caps = generate_captions(client, "sys", segs, "model")
    # Semua batch gagal (3x retry) → kosong, bukan raise
    assert caps == {}


def test_fallback_caption():
    from stages.analyze import Segment, fallback_caption
    seg = Segment(start="00:01:00", end="00:02:00", product_mentioned="Vaseline",
                  topic="body care routine", confidence=0.8, reason="r")
    assert fallback_caption(seg) == "Vaseline — body care routine"
    empty = Segment(start="00:01:00", end="00:02:00", product_mentioned="",
                    topic="", confidence=0.8, reason="r")
    assert fallback_caption(empty) == "Klip produk"


def test_analyze_stage_chunk_failure_does_not_fail_job(tmp_path):
    """Exception chunk individual tidak boleh menggagalkan job — stage tetap DONE
    dengan 0 segmen, file output tetap ditulis (kosong)."""
    import threading

    import runtime
    from stages import analyze

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        Path("data/transcripts").mkdir(parents=True)
        Path("prompts/presets").mkdir(parents=True)
        Path("prompts/presets/affiliate.txt").write_text("test prompt", encoding="utf-8")
        Path("prompts/caption_generator.txt").write_text("test caption prompt", encoding="utf-8")

        transcript = [
            {"text": "Aku pakai serum vitamin C tiap pagi", "start": 10.0, "end": 13.5, "words": []},
            {"text": "Efeknya kulit lebih cerah", "start": 14.0, "end": 17.0, "words": []},
        ]
        Path("data/transcripts/job2.json").write_text(
            json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
        )

        import sqlite3
        from db.jobs import init_db, JobDB
        init_db()
        db = JobDB()
        db.create_job("job2", "https://youtube.com/watch?v=job2")

        orig_analyze_chunk = analyze.analyze_chunk
        analyze.analyze_chunk = lambda client, sp, ct, model: (_ for _ in ()).throw(RuntimeError("boom"))

        from types import SimpleNamespace
        config = SimpleNamespace(
            google_api_key="fake",
            analyze_model="gemini-2.5-flash",
            chunk_duration_min=20,
            chunk_overlap_min=2,
            confidence_threshold=0.6,
        )
        runtime.reset()
        try:
            result = analyze.AnalyzeStage().run("job2", db, config)
        finally:
            analyze.analyze_chunk = orig_analyze_chunk
            db.close()
            runtime.unregister(threading.get_ident())

        # SEMUA chunk gagal → FAILED dengan pesan jelas (bukan done + notice
        # '0 segmen' yang menyesatkan — kasus nyata: quota 429 habis).
        assert result.status.value == "failed", f"status={result.status}"
        assert "Gemini API gagal di semua chunk" in result.error, result.error
        out = Path("data/segments/job2.json")
        assert out.exists(), "Output file tetap harus ditulis"
        assert json.loads(out.read_text(encoding="utf-8")) == []
    finally:
        os.chdir(old_cwd)


def test_segment_schema_new_fields():
    import pydantic
    import pytest

    # Test default values
    s_default = Segment(
        start="00:01:00", end="00:02:00",
        product_mentioned="Serum A", topic="Skincare",
        confidence=0.85, reason="Bagus"
    )
    assert s_default.hook_score == 85
    assert s_default.virality_reason == ""
    assert s_default.affiliate_caption == ""
    assert s_default.hashtags == []

    # Test custom values
    s_custom = Segment(
        start="00:01:00", end="00:02:00",
        product_mentioned="Serum A", topic="Skincare",
        confidence=0.9, reason="Detail",
        hook_score=92,
        virality_reason="Transformasi cepat",
        affiliate_caption="Klik keranjang kuning sekarang! ✨",
        hashtags=["#racuntiktok", "#affiliate", "#skincare"]
    )
    assert s_custom.hook_score == 92
    assert s_custom.virality_reason == "Transformasi cepat"
    assert s_custom.affiliate_caption == "Klik keranjang kuning sekarang! ✨"
    assert s_custom.hashtags == ["#racuntiktok", "#affiliate", "#skincare"]

    # Test validation (hook_score 0-100)
    with pytest.raises(pydantic.ValidationError):
        Segment(
            start="00:01:00", end="00:02:00",
            product_mentioned="Serum A", topic="Skincare",
            confidence=0.9, reason="Detail",
            hook_score=105
        )

    with pytest.raises(pydantic.ValidationError):
        Segment(
            start="00:01:00", end="00:02:00",
            product_mentioned="Serum A", topic="Skincare",
            confidence=0.9, reason="Detail",
            hook_score=-5
        )


def test_fallback_caption_with_affiliate():
    s = Segment(
        start="00:01:00", end="00:02:00",
        product_mentioned="Somethinc Serum",
        topic="Kulit cerah",
        confidence=0.88,
        reason="Detail review",
        hook_score=90,
        virality_reason="Viral review",
        affiliate_caption="Wajib coba ini guys! Klik keranjang kuning ✨",
        hashtags=["#racuntiktok", "#affiliate"]
    )
    fb = fallback_caption(s)
    assert "Wajib coba ini guys!" in fb
    assert "#racuntiktok #affiliate" in fb


def test_get_preset_prompt():
    from stages.analyze import get_preset_prompt
    for p in ["affiliate", "podcast", "comedy", "education", "storytelling"]:
        txt = get_preset_prompt(p)
        assert txt and len(txt) > 50
    # Fallback to affiliate/product_detection on unknown
    fallback = get_preset_prompt("unknown_preset")
    assert fallback and len(fallback) > 50


