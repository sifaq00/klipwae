import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.ingest import extract_video_id, get_yt_metadata
import server as server_mod


def test_extract_video_id():
    cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/abc1234567x", "abc1234567x"),
        ("https://m.youtube.com/watch?v=abcdefghijk", "abcdefghijk"),
        ("https://youtube.com/shorts/123456789ab", "123456789ab"),
        ("https://vimeo.com/12345", None),
        ("not a url", None),
        ("", None),
    ]
    for url, expected in cases:
        got = extract_video_id(url)
        assert got == expected, f"{url!r} -> {got!r}, expected {expected!r}"
    print("OK test_extract_video_id")


def test_get_yt_metadata_parses_and_decodes_utf8():
    fake = subprocess.CompletedProcess([], 0, stdout='{"title": "Serum Hanasui 100%", "duration": 132, "channel": "Kanal A"}', stderr="")
    orig = get_yt_metadata.__globals__["subprocess_run"]
    get_yt_metadata.__globals__["subprocess_run"] = lambda args, timeout=600: fake
    try:
        meta = get_yt_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert meta == {"title": "Serum Hanasui 100%", "duration": 132, "channel": "Kanal A"}, meta
    finally:
        get_yt_metadata.__globals__["subprocess_run"] = orig
    print("OK test_get_yt_metadata_parses_and_decodes_utf8")


def test_get_yt_metadata_nonzero_rc_returns_none():
    fake = subprocess.CompletedProcess([], 1, stdout="", stderr="error")
    orig = get_yt_metadata.__globals__["subprocess_run"]
    get_yt_metadata.__globals__["subprocess_run"] = lambda args, timeout=600: fake
    try:
        assert get_yt_metadata("https://youtu.be/abc") is None
    finally:
        get_yt_metadata.__globals__["subprocess_run"] = orig
    print("OK test_get_yt_metadata_nonzero_rc_returns_none")


def test_get_yt_metadata_timeout_and_bad_json_return_none():
    def boom(args, timeout=600):
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)
    orig = get_yt_metadata.__globals__["subprocess_run"]
    try:
        get_yt_metadata.__globals__["subprocess_run"] = boom
        assert get_yt_metadata("https://youtu.be/abc") is None
        get_yt_metadata.__globals__["subprocess_run"] = lambda args, timeout=600: subprocess.CompletedProcess([], 0, stdout="not json", stderr="")
        assert get_yt_metadata("https://youtu.be/abc") is None
    finally:
        get_yt_metadata.__globals__["subprocess_run"] = orig
    print("OK test_get_yt_metadata_timeout_and_bad_json_return_none")


def test_fetch_meta_early_skips_write_when_duration_missing():
    """Guard: title ADA tapi duration None → jangan tulis metadata parsial."""
    from unittest.mock import patch
    db = MagicMock()
    with patch.object(server_mod, "JobDB", return_value=db), \
         patch("stages.ingest.get_yt_metadata", return_value={"title": "T", "duration": None, "channel": "C"}):
        server_mod._fetch_meta_early("partial", "https://youtu.be/abc")
    db.update_job_metadata.assert_not_called()
    print("OK test_fetch_meta_early_skips_write_when_duration_missing")


def test_fetch_meta_early_writes_db():
    from unittest.mock import patch
    job_id = "earlymeta"
    db = MagicMock()
    with patch.object(server_mod, "JobDB", return_value=db), \
         patch("stages.ingest.get_yt_metadata", return_value={"title": "T", "duration": 60, "channel": "C"}):
        server_mod._fetch_meta_early(job_id, "https://youtu.be/abc")
    db.update_job_metadata.assert_called_once()
    kwargs = db.update_job_metadata.call_args.kwargs
    assert kwargs["title"] == "T" and kwargs["duration_sec"] == 60 and kwargs["channel"] == "C"
    db.close.assert_called_once()
    print("OK test_fetch_meta_early_writes_db")


def test_fetch_meta_early_quiet_on_failure():
    from unittest.mock import patch
    with patch.object(server_mod, "JobDB") as jdb, \
         patch("stages.ingest.get_yt_metadata", return_value=None):
        server_mod._fetch_meta_early("x", "https://youtu.be/abc")  # tak boleh raise
    jdb.assert_not_called()
    print("OK test_fetch_meta_early_quiet_on_failure")


if __name__ == "__main__":
    test_extract_video_id()
    test_get_yt_metadata_parses_and_decodes_utf8()
    test_get_yt_metadata_nonzero_rc_returns_none()
    test_get_yt_metadata_timeout_and_bad_json_return_none()
    test_fetch_meta_early_writes_db()
    test_fetch_meta_early_skips_write_when_duration_missing()
    test_fetch_meta_early_quiet_on_failure()
    print("all ok")
