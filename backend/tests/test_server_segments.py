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
