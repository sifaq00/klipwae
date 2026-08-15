import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.caption_emojis import clean_word, inject_caption_emojis, EMOJI_KEYWORDS


def test_clean_word():
    assert clean_word("keren!") == "keren"
    assert clean_word("(glowing)") == "glowing"
    assert clean_word("MANTAP...") == "mantap"
    assert clean_word("diskon,") == "diskon"
    assert clean_word("100%") == "100"


def test_inject_caption_emojis_categories():
    words = [
        {"text": "glowing", "start": 0.0, "end": 0.5},
        {"text": "api", "start": 0.5, "end": 1.0},
        {"text": "diskon", "start": 1.0, "end": 1.5},
        {"text": "kaget", "start": 1.5, "end": 2.0},
        {"text": "skincare", "start": 2.0, "end": 2.5},
        {"text": "makan", "start": 2.5, "end": 3.0},
        {"text": "biasa", "start": 3.0, "end": 3.5},
    ]
    result = inject_caption_emojis(words)
    assert result[0]["text"] == "glowing ✨"
    assert result[1]["text"] == "api 🔥"
    assert result[2]["text"] == "diskon 💸"
    assert result[3]["text"] == "kaget 😱"
    assert result[4]["text"] == "skincare 🧴"
    assert result[5]["text"] == "makan 🤤"
    assert result[6]["text"] == "biasa"

    # Verify timestamps preserved
    for original, res in zip(words, result):
        assert res["start"] == original["start"]
        assert res["end"] == original["end"]


def test_inject_caption_emojis_punctuation_and_case():
    words = [
        {"text": "Keren!", "start": 0.0, "end": 0.5},
        {"text": "BAGUS,", "start": 0.5, "end": 1.0},
        {"text": "gila...", "start": 1.0, "end": 1.5},
        {"text": "cuan!!", "start": 1.5, "end": 2.0},
    ]
    result = inject_caption_emojis(words)
    assert result[0]["text"] == "Keren! ✨"
    assert result[1]["text"] == "BAGUS, ✨"
    assert result[2]["text"] == "gila... 🔥"
    assert result[3]["text"] == "cuan!! 💸"


def test_inject_caption_emojis_empty_and_no_match():
    assert inject_caption_emojis([]) == []
    words = [{"text": "halo", "start": 0.0, "end": 0.5}, {"text": "semua", "start": 0.5, "end": 1.0}]
    result = inject_caption_emojis(words)
    assert result[0]["text"] == "halo"
    assert result[1]["text"] == "semua"
