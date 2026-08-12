import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.caption import (
    _sanitize_ass_text,
    _sec_to_ass_time,
    _group_sentences,
    _ass_header,
    _hex_to_bgr,
    generate_ass,
    CaptionStage,
)


def _cfg(**over):
    cfg = {
        "font": "Arial", "size": 80, "bold": True, "italic": False,
        "uppercase": False, "pop": False, "spacing": 0,
        "text_color": "#FFFFFF", "highlight_color": "#FFFF00",
        "outline": 4, "outline_color": "#000000", "border_style": "outline",
        "shadow": 2, "shadow_color": "#000000",
        "position": "bottom", "margin_v": 80, "style": "highlight",
    }
    cfg.update(over)
    return cfg


def test_sanitize_ass_text():
    assert _sanitize_ass_text("hello") == "hello"
    assert _sanitize_ass_text("a{b}c}d") == "a\\{b\\}c\\}d"
    assert _sanitize_ass_text("a\\b") == "a\\\\b"
    print("OK test_sanitize_ass_text")


def test_sec_to_ass_time():
    assert _sec_to_ass_time(0) == "0:00:00.00"
    assert _sec_to_ass_time(1.5) == "0:00:01.50"
    assert _sec_to_ass_time(3661.75) == "1:01:01.75"
    assert _sec_to_ass_time(-5) == "0:00:00.00"
    print("OK test_sec_to_ass_time")


def test_group_sentences_empty():
    assert _group_sentences([]) == []
    print("OK test_group_sentences_empty")


def test_group_sentences_max_words():
    words = [{"text": f"w{i}", "start": float(i), "end": float(i + 0.5)} for i in range(12)]
    groups = _group_sentences(words, max_words=5, gap_sec=1.5)
    assert len(groups) == 3
    assert len(groups[0]) == 5
    assert len(groups[1]) == 5
    assert len(groups[2]) == 2
    print("OK test_group_sentences_max_words")


def test_group_sentences_gap():
    words = [
        {"text": "a", "start": 0.0, "end": 0.3},
        {"text": "b", "start": 0.4, "end": 0.7},
        {"text": "c", "start": 3.0, "end": 3.5},
    ]
    groups = _group_sentences(words, max_words=10, gap_sec=1.5)
    assert len(groups) == 2
    assert len(groups[0]) == 2
    assert len(groups[1]) == 1
    print("OK test_group_sentences_gap")


def test_hex_to_bgr():
    assert _hex_to_bgr("#FFFFFF") == "FFFFFF"
    assert _hex_to_bgr("#FF0000") == "0000FF"
    assert _hex_to_bgr("#00FF00") == "00FF00"
    assert _hex_to_bgr("#0000FF") == "FF0000"
    assert _hex_to_bgr("invalid") == "FFFFFF"
    print("OK test_hex_to_bgr")


def test_ass_header_custom_style():
    style = _cfg(font="Poppins", size=110, bold=False, italic=True, spacing=2,
                 text_color="#FF0000", highlight_color="#00FF00",
                 outline=8, outline_color="#0000FF", border_style="box",
                 shadow=4, position="top", margin_v=60)
    h = _ass_header(style)
    assert "Poppins" in h
    assert "110" in h
    assert "0,-1,0,0" in h  # bold=0, italic=-1
    assert "3,8,4,8" in h  # BorderStyle=3 (kotak), outline, shadow, alignment=8 (atas)
    assert "&H000000FF" in h  # text merah → BGR 0000FF
    assert "&H0000FF00" in h  # highlight hijau → BGR 00FF00
    print("OK test_ass_header_custom_style")


def test_generate_ass_static():
    words = [{"text": "halo", "start": 0.0, "end": 1.0}]
    ass = generate_ass(words, style="static", style_cfg=_cfg())
    assert "[Script Info]" in ass
    assert "Dialogue:" in ass
    assert "halo" in ass
    assert "\\c&H" not in ass
    print("OK test_generate_ass_static")


