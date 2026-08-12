import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.clip import align_boundary, load_segments, split_segment_ranges, ClipStage


def _fake_seg(start="00:01:00", end="00:01:10", product="serum", conf=0.8, topic="skincare"):
    return SimpleNamespace(
        start=start, end=end, product_mentioned=product,
        topic=topic, confidence=conf,
    )


def test_load_segments_missing():
    assert load_segments(Path("nonexistent.json")) == []
    print("OK test_load_segments_missing")


def test_load_segments_empty(tmp_path):
    f = tmp_path / "empty.json"
    f.write_text("[]", encoding="utf-8")
    assert load_segments(f) == []
    print("OK test_load_segments_empty")


def test_load_segments_valid(tmp_path):
    data = [{"start": "00:01:00", "end": "00:01:10", "product_mentioned": "serum",
             "topic": "skincare", "confidence": 0.85,
             "caption_text": "Serum ini wajib coba! #skincare"}]
    f = tmp_path / "seg.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    segs = load_segments(f)
    assert len(segs) == 1
    assert segs[0].product_mentioned == "serum"
    assert segs[0].confidence == 0.85
    assert segs[0].caption_text == "Serum ini wajib coba! #skincare"
    print("OK test_load_segments_valid")


def test_clip_path_naming():
    stage = ClipStage()
    seg = _fake_seg(product="serum vitamin C", conf=0.85)
    p = stage._clip_path("abc123", 0, seg)
    assert "abc123" in p.name
    assert "000" in p.name
    assert "serum_vitamin_c" in p.name
    assert "conf85" in p.name
    assert p.suffix == ".mp4"
    print("OK test_clip_path_naming")


def test_clip_path_none_product():
    stage = ClipStage()
    seg = _fake_seg(product=None)
    p = stage._clip_path("abc", 1, seg)
    assert "unknown" in p.name
    print("OK test_clip_path_none_product")


