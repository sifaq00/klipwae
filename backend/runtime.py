import contextvars
import subprocess
import threading

_lock = threading.Lock()
_stops: dict[int, threading.Event] = {}   # thread ident → stop event
_pending: set[int] = set()                # ident di-kill sebelum reset
_by_job: dict[str, list[subprocess.Popen]] = {}  # job_id → subprocess aktif
_anon_procs: list[subprocess.Popen] = []  # proc tanpa konteks job (test/standalone)
_shutdown = threading.Event()             # kill-all: server shutdown

# Job ID aktif di thread ini — contextvars otomatis diteruskan ke worker
# ThreadPoolExecutor, jadi ffmpeg dari clip/caption worker ikut ter-ikat
# ke job-nya dan bisa di-terminate saat job di-kill.
_job_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("current_job", default="")


def _current() -> int:
    return threading.get_ident()


def set_job(job_id: str):
    _job_ctx.set(job_id)


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


def set_proc(p: subprocess.Popen | None):
    """Daftarkan subprocess ter-ikat ke job aktif (contextvar)."""
    if p is None:
        return
    with _lock:
        jid = _job_ctx.get()
        if jid:
            _by_job.setdefault(jid, []).append(p)
        else:
            _anon_procs.append(p)


def clear_proc(p: subprocess.Popen | None):
    if p is None:
        return
    with _lock:
        for lst in _by_job.values():
            if p in lst:
                lst.remove(p)
                return
        if p in _anon_procs:
            _anon_procs.remove(p)


def stop_requested() -> bool:
    with _lock:
        if _shutdown.is_set():
            return True
        ev = _stops.get(_current())
        return ev is not None and ev.is_set()


def _terminate(procs: list[subprocess.Popen]):
    for p in procs:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass


def kill_job(job_id: str, thread_ident: int):
    """Stop job spesifik (thread ident) + terminate SEMUA subprocess-nya
    (termasuk ffmpeg worker dari clip/caption). Job lain tidak tersentuh."""
    with _lock:
        ev = _stops.get(thread_ident)
        if ev is not None:
            ev.set()
        else:
            _pending.add(thread_ident)
        procs = list(_by_job.get(job_id, []))
    _terminate(procs)


def kill(thread_ident: int):
    """Compat: stop per thread tanpa terminate proc (caller lama)."""
    with _lock:
        ev = _stops.get(thread_ident)
        if ev is not None:
            ev.set()
        else:
            _pending.add(thread_ident)


def kill_all():
    """Shutdown server: stop semua job + terminate semua subprocess."""
    with _lock:
        _shutdown.set()
        for ev in _stops.values():
            ev.set()
        procs = [p for lst in _by_job.values() for p in lst] + list(_anon_procs)
    _terminate(procs)


def unregister(thread_ident: int):
    with _lock:
        _stops.pop(thread_ident, None)
        _pending.discard(thread_ident)


def clear_job(job_id: str):
    with _lock:
        _by_job.pop(job_id, None)