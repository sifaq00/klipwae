"""Harden-on-switch: saat side ganti, kamera SNAP cepat (alpha boost) lalu
kembali ke alpha halus — hilangkan kesan "kamera kejar-kejaran" di klip
multi-speaker (glide EMA 0.5-1s terlalu lambat utk konten TikTok)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.reframe.render_tracked import _switch_alpha, _follow_target, _zone_anchors, _segment_anchors


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


def test_zone_anchors_median_position():
    """Anchor zona = median posisi orang (stabil walau ada outlier gerak)."""
    frames = [
        {"boxes": [
            (1, 100, 100, 200, 300, 0.9),   # track 1 kiri
            (2, 900, 100, 1000, 300, 0.9),  # track 2 kanan
        ]},
        {"boxes": [
            (1, 110, 100, 210, 300, 0.9),
            (2, 910, 100, 1010, 300, 0.9),
        ]},
        {"boxes": [
            (1, 120, 100, 220, 300, 0.9),
            (2, 920, 100, 1020, 300, 0.9),
        ]},
    ]
    zone_map = {1: 0, 2: 1}
    anchors = _zone_anchors(frames, zone_map, head_bias=0.5)
    # zona 0: x center 150/160/170 median 160, y = 100+(100)*0.5 = 200
    assert abs(anchors[0][0] - 160.0) < 1e-6, anchors[0]
    assert abs(anchors[0][1] - 200.0) < 1e-6, anchors[0]
    # zona 1: x centers 950/960/970 median 960
    assert abs(anchors[1][0] - 960.0) < 1e-6, anchors[1]


def test_zone_anchors_ignores_low_conf_and_empty():
    frames = [
        {"boxes": [(1, 100, 100, 200, 300, 0.1), (2, 900, 100, 1000, 300, 0.9)]},
    ]
    zone_map = {1: 0, 2: 1}
    anchors = _zone_anchors(frames, zone_map, conf_min=0.35)
    assert 0 in anchors  # fallback (0,0) utk zona kosong
    assert anchors[0] == (0.0, 0.0)
    assert abs(anchors[1][0] - 950.0) < 1e-6


def test_follow_target_ema_moves_toward_target():
    cur, tgt = 0.0, 100.0
    n = 0
    while abs(tgt - cur) > 1.0 and n < 1000:
        cur = _follow_target(cur, tgt, snap=False, alpha=0.25)
        n += 1
    assert n < 100, f"EMA tak konvergen: {n} iterasi"
    assert abs(cur - tgt) < 1.0


def test_segment_anchors_per_window():
    """Anchor per SEGMEN: orang bergeser antar segmen → anchor ikut segmen
    (bukan median global yang bikin off-center). Box terbesar per frame."""
    # 30 frame @30fps: segmen 0 = 0-1s, segmen 1 = 1-2s
    frames = []
    for i in range(60):
        if i < 30:  # segmen 0: orang di x~400
            boxes = [(1, 300, 100, 500, 300, 0.9), (2, 100, 100, 200, 300, 0.5)]
        else:       # segmen 1: orang bergeser ke x~800
            boxes = [(1, 700, 100, 900, 300, 0.9)]
        frames.append({"boxes": boxes})
    zone_map = {1: 0, 2: 0}
    camera_path = [(0.0, 1.0, "left"), (1.0, 2.0, "left")]
    anchors = _segment_anchors(frames, zone_map, camera_path, fps=30.0, head_bias=0.5)
    # segmen 0: box terbesar tiap frame = track 1 (area 40000 > 10000) x~400
    assert abs(anchors[(0, 0)][0] - 400.0) < 2.0, anchors
    # segmen 1: x~800
    assert abs(anchors[(0, 1)][0] - 800.0) < 2.0, anchors
    # y: head_bias 0.5 → 100 + (300-100)*0.5 = 200
    assert abs(anchors[(0, 0)][1] - 200.0) < 1e-6


if __name__ == "__main__":
    test_no_switch_uses_base_alpha()
    test_switch_boosts_alpha()
    test_boost_ramps_down_to_base()
    test_no_path_single_shot_never_boosts()
    test_follow_target_snaps_when_boosted()
    test_follow_target_ema_moves_toward_target()
    test_zone_anchors_median_position()
    test_zone_anchors_ignores_low_conf_and_empty()
    test_segment_anchors_per_window()
    print("all ok")