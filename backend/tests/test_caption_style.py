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


def test_available_fonts_metadata():
    from utils.caption_style import AVAILABLE_FONTS
    assert isinstance(AVAILABLE_FONTS, list)
    assert len(AVAILABLE_FONTS) >= 5

    font_names = [f["name"] for f in AVAILABLE_FONTS]
    assert "Montserrat Black" in font_names
    assert "Segoe UI Black" in font_names
    assert "Impact" in font_names
    assert "Arial Black" in font_names
    assert "Trebuchet MS" in font_names

    for item in AVAILABLE_FONTS:
        assert "name" in item
        assert "label" in item
        assert "tag" in item
        assert "sample" in item


def test_font_name_map():
    from utils.caption_style import FONT_NAME_MAP
    assert FONT_NAME_MAP["Montserrat-Black"] == "Montserrat Black"
    assert FONT_NAME_MAP["Segoe-UI-Black"] == "Segoe UI Black"
    assert FONT_NAME_MAP["Arial-Black"] == "Arial Black"
    assert FONT_NAME_MAP["Trebuchet-MS"] == "Trebuchet MS"


def test_bundled_assets_fonts_exist():
    fonts_dir = Path(__file__).parent.parent / "assets" / "fonts"
    assert fonts_dir.exists()
    assert fonts_dir.is_dir()
    ttf_files = list(fonts_dir.glob("*.ttf")) + list(fonts_dir.glob("*.otf"))
    assert len(ttf_files) > 0


def test_api_fonts_endpoint():
    from fastapi.testclient import TestClient
    from server import app
    client = TestClient(app)
    res = client.get("/api/fonts")
    assert res.status_code == 200
    data = res.json()
    assert "fonts" in data
    assert "available_fonts" in data
    assert len(data["available_fonts"]) >= 5