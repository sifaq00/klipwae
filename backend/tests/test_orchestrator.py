import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.base import Stage, StageResult, StageStatus
from orchestrator import topological_order, run_with_retry, run_pipeline


class _MockStage(Stage):
    """Stage dummy untuk test topological_order."""
    def __init__(self, name: str, depends_on: list[str] = None):
        self.name = name
        self.depends_on = depends_on or []

    def is_complete(self, job_id, db): return False
    def run(self, job_id, db, config):
        return StageResult(status=StageStatus.DONE)


class _FailingStage(Stage):
    def __init__(self, name: str, depends_on: list[str] = None):
        self.name = name
        self.depends_on = depends_on or []

    def is_complete(self, job_id, db): return False
    def run(self, job_id, db, config):
        raise RuntimeError("simulated failure")


class _RetryOnceStage(Stage):
    def __init__(self):
        self.name = "retry_me"
        self.depends_on = []
        self.call_count = 0

    def is_complete(self, job_id, db): return False
    def run(self, job_id, db, config):
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("first attempt fails")
        return StageResult(status=StageStatus.DONE)

    def max_retries(self): return 1


def test_topological_order_simple():
    a = _MockStage("a")
    b = _MockStage("b", ["a"])
    c = _MockStage("c", ["b"])
    registry = {"a": a, "b": b, "c": c}
    order = topological_order(registry)
    names = [s.name for s in order]
    assert names.index("a") < names.index("b")
    assert names.index("b") < names.index("c")
    assert len(order) == 3
    print("OK test_topological_order_simple")


def test_topological_order_independent():
    a = _MockStage("a")
    b = _MockStage("b")
    registry = {"a": a, "b": b}
    order = topological_order(registry)
    assert len(order) == 2
    print("OK test_topological_order_independent")


def test_topological_order_circular():
    a = _MockStage("a", ["c"])
    b = _MockStage("b", ["a"])
    c = _MockStage("c", ["b"])
    registry = {"a": a, "b": b, "c": c}
    try:
        topological_order(registry)
        assert False, "Should raise ValueError"
    except ValueError:
        pass
    print("OK test_topological_order_circular")


def test_topological_order_missing_dep():
    a = _MockStage("a", ["nonexistent"])
    registry = {"a": a}
    try:
        topological_order(registry)
        assert False, "Should raise ValueError"
    except ValueError:
        pass
    print("OK test_topological_order_missing_dep")


def test_run_with_retry_success_first():
    stage = _MockStage("ok")
    db = MagicMock()
    config = MagicMock()
    result = run_with_retry(stage, "job1", db, config)
    assert result.status == StageStatus.DONE
    assert db.log_stage_start.call_count == 1
    assert db.log_stage_end.call_count == 1
    print("OK test_run_with_retry_success_first")


def test_run_with_retry_transient_then_ok():
    stage = _RetryOnceStage()
    db = MagicMock()
    config = MagicMock()
    result = run_with_retry(stage, "job1", db, config)
    assert result.status == StageStatus.DONE
    assert stage.call_count == 2
    assert db.log_stage_start.call_count == 2
    assert db.log_stage_end.call_count == 2
    print("OK test_run_with_retry_transient_then_ok")


def test_run_with_retry_always_fails():
    stage = _FailingStage("fail")
    db = MagicMock()
    config = MagicMock()
    result = run_with_retry(stage, "job1", db, config)
    assert result.status == StageStatus.FAILED
    max_attempts = stage.max_retries() + 1
    assert db.log_stage_start.call_count == max_attempts
    print("OK test_run_with_retry_always_fails")


class _AnalyzeStage(Stage):
    def __init__(self, segments_found: int = -1):
        self.name = "analyze"
        self.depends_on = []
        self._segments_found = segments_found

    def is_complete(self, job_id, db): return False
    def run(self, job_id, db, config):
        if self._segments_found < 0:
            return StageResult(status=StageStatus.FAILED, error="boom")
        return StageResult(status=StageStatus.DONE, metadata={"segments_found": self._segments_found})


def _run_with_stage(stage, db):
    import orchestrator
    original = orchestrator.STAGE_REGISTRY
    orchestrator.STAGE_REGISTRY = {"analyze": stage}
    try:
        orchestrator.run_pipeline("job1", db, MagicMock())
    finally:
        orchestrator.STAGE_REGISTRY = original


def test_pipeline_notice_when_zero_segments():
    db = MagicMock()
    _run_with_stage(_AnalyzeStage(segments_found=0), db)
    db.set_notice.assert_called_once()
    assert "Tidak ditemukan segmen produk" in db.set_notice.call_args[0][1]
    print("OK test_pipeline_notice_when_zero_segments")


def test_pipeline_clears_notice_when_segments_found():
    db = MagicMock()
    _run_with_stage(_AnalyzeStage(segments_found=3), db)
    db.set_notice.assert_called_once_with("job1", None)
    print("OK test_pipeline_clears_notice_when_segments_found")


def test_pipeline_no_notice_on_analyze_failure():
    db = MagicMock()
    _run_with_stage(_AnalyzeStage(segments_found=-1), db)
    db.set_notice.assert_not_called()
    print("OK test_pipeline_no_notice_on_analyze_failure")


def test_run_pipeline_skip_complete():
    stage = _MockStage("a")
    stage.is_complete = lambda j, db: True
    registry = {"a": stage}
    import orchestrator
    original_registry = orchestrator.STAGE_REGISTRY
    orchestrator.STAGE_REGISTRY = registry
    try:
        db = MagicMock()
        config = MagicMock()
        run_pipeline("job1", db, config)
        stage.run = lambda j, d, c: (_ for _ in ()).throw(AssertionError("should not be called"))
        db.mark_job_status.assert_called_with("job1", "done")
        print("OK test_run_pipeline_skip_complete")
    finally:
        orchestrator.STAGE_REGISTRY = original_registry


if __name__ == "__main__":
    test_topological_order_simple()
    test_topological_order_independent()
    test_topological_order_circular()
    test_topological_order_missing_dep()
    test_run_with_retry_success_first()
    test_run_with_retry_transient_then_ok()
    test_run_with_retry_always_fails()
    test_pipeline_notice_when_zero_segments()
    test_pipeline_clears_notice_when_segments_found()
    test_pipeline_no_notice_on_analyze_failure()
    test_run_pipeline_skip_complete()
    print("\nAll orchestrator tests passed.")
