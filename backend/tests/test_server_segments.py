import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _resolve_clip_path


def test_resolve_relative():
    p = _resolve_clip_path("data/clips_raw/x.mp4")
    assert p.is_absolute()
    assert p == Path(__file__).parent.parent / "data/clips_raw/x.mp4"


def test_resolve_absolute():
    p = _resolve_clip_path("D:/tmp/x.mp4")
    assert p == Path("D:/tmp/x.mp4")


def test_segment_files_includes_thumb():
    """Bug: reject segment tidak menghapus thumbnail .jpg (yatim di clips_final)."""
    from server import _segment_files
    files = _segment_files({"clip_path": "data/clips_raw/job_001_pasta.mp4"})
    names = {p.name for p in files}
    assert "job_001_pasta.mp4" in names            # raw clip
    assert "job_001_pasta_reframed.mp4" in names   # hasil reframe
    assert "job_001_pasta.ass" in names            # subtitle
    assert "job_001_pasta.jpg" in names            # thumbnail — dulu tidak ada
