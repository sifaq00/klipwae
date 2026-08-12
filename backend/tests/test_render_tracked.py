import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_default_params_preserved():
    from stages.reframe.render_tracked import render_tracked
    import inspect
    sig = inspect.signature(render_tracked)
    assert sig.parameters["head_bias"].default == 0.30
    assert sig.parameters["zoom_min"].default == 1.15
    assert sig.parameters["zoom_max"].default == 2.0
    assert sig.parameters["zoom_fit"].default == 0.6
    assert sig.parameters["smooth_alpha"].default == 0.12
