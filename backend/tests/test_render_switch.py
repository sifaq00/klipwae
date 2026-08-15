"""Harden-on-switch: saat side ganti, kamera SNAP cepat (alpha boost) lalu
kembali ke alpha halus — hilangkan kesan "kamera kejar-kejaran" di klip
multi-speaker (glide EMA 0.5-1s terlalu lambat utk konten TikTok)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.reframe.render_tracked import _switch_alpha


def test_no_switch_uses_base_alpha():
    alpha, boost = _switch_alpha(prev_side="left", cur_side="left", boost_left=0,
                                 base=0.08, boost=0.5, boost_frames=6)
    assert alpha == 0.08
    assert boost == 0


def test_switch_boosts_alpha():
    alpha, boost = _switch_alpha(prev_side="left", cur_side="right", boost_left=0,
                                 base=0.08, boost=0.5, boost_frames=6)
    assert alpha == 0.5, f"switch harus boost, got {alpha}"
    assert boost == 5, f"boost counter harus 6-1, got {boost}"


def test_boost_ramps_down_to_base():
    # frame kedua setelah switch: masih boost
    alpha, boost = _switch_alpha(prev_side="right", cur_side="right", boost_left=5,
                                 base=0.08, boost=0.5, boost_frames=6)
    assert alpha == 0.5 and boost == 4, f"got alpha={alpha}, boost={boost}"
    # habis boost window → base
    alpha, boost = _switch_alpha(prev_side="right", cur_side="right", boost_left=1,
                                 base=0.08, boost=0.5, boost_frames=6)
    assert alpha == 0.08 and boost == 0, f"got alpha={alpha}, boost={boost}"


def test_no_path_single_shot_never_boosts():
    alpha, boost = _switch_alpha(prev_side=None, cur_side=None, boost_left=0,
                                 base=0.08, boost=0.5, boost_frames=6)
    assert alpha == 0.08 and boost == 0


if __name__ == "__main__":
    test_no_switch_uses_base_alpha()
    test_switch_boosts_alpha()
    test_boost_ramps_down_to_base()
    test_no_path_single_shot_never_boosts()
    print("all ok")