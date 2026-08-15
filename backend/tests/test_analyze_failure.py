"""Analyze failure semantics: semua chunk gagal → FAILED (bukan '0 segmen'
yang menyesatkan user — kasus nyata: quota Gemini 429 free-tier habis)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.analyze import analyze_failure_message


def test_partial_failure_ok():
    assert analyze_failure_message(3, ["err1"], []) is None  # sebagian gagal
    assert analyze_failure_message(3, ["err1", "err2"], [{"seg": 1}]) is None  # ada segmen


def test_all_failed_generic():
    msg = analyze_failure_message(2, ["ServerError 500", "ServerError 500"], [])
    assert msg is not None
    assert "Gemini API gagal" in msg


def test_all_failed_quota_message():
    msg = analyze_failure_message(2, ["429 RESOURCE_EXHAUSTED quota", "429 RESOURCE_EXHAUSTED quota"], [])
    assert msg is not None
    assert "Kuota Gemini habis" in msg
    assert "429" in msg


def test_no_chunks_processed():
    assert analyze_failure_message(0, [], []) is None


if __name__ == "__main__":
    test_partial_failure_ok()
    test_all_failed_generic()
    test_all_failed_quota_message()
    test_no_chunks_processed()
    print("all ok")