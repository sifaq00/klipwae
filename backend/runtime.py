import subprocess
import threading

_proc: subprocess.Popen | None = None
_lock = threading.Lock()
_stop = threading.Event()


def set_proc(p: subprocess.Popen | None):
    global _proc
    with _lock:
        _proc = p


def get_proc() -> subprocess.Popen | None:
    with _lock:
        return _proc


def kill():
    p = get_proc()
    if p:
        try:
            p.terminate()
        except Exception:
            pass
    _stop.set()


def stop_requested() -> bool:
    return _stop.is_set()


def reset():
    global _stop
    _stop = threading.Event()
    set_proc(None)
