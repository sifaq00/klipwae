"""Analyze failure semantics: semua chunk gagal → FAILED (bukan '0 segmen'
yang menyesatkan user — kasus nyata: quota Gemini 429 free-tier habis).
+ fallback otomatis ke model cadangan saat 429."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.analyze import analyze_failure_message, _is_quota_error


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


def test_quota_error_detection():
    assert _is_quota_error(RuntimeError("429 RESOURCE_EXHAUSTED quota"))
    assert _is_quota_error(RuntimeError("RESOURCE_EXHAUSTED: limit 20"))
    assert not _is_quota_error(RuntimeError("ServerError 500"))
    assert not _is_quota_error(RuntimeError("boom"))


def test_analyze_chunk_falls_back_on_quota():
    """Primary 429 -> fallback model dipakai; non-429 -> error asli di-propagate."""
    import stages.analyze as analyze

    calls = []

    def fake_retry(client, sp, ct, model):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
        return ([], {})

    orig = analyze._analyze_chunk_retry
    analyze._analyze_chunk_retry = fake_retry
    try:
        segs, _ = analyze.analyze_chunk(None, "sp", "ct", "gemini-flash-latest",
                                        fallback_model="gemini-3.6-flash")
    finally:
        analyze._analyze_chunk_retry = orig
    assert calls == ["gemini-flash-latest", "gemini-3.6-flash"], calls
    assert segs == []


def test_analyze_chunk_chain_falls_to_last_resort():
    """3.6 gagal (503) → cadangan terakhir 3.5-flash dipakai."""
    import stages.analyze as analyze

    calls = []

    def fake_retry(client, sp, ct, model):
        calls.append(model)
        if model == "gemini-flash-latest":
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
        if model == "gemini-3.6-flash":
            raise RuntimeError("503 UNAVAILABLE high demand")
        return ([], {})

    orig = analyze._analyze_chunk_retry
    analyze._analyze_chunk_retry = fake_retry
    try:
        segs, _ = analyze.analyze_chunk(None, "sp", "ct", "gemini-flash-latest",
                                        fallback_model="gemini-3.6-flash")
    finally:
        analyze._analyze_chunk_retry = orig
    assert calls == ["gemini-flash-latest", "gemini-3.6-flash", "gemini-3.5-flash"], calls
    assert segs == []


def test_tenacity_skips_retry_on_quota_error():
    """429 tidak boleh di-retry tenacity (predicate skip) -> 1 attempt saja."""
    import stages.analyze as analyze
    from unittest.mock import patch

    attempts = {"n": 0}

    class FakeModels:
        def generate_content(self, **kw):
            attempts["n"] += 1
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")

    class FakeClient:
        models = FakeModels()

    with patch.object(analyze, "_is_quota_error", return_value=True):
        try:
            analyze._analyze_chunk_retry(FakeClient(), "sp", "ct", "m")
            assert False, "harus raise"
        except RuntimeError:
            pass
    assert attempts["n"] == 1, f"429 harus 1 attempt (tanpa retry), got {attempts['n']}"


def test_tenacity_retries_non_quota_three_times():
    """503/500 tetap di-retry 3x oleh tenacity."""
    import stages.analyze as analyze
    from unittest.mock import patch

    attempts = {"n": 0}

    class FakeModels:
        def generate_content(self, **kw):
            attempts["n"] += 1
            raise RuntimeError("ServerError 500")

    class FakeClient:
        models = FakeModels()

    with patch.object(analyze, "_is_quota_error", return_value=False):
        import tenacity
        try:
            analyze._analyze_chunk_retry(FakeClient(), "sp", "ct", "m")
            assert False, "harus raise"
        except tenacity.RetryError:
            pass
    assert attempts["n"] == 3, f"503 harus 3 attempt (tenacity), got {attempts['n']}"


def test_analyze_chunk_no_fallback_on_other_error():
    import stages.analyze as analyze

    def fake_retry(client, sp, ct, model):
        raise RuntimeError("ServerError 500")

    orig = analyze._analyze_chunk_retry
    analyze._analyze_chunk_retry = fake_retry
    try:
        try:
            analyze.analyze_chunk(None, "sp", "ct", "gemini-flash-latest",
                                  fallback_model="gemini-3.6-flash")
            assert False, "harus raise"
        except RuntimeError as e:
            assert "ServerError" in str(e)
    finally:
        analyze._analyze_chunk_retry = orig


if __name__ == "__main__":
    test_partial_failure_ok()
    test_all_failed_generic()
    test_all_failed_quota_message()
    test_no_chunks_processed()
    test_quota_error_detection()
    test_analyze_chunk_falls_back_on_quota()
    test_analyze_chunk_chain_falls_to_last_resort()
    test_analyze_chunk_no_fallback_on_other_error()
    print("all ok")