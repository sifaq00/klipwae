import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


def _runner():
    r = server.JobRunner("testjob", "https://example.com")
    r.log_buffer.clear()
    r._log_seq = 0
    return r


def test_recent_logs_after_500_lines_does_not_freeze():
    """Bug: buffer maxlen=500. Klien yang KETINGGALAN jauh (since di bawah
    window buffer) harus di-replay dari awal buffer — dulu dikasih slice
    kosong selamanya → SSE beku diam-diam."""
    r = _runner()
    for i in range(600):
        r._log(f"line {i}")
    assert len(r.log_buffer) == 500  # window sekarang index 100..599

    # Klien stuck di since=100 (ketinggalan 500 baris) → replay seluruh window
    got = r.recent_logs(100)
    assert len(got) == 500, f"harus replay seluruh buffer, got {len(got)}"
    assert got[0] == "line 100" and got[-1] == "line 599"


def test_recent_logs_caught_up_gets_new_lines():
    r = _runner()
    for i in range(600):
        r._log(f"line {i}")
    # Klien sudah menerima sampai sejak=600 (up-to-date) → baris BARU muncul
    assert r.recent_logs(600) == []
    r._log("line 600")
    assert r.recent_logs(600) == ["line 600"]


def test_recent_logs_in_window():
    r = _runner()
    for i in range(600):
        r._log(f"line {i}")
    # since di dalam window buffer (base=100): hanya baris sejak base
    got = r.recent_logs(200)
    assert len(got) == 400, f"got {len(got)}"
    assert got[0] == "line 200"


def test_recent_logs_initial():
    r = _runner()
    r._log("a")
    r._log("b")
    assert r.recent_logs(0) == ["a", "b"]
    assert r.recent_logs(1) == ["b"]
    assert r.recent_logs(99) == []  # tidak ada baris baru, bukan replay lagi