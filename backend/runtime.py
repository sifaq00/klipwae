import subprocess
import threading

_lock = threading.Lock()
_stops: dict[int, threading.Event] = {}   # thread ident → stop event
_procs: dict[int, subprocess.Popen] = {}  # thread ident → subprocess aktif
_pending: set[int] = set()                # ident di-kill sebelum reset
_shutdown = threading.Event()             # kill-all: server shutdown


def _current() -> int:
    return threading.get_ident()


def reset():
    """Panggil di awal thread job — stop state FRESH per job.
    Kill yang sempat masuk sebelum reset (pending) langsung kena."""
    with _lock:
        ident = _current()
        ev = threading.Event()
        if ident in _pending:
            ev.set()
            _pending.discard(ident)
        _stops[ident] = ev
        _procs.pop(ident, None)


def set_proc(p: subprocess.Popen | None):
    with _lock:
        _procs[_current()] = p


def get_proc() -> subprocess.Popen | None:
    with _lock:
        return _procs.get(_current())


def stop_requested() -> bool:
    with _lock:
        if _shutdown.is_set():
            return True
        ev = _stops.get(_current())
        return ev is not None and ev.is_set()


def kill(thread_ident: int):
    """Stop JOB SPESIFIK (thread ident) + terminate subprocess-nya.
    Job lain tidak terpengaruh — sebelumnya 1 kill membunuh semua job."""
    with _lock:
        ev = _stops.get(thread_ident)
        if ev is not None:
            ev.set()
        else:
            _pending.add(thread_ident)
        proc = _procs.get(thread_ident)
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass


def kill_all():
    """Shutdown server: stop semua job + terminate semua subprocess."""
    with _lock:
        _shutdown.set()
        for ev in _stops.values():
            ev.set()
        procs = list(_procs.values())
    for p in procs:
        if p is not None:
            try:
                p.terminate()
            except Exception:
                pass


def unregister(thread_ident: int):
    """Bersihkan state job yang sudah selesai — cegah kebocoran memori."""
    with _lock:
        _stops.pop(thread_ident, None)
        _procs.pop(thread_ident, None)
        _pending.discard(thread_ident)