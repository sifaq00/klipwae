import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_zoom_deadband_filter():
    from stages.reframe.render_tracked import _update_target_zoom

    current_target = 1.20
    # Small fluctuation (2% change) within 5% deadband -> target stays 1.20
    assert _update_target_zoom(raw_zoom=1.22, active_target=current_target, deadband=0.05) == 1.20
    assert _update_target_zoom(raw_zoom=1.18, active_target=current_target, deadband=0.05) == 1.20

    # Significant change (10% change) beyond 5% deadband -> target updates
    assert _update_target_zoom(raw_zoom=1.35, active_target=current_target, deadband=0.05) == 1.35
    assert _update_target_zoom(raw_zoom=1.10, active_target=current_target, deadband=0.05) == 1.10


def test_default_params_preserved():
    from stages.reframe.render_tracked import render_tracked
    import inspect
    sig = inspect.signature(render_tracked)
    assert sig.parameters["head_bias"].default == 0.22
    assert sig.parameters["zoom_min"].default == 1.15
    assert sig.parameters["zoom_max"].default == 2.0
    assert sig.parameters["zoom_fit"].default == 0.6
    assert sig.parameters["zoom_ease"].default == 0.04
    assert sig.parameters["zoom_deadband"].default == 0.05
    assert sig.parameters["min_headroom_ratio"].default == 0.12


def test_clamp_headroom_preserves_top_margin():
    from stages.reframe.render_tracked import _clamp_headroom

    # Case 1: Headroom violation - box_top is too close to top of crop frame
    # cy = 500, crop_h = 1000 -> crop_top = 0.
    # min_headroom_ratio = 0.12 -> min_headroom = 120.
    # box_top = 50 (margin is only 50px < 120px)
    # Adjusted cy should be 50 - 120 + 500 = 430
    adjusted_cy = _clamp_headroom(cy=500.0, box_top=50.0, crop_h=1000.0, min_headroom_ratio=0.12)
    assert adjusted_cy == 430.0
    # Verify effective headroom with adjusted_cy
    new_crop_top = adjusted_cy - 1000.0 / 2.0
    assert 50.0 - new_crop_top == 120.0

    # Case 2: Adequate headroom - box_top already has >= 12% margin
    # cy = 500, crop_h = 1000 -> crop_top = 0.
    # box_top = 200 (margin is 200px >= 120px)
    # cy should remain 500.0
    unchanged_cy = _clamp_headroom(cy=500.0, box_top=200.0, crop_h=1000.0, min_headroom_ratio=0.12)
    assert unchanged_cy == 500.0

    # Case 3: Exact boundary - box_top exactly at threshold
    # box_top = 120
    boundary_cy = _clamp_headroom(cy=500.0, box_top=120.0, crop_h=1000.0, min_headroom_ratio=0.12)
    assert boundary_cy == 500.0

    # Case 4: Default min_headroom_ratio parameter is 0.12
    res = _clamp_headroom(cy=600.0, box_top=100.0, crop_h=1000.0)
    # crop_top = 100, min_headroom = 120, box_top - crop_top = 0 < 120 -> adjusted cy = 100 - 120 + 500 = 480
    assert res == 480.0

