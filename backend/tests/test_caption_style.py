import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_validate_accepts_clean():
    from utils.caption_style import DEFAULT_STYLE, validate
    clean = validate(dict(DEFAULT_STYLE))
    assert clean is not None
    assert clean["size"] == 96


def test_validate_coerce_number_string():
    from utils.caption_style import validate
    clean = validate({"size": "120", "bold": "false"})
    assert clean is not None
    assert clean["size"] == 120
    assert clean["bold"] is False


def test_validate_rejects_garbage():
    from utils.caption_style import validate
    assert validate({"size": "abc"}) is None
    assert validate({"style": "injap"}) is None
    assert validate({"position": "left"}) is None
    assert validate({"font": "x" * 500}) is None


def test_enabled_toggle():
    from utils.caption_style import DEFAULT_STYLE, validate
    assert DEFAULT_STYLE["enabled"] is True
    assert validate({"enabled": "false"})["enabled"] is False
    assert validate({"enabled": False})["enabled"] is False


def test_hms_to_sec_never_crashes():
    from utils.time_helpers import hms_to_sec, sec_to_hms
    assert hms_to_sec("01:02:03") == 3723.0
    assert hms_to_sec("02:30") == 150.0
    assert hms_to_sec("45") == 45.0
    assert hms_to_sec("01:02:03.5") == 3723.5
    assert hms_to_sec("lorem ipsum") == 0.0
    assert hms_to_sec("") == 0.0
    assert hms_to_sec(30) == 30.0
    assert sec_to_hms(3723) == "01:02:03"