import subprocess
from pathlib import Path

import pytest

from stages.reframe import _get_video_info
from stages.reframe.camera_path import build_camera_path
from stages.reframe.layout_detector import detect_layout
from stages.reframe.render import render_center_crop, render_split_screen
from stages.reframe.speaker_activity import _calc_mar

TEST_VIDEO = Path(__file__).parent.parent / "data/raw/DkPEGUUnJGE.mp4"

requires_test_video = pytest.mark.skipif(
    not TEST_VIDEO.exists(),
    reason="fixture video data/raw/DkPEGUUnJGE.mp4 belum ada",
)


class TestGetVideoInfo:
    @requires_test_video
    def test_normal_video(self):
        fps, dur = _get_video_info(TEST_VIDEO)
        assert 15 < fps < 60, f"fps={fps}"
        assert dur > 400

    def test_missing_file(self):
        fps, dur = _get_video_info(Path("nonexistent.mp4"))
        assert fps == 30.0 and dur == 0.0


class TestDetectLayout:
    @requires_test_video
    def test_single_person(self):
        assert detect_layout(TEST_VIDEO) == "single_shot"

    def test_missing_file(self):
        assert detect_layout(Path("nonexistent.mp4")) == "single_shot"


class TestCameraPath:
    def test_empty(self):
        assert build_camera_path([]) == []

    def test_single_entry(self):
        assert build_camera_path([(0, 10, "left")], 1.2) == [(0, 10, "left")]

    def test_all_previous(self):
        raw = [(0, 1, "previous"), (1, 2, "previous")]
        assert build_camera_path(raw, 0.5) == [(0, 2, "left")]

    def test_brief_interruption_merged(self):
        raw = [(0, 1, "left"), (1, 1.3, "right"), (1.3, 2, "left")]
        assert build_camera_path(raw, 0.5) == [(0, 2, "left")]

    def test_long_switch_happens(self):
        raw = [(0, 1, "left"), (1, 3, "right")]
        assert build_camera_path(raw, 1.2) == [(0, 1, "left"), (1, 3, "right")]

    def test_too_short_switch_no(self):
        raw = [(0, 1, "left"), (1, 2, "right")]
        assert build_camera_path(raw, 1.2) == [(0, 2, "left")]

    def test_multiple_switches_with_tail_merged(self):
        raw = [(0, 1, "left"), (1, 2.5, "right"), (2.5, 4, "left"), (4, 5, "right")]
        path = build_camera_path(raw, 1.2)
        assert path == [(0, 1, "left"), (1, 2.5, "right"), (2.5, 5, "left")]

    def test_min_hold_zero(self):
        raw = [(0, 1, "left"), (1, 2, "right"), (2, 3, "left")]
        assert build_camera_path(raw, 0) == [(0, 1, "left"), (1, 2, "right"), (2, 3, "left")]

    def test_rapid_speaker_turns_smoothed(self):
        from stages.reframe.camera_path import smooth_rapid_speaker_turns

        # 4 rapid turns under 2.0s within 6.0s (switches at 1.2, 2.4, 3.6, 4.8)
        rapid_path = [
            (0.0, 1.2, "left"),
            (1.2, 2.4, "right"),
            (2.4, 3.6, "left"),
            (3.6, 4.8, "right"),
            (4.8, 10.0, "left"),
        ]
        smoothed = smooth_rapid_speaker_turns(rapid_path)
        # All merged into continuous left hold
        assert smoothed == [(0.0, 10.0, "left")]

    def test_rapid_speaker_turns_then_stable_other_speaker(self):
        from stages.reframe.camera_path import smooth_rapid_speaker_turns

        # Rapid banter between left and right (1.0s each), then right speaks for 5s (5.0 to 10.0)
        rapid_path = [
            (0.0, 1.0, "left"),
            (1.0, 2.0, "right"),
            (2.0, 3.0, "left"),
            (3.0, 4.0, "right"),
            (4.0, 5.0, "left"),
            (5.0, 10.0, "right"),
        ]
        smoothed = smooth_rapid_speaker_turns(rapid_path)
        # Banter held on initial speaker (left) until stable switch to right at 5.0
        assert smoothed == [(0.0, 5.0, "left"), (5.0, 10.0, "right")]

    def test_slow_turns_preserved(self):
        from stages.reframe.camera_path import smooth_rapid_speaker_turns

        # Turns are 3.0s each (>= 2.0s) -> should NOT be smoothed
        slow_path = [
            (0.0, 3.0, "left"),
            (3.0, 6.0, "right"),
            (6.0, 9.0, "left"),
            (9.0, 12.0, "right"),
        ]
        smoothed = smooth_rapid_speaker_turns(slow_path)
        assert smoothed == slow_path


class TestCalcMAR:
    def test_open_vs_closed(self):
        LM = lambda x, y: type("LM", (), {"x": float(x), "y": float(y)})()
        base = [LM(0, 0) for _ in range(468)]

        open_lms = list(base)
        open_lms[13] = LM(0.5, 0.3)
        open_lms[14] = LM(0.5, 0.5)
        open_lms[61] = LM(0.3, 0.4)
        open_lms[291] = LM(0.7, 0.4)

        closed_lms = list(base)
        closed_lms[13] = LM(0.5, 0.395)
        closed_lms[14] = LM(0.5, 0.405)
        closed_lms[61] = LM(0.3, 0.4)
        closed_lms[291] = LM(0.7, 0.4)

        assert _calc_mar(open_lms, 100, 100) > _calc_mar(closed_lms, 100, 100)

    def test_zero_mouth_width(self):
        LM = lambda x, y: type("LM", (), {"x": float(x), "y": float(y)})()
        base = [LM(0, 0) for _ in range(468)]
        base[13] = LM(0.5, 0.3)
        base[14] = LM(0.5, 0.5)
        base[61] = LM(0, 0)
        base[291] = LM(0, 0)
        assert _calc_mar(base, 100, 100) == 0.0


@requires_test_video
class TestRenderSmoke:
    def _make_clip(self, tmp_path) -> Path:
        clip = tmp_path / "smoke.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "10", "-i", str(TEST_VIDEO), "-t", "3", "-c", "copy", str(clip)],
            check=True, capture_output=True,
        )
        return clip

    def test_center_crop(self, tmp_path):
        clip = self._make_clip(tmp_path)
        out = tmp_path / "out.mp4"
        render_center_crop(clip, out)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_split_screen_empty_path_fallsback(self, tmp_path):
        clip = self._make_clip(tmp_path)
        out = tmp_path / "out.mp4"
        render_split_screen(clip, [], {}, out)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_split_screen_single_segment(self, tmp_path):
        clip = self._make_clip(tmp_path)
        out = tmp_path / "out.mp4"
        region = type("R", (), {"x": 0, "y": 0, "w": 640, "h": 720})()
        render_split_screen(clip, [(0, 3, "left")], {"left": region}, out)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_split_screen_multi_segment(self, tmp_path):
        clip = self._make_clip(tmp_path)
        out = tmp_path / "out.mp4"
        region = type("R", (), {"x": 0, "y": 0, "w": 640, "h": 720})()
        render_split_screen(
            clip,
            [(0, 1, "left"), (1, 2, "right"), (2, 3, "left")],
            {"left": region, "right": region},
            out,
        )
        assert out.exists()
        assert out.stat().st_size > 1000
