"""Harden-on-switch: saat side ganti, kamera SNAP cepat (alpha boost) lalu
kembali ke alpha halus — hilangkan kesan "kamera kejar-kejaran" di klip
multi-speaker (glide EMA 0.5-1s terlalu lambat utk konten TikTok)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.reframe.render_tracked import _switch_alpha, _follow_target


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


def test_follow_target_snaps_when_boosted():
    """Bottleneck ke-2: target EMA (0.25) TIDAK di-boost → kamera ngejar
    target yang melayang pelan (settle tetap ~1.3s walau camera alpha 0.5).
    Saat boost aktif, target di-SNAP ke box — settle jadi 0.2s."""
    # snap: langsung ke target
    assert _follow_target(100.0, 900.0, snap=True) == 900.0
    assert _follow_target(100.0, 100.0, snap=True) == 100.0
    # normal EMA
    t = _follow_target(100.0, 900.0, snap=False, alpha=0.25)
    assert abs(t - 300.0) < 1e-6, f"EMA 0.25 harus 300, got {t}"


def test_follow_target_ema_moves_toward_target():
    cur, tgt = 0.0, 100.0
    n = 0
    while abs(tgt - cur) > 1.0 and n < 1000:
        cur = _follow_target(cur, tgt, snap=False, alpha=0.25)
        n += 1
    assert n < 100, f"EMA tak konvergen: {n} iterasi"
    assert abs(cur - tgt) < 1.0


if __name__ == "__main__":
    test_no_switch_uses_base_alpha()
    test_switch_boosts_alpha()
    test_boost_ramps_down_to_base()
    test_no_path_single_shot_never_boosts()
    test_follow_target_snaps_when_boosted()
    test_follow_target_ema_moves_toward_target()
    print("all ok")