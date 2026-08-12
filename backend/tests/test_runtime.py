import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import runtime


def _wait_stop(timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if runtime.stop_requested():
            return True
        time.sleep(0.01)
    return False


def test_kill_only_targets_its_job():
    """Kill job A (thread ini) tidak boleh menghentikan job B (thread lain)."""
    runtime.reset()
    my_ident = threading.get_ident()
    b_saw_stop = []

    def job_b():
        runtime.reset()
        if _wait_stop(0.5):
            b_saw_stop.append(True)
        runtime.unregister(threading.get_ident())

    t = threading.Thread(target=job_b)
    t.start()
    time.sleep(0.15)  # biar reset() B keproses
    runtime.kill(my_ident)
    assert runtime.stop_requested(), "Job A harus berhenti"
    t.join(3)
    assert b_saw_stop == [], "Job B tidak boleh ikut berhenti"
    runtime.unregister(my_ident)


def test_kill_before_reset_applies_after_reset():
    """Kill sebelum thread job sempat reset → event pending, kena setelah reset."""
    ident = threading.get_ident()
    runtime.kill(ident)
    assert not runtime.stop_requested(), "Belum reset, belum kena"
    runtime.reset()
    assert runtime.stop_requested(), "Pending kill harus aktif setelah reset"
    runtime.unregister(ident)


def test_kill_all_stops_every_job():
    b_saw_stop = []

    def job_b():
        runtime.reset()
        if _wait_stop(2.0):
            b_saw_stop.append(True)
        runtime.unregister(threading.get_ident())

    t = threading.Thread(target=job_b)
    t.start()
    time.sleep(0.15)
    runtime.kill_all()
    t.join(3)
    assert b_saw_stop == [True], "kill_all harus menghentikan semua job"
    runtime.reset()
    runtime.unregister(threading.get_ident())
    # Jangan bocor ke test lain: kill_all bersifat permanen (shutdown server)
    runtime._shutdown.clear()


def test_proc_is_per_thread():
    """set_proc terkait JOB (contextvar), bukan thread — worker ThreadPool
    yang di-submit dari thread job ikut ter-ikat ke job yang sama."""
    class FakeProc:
        def __init__(self):
            self.calls = []

        def poll(self):
            return None

        def terminate(self):
            self.calls.append("terminate")

    runtime.reset()
    runtime.set_job("jobA")
    pa, pb = FakeProc(), FakeProc()
    runtime.set_proc(pa)
    runtime.set_proc(pb)
    assert runtime._by_job.get("jobA") == [pa, pb]

    # kill_job("jobA") terminate proc-nya; job lain bersih
    runtime.kill_job("jobA", threading.get_ident())
    assert pa.calls == ["terminate"] and pb.calls == ["terminate"]
    assert runtime._by_job["jobA"] == [pa, pb]  # list belum di-clear, proc sudah mati

    runtime.clear_proc(pa)
    runtime.clear_proc(pb)
    assert runtime._by_job["jobA"] == []
    runtime.clear_job("jobA")
    runtime.unregister(threading.get_ident())


if __name__ == "__main__":
    test_kill_only_targets_its_job()
    test_kill_before_reset_applies_after_reset()
    test_kill_all_stops_every_job()
    test_proc_is_per_thread()
    print("OK semua test_runtime")