"""Snap-fixed-zoom: kamera SNAP instan ke anchor per-segmen saat ganti
speaker, no-pan selama bicara, zoom-only dari ukuran box."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.reframe.render_tracked import _zone_anchors, _segment_anchors


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
    assert anchors[0] is None  # zona 1 (track low-conf) tak punya anchor
    assert abs(anchors[1][0] - 950.0) < 1e-6


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
    test_zone_anchors_median_position()
    test_zone_anchors_ignores_low_conf_and_empty()
    test_segment_anchors_per_window()
    print("all ok")