import os
import time
from pathlib import Path

from stages.base import Stage, StageResult, StageStatus
from stages.registry import STAGE_REGISTRY
from db.jobs import JobDB
import runtime


STAGE_TO_JOB_STATUS = {
    "ingest": "downloading",
    "transcribe": "transcribing",
    "analyze": "analyzing",
    "clip": "clipping",
    "reframe": "reframing",
    "caption": "captioning",
}


def topological_order(registry: dict[str, Stage]) -> list[Stage]:
    in_degree = {name: 0 for name in registry}
    adj = {name: [] for name in registry}
    for name, stage in registry.items():
        for dep in stage.depends_on:
            if dep not in registry:
                raise ValueError(f"Stage '{name}' depends on '{dep}' which is not registered")
            adj[dep].append(name)
            in_degree[name] += 1

    queue = [name for name, deg in in_degree.items() if deg == 0]
    resolved = []
    while queue:
        name = queue.pop(0)
        resolved.append(registry[name])
        for next_name in adj[name]:
            in_degree[next_name] -= 1
            if in_degree[next_name] == 0:
                queue.append(next_name)

    if len(resolved) != len(registry):
        raise ValueError(f"Circular dependency detected in stages: {list(registry.keys())}")
    return resolved


def run_with_retry(stage: Stage, job_id: str, db: JobDB, config: "Settings") -> StageResult:
    max_attempts = stage.max_retries() + 1
    for attempt in range(1, max_attempts + 1):
        if runtime.stop_requested():
            return StageResult(status=StageStatus.FAILED, error="Killed")
        db.log_stage_start(job_id, stage.name, attempt)
        try:
            result = stage.run(job_id, db, config)
        except Exception as e:
            result = StageResult(status=StageStatus.FAILED, error=str(e))
        db.log_stage_end(job_id, stage.name, result)
        if result.status != StageStatus.FAILED:
            return result
        if attempt < max_attempts:
            time.sleep(min(2 ** attempt, 60))
    return result


def run_pipeline(job_id: str, db: JobDB, config: "Settings", log_func: callable = print):
    # Pastikan semua stage ter-register (auto-import stages/__init__ dihapus
    # supaya server API mode ringan — worker yang jalankan pipeline harus
    # import eksplisit di sini). Import idempoten; dekorator @register
    # mengisi STAGE_REGISTRY.
    from stages import ingest, transcribe, analyze, clip, caption, reframe  # noqa: F401
    runtime.reset()
    db.mark_job_status(job_id, "running")
    for stage in topological_order(STAGE_REGISTRY):
        if runtime.stop_requested():
            db.mark_job_status(job_id, "killed")
            log_func("  [pipeline] killed")
            return
        if stage.is_complete(job_id, db):
            log_func(f"  [{stage.name}] already done, skipping")
            continue
        status_text = STAGE_TO_JOB_STATUS.get(stage.name, stage.name)
        db.mark_job_status(job_id, status_text)
        log_func(f"  [{status_text}] starting...")
        result = run_with_retry(stage, job_id, db, config)
        if stage.name == "analyze":
            # Info non-fatal: episode tanpa segmen produk — tampilkan di UI,
            # bukan dianggap error.
            found = (result.metadata or {}).get("segments_found", -1)
            if result.status != StageStatus.FAILED and found == 0 and not runtime.stop_requested():
                db.set_notice(job_id, "Tidak ditemukan segmen produk di episode ini — coba episode yang membahas produk (review, haul, demo).")
            elif found > 0:
                db.set_notice(job_id, None)  # run ulang ketemu segmen → bersihkan
        if result.status == StageStatus.FAILED:
            if result.error == "Killed":
                db.mark_job_status(job_id, "killed")
                log_func("  [pipeline] killed")
            else:
                db.mark_job_status(job_id, "failed", failed_stage=stage.name, error=result.error)
                log_func(f"  [{status_text}] FAILED: {result.error[:200]}")
            return
        meta = result.metadata or {}
        meta_str = " | ".join(f"{k}={v}" for k, v in meta.items()) if meta else ""
        log_func(f"  [{status_text}] done {meta_str}")
    _cleanup_raw(job_id, log_func)
    db.mark_job_status(job_id, "done")


def _cleanup_raw(job_id: str, log_func: callable = print):
    """Hapus audio hasil ekstraksi (.wav) — bisa dibuat ulang dari video.
    RAW VIDEO DI-SIMPAN sampai retention (config.storage_retention_days):
    reprocess/"proses ulang" jadi instan, gak download ulang 400MB.
    Cleanup umur-file jalan di startup server (server.py lifespan)."""
    p = Path(f"data/raw/{job_id}.wav")
    try:
        if p.exists():
            p.unlink()
            log_func(f"  [pipeline] cleaned {p}")
    except OSError:
        pass
