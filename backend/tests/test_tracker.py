import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


class FakeModel:
    def __init__(self):
        self.calls = 0

    def track(self, frames, *args, **kwargs):
        self.calls += 1
        return [SimpleNamespace(boxes=None)] * len(frames)


def _tiny_video(tmp_path: Path) -> Path:
    video = tmp_path / "tiny.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=2",
         "-r", "10", "-pix_fmt", "yuv420p", str(video)],
        check=True, capture_output=True,
    )
    return video


def test_extract_boxes():
    from stages.reframe.tracker import _extract_boxes
    r = MagicMock()
    r.boxes.id.int.return_value.tolist.return_value = [7, 8]
    r.boxes.xyxy.tolist.return_value = [[1, 2, 3, 4], [5, 6, 7, 8]]
    r.boxes.conf.tolist.return_value = [0.9, 0.8]
    out = _extract_boxes(r)
    assert out == [(7, 1, 2, 3, 4, 0.9), (8, 5, 6, 7, 8, 0.8)]

    r2 = SimpleNamespace(boxes=None)
    assert _extract_boxes(r2) == []


def test_interpolate_boxes():
    from stages.reframe.tracker import _interpolate_boxes

    # Sample 0: box at (10, 20, 100, 200) for track 1
    # Sample 1: box at (20, 40, 110, 210) for track 1
    sample_a = [(1, 10.0, 20.0, 100.0, 200.0, 0.9)]
    sample_b = [(1, 20.0, 40.0, 110.0, 210.0, 0.9)]

    # Halfway (t = 0.5)
    interp = _interpolate_boxes(sample_a, sample_b, 0.5)
    assert len(interp) == 1
    bid, x1, y1, x2, y2, conf = interp[0]
    assert bid == 1
    assert x1 == 15.0
    assert y1 == 30.0
    assert x2 == 105.0
    assert y2 == 205.0

    # Boundary t=0.0 -> exact sample_a
    assert _interpolate_boxes(sample_a, sample_b, 0.0) == sample_a
    # Boundary t=1.0 -> exact sample_b
    assert _interpolate_boxes(sample_a, sample_b, 1.0) == sample_b

    # Track missing in sample_b -> preserved from sample_a
    sample_b_empty = []
    assert _interpolate_boxes(sample_a, sample_b_empty, 0.5) == sample_a


def test_track_persons_subsample_and_cache(tmp_path):
    """Step=3 → semua frame tercatat (carry-forward), inference cuma ~1/3
    frame. Cache JSON: run kedua tidak nge-track ulang."""
    from stages.reframe import tracker

    video = _tiny_video(tmp_path)

    fake = FakeModel()
    tracker.get_tracker = lambda: fake

    try:
        import cv2
        cap = cv2.VideoCapture(str(video))
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        frames = tracker.track_persons(video, device="cpu", step=3, use_cache=False)
        assert len(frames) == n_frames, f"frames={len(frames)} != {n_frames}"
        assert fake.calls == 1, "batch track = SATU call inference"
        assert all(f["boxes"] == [] for f in frames)

        cache_path = tracker._cache_path(video, 3, 320)
        assert not cache_path.exists(), "use_cache=False tidak boleh nulis cache"

        run2 = tracker.track_persons(video, device="cpu", step=3, imgsz=320, use_cache=True)
        assert cache_path.exists(), "cache harus ditulis"
        assert fake.calls == 2, "run pertama use_cache=True masih re-track (cache belum ada)"
        calls_after_two = fake.calls

        run3 = tracker.track_persons(video, device="cpu", step=3, imgsz=320, use_cache=True)
        assert fake.calls == calls_after_two, "run ketiga harus pakai cache, bukan re-track"
        assert run3 == frames

        # Cache rusak/basi → re-track
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["step"] = 99
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        tracker.track_persons(video, device="cpu", step=3, imgsz=320, use_cache=True)
        assert fake.calls > 0, "cache basi harus memicu re-track"
    finally:
        # bersihkan global biar test lain tidak kena
        tracker._cache_path(video, 3, 320).unlink(missing_ok=True)


def test_track_persons_gagal_return_none(tmp_path):
    """GPU/утилиtralytics error → None (stage fallback), bukan exception."""
    from stages.reframe import tracker

    video = _tiny_video(tmp_path)
    video.unlink()  # file hilang → VideoCapture gagal open

    out = tracker.track_persons(video, device="cpu", step=3, use_cache=False)
    assert out is None