def test_clip_stage_no_segments(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        Path("data/raw").mkdir(parents=True)
        Path("data/segments").mkdir()
        Path("data/raw/job1.mp4").touch()
        Path("data/segments/job1.json").write_text("[]", encoding="utf-8")

        config = SimpleNamespace()
        result = ClipStage().run("job1", None, config)
        assert result.status.value == "done"
        assert result.metadata["clips_created"] == 0
        print("OK test_clip_stage_no_segments")
    finally:
        os.chdir(old_cwd)


def test_clip_stage_missing_raw(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        Path("data/segments").mkdir(parents=True)
        Path("data/segments/job1.json").write_text(
            json.dumps([{"start": "00:01:00", "end": "00:01:10", "product_mentioned": "x",
                         "topic": "t", "confidence": 0.8}]), encoding="utf-8"
        )
        config = SimpleNamespace()
        result = ClipStage().run("job1", None, config)
        assert result.status.value == "failed"
        print("OK test_clip_stage_missing_raw")
    finally:
        os.chdir(old_cwd)


def test_is_complete_no_segments(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        Path("data/segments").mkdir(parents=True)
        Path("data/segments/job1.json").write_text("[]", encoding="utf-8")
        assert ClipStage().is_complete("job1", None) is True
        print("OK test_is_complete_no_segments")
    finally:
        os.chdir(old_cwd)


def test_split_segment_ranges_short():
    assert split_segment_ranges(0, 45, []) == [(0, 45)]
    print("OK test_split_segment_ranges_short")


def test_split_segment_ranges_no_words():
    # Tidak ada kata → potong persis di max_sec (60s)
    ranges = split_segment_ranges(0, 130, [])
    assert len(ranges) == 3
    assert all(e - s <= 60.001 for s, e in ranges)
    assert ranges[0] == (0, 60)
    assert ranges[1] == (60, 120)
    assert ranges[2] == (120, 130)
    print("OK test_split_segment_ranges_no_words")


def test_split_segment_ranges_gap():
    # Jeda besar di detik 30 → potong di awal kata setelah jeda
    words = [
        {"text": f"w{i}", "start": float(i), "end": float(i + 0.4)} for i in range(30)
    ]
    words += [
        {"text": f"w{i}", "start": float(i + 2.0), "end": float(i + 2.4)} for i in range(30, 100)
    ]
    ranges = split_segment_ranges(0, 100, words)
    assert ranges[0][1] == 32.0  # potong di awal kata setelah jeda
    assert ranges[-1][1] == 100
    assert all(e - s <= 60.001 for s, e in ranges)
    print(f"OK test_split_segment_ranges_gap ({ranges})")


def test_split_segment_ranges_deterministic():
    words = [{"text": "x", "start": float(i), "end": float(i + 0.5)} for i in range(200)]
    a = split_segment_ranges(10, 170, words)
    b = split_segment_ranges(10, 170, words)
    assert a == b
    print("OK test_split_segment_ranges_deterministic")


def test_split_segment_ranges_respects_min():
    # Potongan tidak boleh sebelum min_sec dari cursor
    words = [{"text": "x", "start": float(i), "end": float(i + 0.5)} for i in range(0, 100)]
    # gap besar di detik 5 (di bawah min_sec) → harus diabaikan, potong di 60
    words = [w for w in words if w["start"] != 5] + [{"text": "gap", "start": 5.0, "end": 6.0}]
    words.sort(key=lambda w: w["start"])
    ranges = split_segment_ranges(0, 100, words, min_sec=25)
    assert ranges[0][1] == 60.0
    print("OK test_split_segment_ranges_respects_min")


def test_align_start_moves_back_to_gap():
    # jeda 2.2s sebelum kata "d" → sec=6.5 di tengah kalimat d-e → mundur ke awal d (5.0)
    words = [
        {"text": "a", "start": 0.0, "end": 0.8},
        {"text": "b", "start": 1.0, "end": 1.8},
        {"text": "c", "start": 2.0, "end": 2.8},
        {"text": "d", "start": 5.0, "end": 5.8},
        {"text": "e", "start": 6.0, "end": 6.8},
    ]
    assert align_boundary(words, 6.5, "start") == 5.0


def test_align_start_no_gap_in_window():
    words = [
        {"text": "a", "start": 0.0, "end": 0.9},
        {"text": "b", "start": 1.0, "end": 1.9},
        {"text": "c", "start": 2.0, "end": 2.9},
    ]
    assert align_boundary(words, 2.5, "start") == 2.5


def test_align_end_moves_forward_to_next_sentence():
    words = [
        {"text": "a", "start": 0.0, "end": 0.8},
        {"text": "b", "start": 1.0, "end": 1.8},
        {"text": "c", "start": 2.0, "end": 2.8},
        {"text": "d", "start": 6.0, "end": 6.8},   # gap 3.2s sebelum d
    ]
    # sec=3 di tengah jeda, kalimat lanjut di 6.0 → end = 6.0 (awal kalimat baru)
    assert align_boundary(words, 3.0, "end") == 6.0


def test_align_end_no_gap_in_window():
    words = [
        {"text": "a", "start": 0.0, "end": 0.8},
        {"text": "b", "start": 1.0, "end": 1.8},
    ]
    assert align_boundary(words, 1.5, "end") == 1.5


def test_align_empty_words():
    assert align_boundary([], 5.0, "start") == 5.0
    assert align_boundary([], 5.0, "end") == 5.0


if __name__ == "__main__":
    test_load_segments_missing()
    test_load_segments_empty(Path(tempfile.mkdtemp()))
    test_load_segments_valid(Path(tempfile.mkdtemp()))
    test_clip_path_naming()
    test_clip_path_none_product()
    with tempfile.TemporaryDirectory() as tmp:
        test_clip_stage_no_segments(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_clip_stage_missing_raw(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_is_complete_no_segments(Path(tmp))
    print("\nAll clip tests passed.")
