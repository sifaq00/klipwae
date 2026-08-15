"""Clip window: ffmpeg cut HARUS sama persis dengan yang disimpan di DB —
buffer TIDAK boleh di-apply dua kali (bug: _do hitung s-buf, _clip_one kurangi
buf lagi → cut di s-2buf, subtitle early)."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.clip import ClipStage


def test_clip_one_does_not_double_apply_buffer(tmp_path, monkeypatch):
    calls = {}

    def fake_run_ffmpeg(args, timeout=None, cwd=None):
        calls["args"] = args
        class R:
            returncode = 0
            stderr = b""
        return R()

    stage = ClipStage()
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"x")
    out = tmp_path / "out.mp4"

    with patch("stages.clip.run_ffmpeg", fake_run_ffmpeg), \
         patch("stages.clip.video_encode_args", lambda: ["-c:v", "libx264"]):
        # _do mengirim window ACTUAL (sudah termasuk buf=1.5): 10.0-30.0
        stage._clip_one(raw, 10.0, 30.0, out, buf=1.5)

    args = calls["args"]
    ss = args[args.index("-ss") + 1]
    to = args[args.index("-to") + 1]
    assert ss == "10.000", f"ffmpeg cut harus di 10.0 (bukan 8.5 = double buffer), got {ss}"
    assert to == "30.000", f"got {to}"
    print("OK test_clip_one_does_not_double_apply_buffer")