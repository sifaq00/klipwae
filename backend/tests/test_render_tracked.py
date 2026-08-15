import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_soft_deadzone_displacement():
    from stages.reframe.render_tracked import _apply_soft_deadzone

    # Within deadzone (displacement 5px, deadzone 10px) -> excess should be 0.0
    assert _apply_soft_deadzone(5.0, 10.0) == 0.0
    assert _apply_soft_deadzone(-5.0, 10.0) == 0.0
    assert _apply_soft_deadzone(10.0, 10.0) == 0.0
    assert _apply_soft_deadzone(-10.0, 10.0) == 0.0

    # Outside deadzone (displacement 15px, deadzone 10px) -> excess should be +5.0
    assert _apply_soft_deadzone(15.0, 10.0) == 5.0
    # Outside deadzone (displacement -15px, deadzone 10px) -> excess should be -5.0
    assert _apply_soft_deadzone(-15.0, 10.0) == -5.0


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
    assert sig.parameters["smooth_alpha"].default == 0.08
    assert sig.parameters["target_alpha"].default == 0.25
    assert sig.parameters["deadband"].default == 0.012
    assert sig.parameters["hold_sec"].default == 0.8
    assert sig.parameters["zoom_ease"].default == 0.04
    assert sig.parameters["zoom_deadband"].default == 0.05
