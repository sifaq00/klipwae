"""Golden test untuk stage analyze — bandingkan hasil LLM vs expected_segments.

Plan Section 16: cara paling reliable untuk tuning prompt secara terukur.
Cek: (1) ada segmen hasil LLM yang overlap besar dengan expected_segments,
(2) confidence di atas min_confidence. Tidak cek exact match teks topic/reason.

Fixture sintetis dibuat berdasarkan contoh plan Section 10.7f.
Plan Section 23.3 bilang "idealnya dari transkrip podcast asli yang sudah
ditandai manual, bukan cuma contoh sintetis" — fixture asli butuh kerja
manual marking, tunda sampai punya akses podcast asli.
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.analyze import Segment, format_chunk_for_prompt, merge_and_dedupe, overlap_ratio
from utils.time_helpers import hms_to_sec

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "golden_transcripts"


def _seg(start: str, end: str, conf: float = 0.8) -> Segment:
    return Segment(start=start, end=end, product_mentioned="x", topic="t", confidence=conf, reason="r")


def _overlap_with_expected(found: Segment, expected: dict) -> bool:
    """Cek apakah found segmen overlap >70% dengan expected (terhadap segmen
    lebih pendek), dan confidence di atas min_confidence."""
    exp_start = hms_to_sec(expected["start"])
    exp_end = hms_to_sec(expected["end"])
    found_start = hms_to_sec(found.start)
    found_end = hms_to_sec(found.end)
    overlap = max(0.0, min(found_end, exp_end) - max(found_start, exp_start))
    shorter = min(found_end - found_start, exp_end - exp_start)
    ratio = overlap / shorter if shorter > 0 else 0.0
    return ratio >= 0.7 and found.confidence >= expected.get("min_confidence", 0.75)


def _run_fixture(fixture_path: Path, mock_analyze):
    """Jalankan stage analyze dengan mock LLM, return (found_segments, expected)."""
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    transcript = [
        SimpleNamespace(text=s["text"], start=s["start"], end=s["end"])
        for s in data["transcript"]
    ]
    # Mock analyze_chunk supaya test tidak panggil Gemini asli
    from stages import analyze
    original = analyze.analyze_chunk
    analyze.analyze_chunk = mock_analyze
    try:
        from stages.analyze import AnalyzeStage
        # Patch analyze_chunk return sesuai fixture expected
        segs = [_seg(e["start"], e["end"], conf=e.get("min_confidence", 0.8)) for e in data["expected_segments"]]
        mock_analyze.return_value = (segs, {"input_tokens": 100, "output_tokens": 50})
        # Run via direct call (skip DB, file IO)
        # Format chunk dan panggil analyze_chunk langsung
        chunks = analyze.chunk_transcript(transcript, chunk_min=20, overlap_min=2)
        all_segs = []
        for c in chunks:
            segs_chunk, _ = analyze.analyze_chunk(None, "prompt", format_chunk_for_prompt(c), "mock")
            all_segs.extend(segs_chunk)
        merged = merge_and_dedupe(all_segs)
        return merged, data["expected_segments"]
    finally:
        analyze.analyze_chunk = original


def _check(found: list, expected: list, name: str) -> bool:
    """Setiap expected harus punya match di found. Negatif test: expected kosong,
    found harus kosong juga."""
    if not expected:
        if found:
            print(f"FAIL {name}: expected 0 segments, found {len(found)}")
            return False
        print(f"OK {name}: 0 segments (correct)")
        return True
    for exp in expected:
        match = any(_overlap_with_expected(f, exp) for f in found)
        if not match:
            print(f"FAIL {name}: no match for expected [{exp['start']}-{exp['end']}]")
            return False
    print(f"OK {name}: {len(found)} segments match {len(expected)} expected")
    return True


def test_golden_fixtures():
    """Jalankan semua fixture di golden_transcripts/. Karena ini test mock
    (analyze_chunk return expected), test ini memvalidasi plumbing (chunking,
    merge, overlap check) bukan akurasi LLM asli. LLM asli divalidasi manual
    di Fase 6 (plan Section 19)."""
    from unittest.mock import MagicMock
    mock = MagicMock()

    failures = 0
    for fixture in sorted(FIXTURES_DIR.glob("*.json")):
        found, expected = _run_fixture(fixture, mock)
        if not _check(found, expected, fixture.name):
            failures += 1

    if failures:
        print(f"\n{failures} fixture(s) failed")
        sys.exit(1)
    print("\nAll golden fixtures passed.")


def test_fixture_format():
    """Validasi format fixture sesuai plan Section 10.7f."""
    for fixture in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(fixture.read_text(encoding="utf-8"))
        assert "transcript" in data, f"{fixture.name}: missing transcript"
        assert "expected_segments" in data, f"{fixture.name}: missing expected_segments"
        for s in data["transcript"]:
            assert "text" in s and "start" in s and "end" in s, f"{fixture.name}: bad transcript entry"
        for e in data["expected_segments"]:
            assert "start" in e and "end" in e, f"{fixture.name}: bad expected entry"
    print(f"OK test_fixture_format ({len(list(FIXTURES_DIR.glob('*.json')))} fixtures)")


if __name__ == "__main__":
    test_fixture_format()
    test_golden_fixtures()
