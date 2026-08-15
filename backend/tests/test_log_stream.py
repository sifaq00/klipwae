import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


def _runner():
    server._JOB_LOG_SEQ.pop("testjob", None)
    r = server.JobRunner("testjob", "https://example.com")
    r.log_buffer.clear()
    return r


def test_recent_logs_after_500_lines_does_not_freeze():
    """Bug: buffer maxlen=500. Klien yang KETINGGALAN jauh (since di bawah
    window buffer) harus di-replay dari awal buffer — dulu dikasih slice
    kosong selamanya → SSE beku diam-diam."""
    r = _runner()
    for i in range(600):
        r._log(f"line {i}")
    assert len(r.log_buffer) == 500  # window sekarang seq 101..600

    # Klien stuck di since=100 (ketinggalan jauh) → replay seluruh window
    got = r.recent_logs(100)
    assert len(got) == 500, f"harus replay seluruh buffer, got {len(got)}"
    assert got[0] == "line 100" and got[-1] == "line 599"


def test_recent_logs_caught_up_gets_new_lines():
    r = _runner()
    for i in range(600):
        r._log(f"line {i}")
    # Klien sudah menerima sampai since=600 (up-to-date) → baris BARU muncul
    assert r.recent_logs(600) == []
    r._log("line 600")
    assert r.recent_logs(600) == ["line 600"]


def test_recent_logs_in_window():
    r = _runner()
    for i in range(600):
        r._log(f"line {i}")
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


def test_seq_survives_new_runner_retry():
    """Bug inti retry: runner BARU me-reset buffer tapi seq harus LANJUT —
    kalau tidak, klien sejak >500 langsung beku di runner baru."""
    server._JOB_LOG_SEQ.pop("testjob", None)
    r1 = server.JobRunner("testjob", "https://example.com")
    r1.log_buffer.clear()
    for i in range(600):
        r1._log(f"line {i}")  # seq 1..600

    # Job di-retry → runner LAMA mati, runner BARU (buffer kosong)
    r2 = server.JobRunner("testjob", "https://example.com")
    r2.log_buffer.clear()
    assert r2.recent_logs(600) == []  # belum ada baris baru
    r2._log("line 601")  # seq LANJUT 601, bukan reset ke 1
    got = r2.recent_logs(600)
    assert got == ["line 601"], f"got {got}"
    server._JOB_LOG_SEQ.pop("testjob", None)


def test_two_jobs_stdout_does_not_cross():
    """Bug: 2 job jalan bareng. redirect_stdout GLOBAL → sys.stdout di-race
    antar thread, print job A bocor ke buffer/SSE job B (progress bar
    saling tumpang tindih). Proxy harus route per-thread ke log masing-masing."""
    import threading
    from io import StringIO

    got: dict[str, list[str]] = {"a": [], "b": []}

    class FakeLog:
        def __init__(self, name: str):
            self.name = name
        def __call__(self, msg: str):
            got[self.name].append(msg)

    fallback = StringIO()
    proxy = server._ThreadRoutedStdout(fallback)

    def worker(name: str):
        stream = server._LogStream(FakeLog(name))
        server.JobRunner._thread_streams[threading.get_ident()] = stream
        try:
            proxy.write(f"progress {name} 1\n")
            proxy.write(f"progress {name} 2\n")
        finally:
            del server.JobRunner._thread_streams[threading.get_ident()]

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()

    assert got["a"] == ["progress a 1", "progress a 2"], got
    assert got["b"] == ["progress b 1", "progress b 2"], got

    # Thread tanpa stream (main) → jatuh ke fallback, bukan log job
    proxy.write("console line\n")
    assert "console line" in fallback.getvalue()


def test_install_stdout_proxy_no_crash():
    """Bug: _install_stdout_proxy refer _STDOUT_PROXY yang belum
    didefinisikan → NameError → runner thread mati → job tak pernah
    masuk DB (Studio kosong padahal POST sukses)."""
    out_before = sys.stdout
    try:
        server._install_stdout_proxy()
        assert sys.stdout is not out_before
        proxy = sys.stdout
        server._install_stdout_proxy()  # idempotent
        assert sys.stdout is proxy
    finally:
        sys.stdout = out_before
        server._STDOUT_PROXY = None


def test_main_thread_stdout_falls_back():
    from io import StringIO

    fallback = StringIO()
    proxy = server._ThreadRoutedStdout(fallback)
    proxy.write("hello\n")
    assert fallback.getvalue() == "hello\n"


def test_sse_replay_done_marker():
    """Bug glitch bar: hard refresh → since=0 → replay baris progress LAMA
    bikin bar menari download→transcribe→…→reframe. Server harus kirim event
    `replay-done` SETELAH buffer replay habis — baris berikutnya = LIVE,
    frontend baru boleh parseProgress."""
    import time
    from starlette.testclient import TestClient

    r = _runner()
    r._log("progress 1/5")
    r._log("progress 2/5")
    server.JOB_RUNNERS["testjob"] = r
    try:
        with TestClient(server.app) as client:
            with client.stream("GET", "/api/jobs/testjob/log?since=0") as resp:
                events = []
                lines = resp.iter_lines()
                for _ in range(8):
                    try:
                        chunk = lines.__next__()
                    except StopIteration:
                        break
                    if not chunk:
                        continue
                    if chunk.startswith("event:"):
                        events.append(chunk.split("event:", 1)[1].strip())
                        continue
                    if chunk.startswith("data:"):
                        events.append("DATA:" + chunk.split("data:", 1)[1].strip())
                # urutan: baris replay → marker → (baris baru kalau masuk)
                assert "replay-done" in events, f"marker tak ada: {events}"
                data_idx = [i for i, e in enumerate(events) if e.startswith("DATA:") and len(e) > 5]
                marker_idx = events.index("replay-done")
                assert max(data_idx) < marker_idx, f"marker harus setelah replay: {events}"
    finally:
        server.JOB_RUNNERS.pop("testjob", None)
    print("OK test_sse_replay_done_marker")