def test_generate_ass_highlight_karaoke_lines():
    words = [{"text": "halo", "start": 0.0, "end": 0.6}, {"text": "dunia", "start": 0.6, "end": 1.2}]
    ass = generate_ass(words, style="highlight", style_cfg=_cfg(pop=True))
    # Satu baris dialogue per kata aktif
    assert ass.count("Dialogue:") == 2
    # Kata aktif dibungkus \c highlight + reset warna teks
    assert "{\\c&H00FFFF" in ass
    assert "halo{\\c&HFFFFFF}" in ass or "dunia{\\c&HFFFFFF}" in ass
    # Pop = static scale pada kata aktif
    assert "\\fscx112\\fscy112" in ass
    print("OK test_generate_ass_highlight_karaoke_lines")


def test_generate_ass_line_spacing():
    words = [{"text": f"kata{i}", "start": i * 0.4, "end": i * 0.4 + 0.35} for i in range(14)]
    ass = generate_ass(words, style="static", style_cfg=_cfg(line_spacing=50))
    assert "\\fs50" in ass
    assert "\\N" in ass  # bungkus jadi >1 baris
    ass0 = generate_ass(words, style="static", style_cfg=_cfg(line_spacing=0))
    assert "\\fs" not in ass0
    print("OK test_generate_ass_line_spacing")


def test_generate_ass_uppercase():
    words = [{"text": "halo", "start": 0.0, "end": 1.0}, {"text": "dunia", "start": 1.0, "end": 2.0}]
    ass = generate_ass(words, style="static", style_cfg=_cfg(uppercase=True))
    assert "HALO" in ass and "DUNIA" in ass
    assert "halo" not in ass
    print("OK test_generate_ass_uppercase")


def test_generate_ass_empty():
    ass = generate_ass([])
    assert "[Script Info]" in ass
    assert "Dialogue:" not in ass
    print("OK test_generate_ass_empty")


def test_caption_stage_no_clips(tmp_path: Path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        Path("data/clips_raw").mkdir(parents=True)
        Path("data/transcripts").mkdir()
        Path("data/transcripts/job1.json").write_text("[]", encoding="utf-8")

        from types import SimpleNamespace
        config = SimpleNamespace()
        result = CaptionStage().run("job1", None, config)
        assert result.status.value == "done"
        assert result.metadata["clips_captioned"] == 0
        print("OK test_caption_stage_no_clips")
    finally:
        os.chdir(old_cwd)


def test_wrap_scales_with_font_size():
    words = [{"text": f"kata{i}", "start": i * 0.3, "end": i * 0.3 + 0.25} for i in range(30)]
    # size 96 → max_chars = 20; baris wrap tidak boleh melebihi 20 char
    ass = generate_ass(words, style="static", style_cfg=_cfg(size=96))
    for line in ass.splitlines():
        if line.startswith("Dialogue:"):
            text = line.split(",", 9)[-1]
            for visual_line in text.split("\\N"):
                assert len(visual_line.replace(" ", "")) <= 20, f"line too long: {visual_line}"
    # size 60 → max_chars = 33
    ass60 = generate_ass(words, style="static", style_cfg=_cfg(size=60))
    for line in ass60.splitlines():
        if line.startswith("Dialogue:"):
            text = line.split(",", 9)[-1]
            for visual_line in text.split("\\N"):
                assert len(visual_line.replace(" ", "")) <= 33, f"line too long: {visual_line}"


if __name__ == "__main__":
    test_sanitize_ass_text()
    test_sec_to_ass_time()
    test_group_sentences_empty()
    test_group_sentences_max_words()
    test_group_sentences_gap()
    test_hex_to_bgr()
    test_ass_header_custom_style()
    test_generate_ass_static()
    test_generate_ass_highlight_karaoke_lines()
    test_generate_ass_uppercase()
    test_generate_ass_empty()
    with tempfile.TemporaryDirectory() as tmp:
        test_caption_stage_no_clips(Path(tmp))
    print("\nAll caption tests passed.")
