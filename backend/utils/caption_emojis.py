"""Auto-emoji injection for caption keywords (Indonesian & English terms)."""
import re

EMOJI_KEYWORDS: dict[str, str] = {
    # ✨
    "glowing": "✨",
    "bagus": "✨",
    "mantap": "✨",
    "keren": "✨",
    "viral": "✨",
    "juara": "✨",
    # 🔥
    "api": "🔥",
    "panas": "🔥",
    "gokil": "🔥",
    "terbaik": "🔥",
    "gila": "🔥",
    # 💸
    "mahal": "💸",
    "murah": "💸",
    "harga": "💸",
    "diskon": "💸",
    "cuan": "💸",
    "beli": "💸",
    "jual": "💸",
    "rupiah": "💸",
    "promo": "💸",
    # 😱
    "kaget": "😱",
    "syok": "😱",
    "bahaya": "😱",
    "zonk": "😱",
    "bohong": "😱",
    "parah": "😱",
    "nyesel": "😱",
    # 🧴
    "skincare": "🧴",
    "serum": "🧴",
    "cream": "🧴",
    "wajah": "🧴",
    "kulit": "🧴",
    "sunscreen": "🧴",
    "moisturizer": "🧴",
    # 🤤
    "makan": "🤤",
    "minum": "🤤",
    "enak": "🤤",
    "kuliner": "🤤",
    "resep": "🤤",
    "masak": "🤤",
}

_CLEAN_RE = re.compile(r"[^\w]")


def clean_word(text: str) -> str:
    """Strip all punctuation and convert to lowercase for keyword matching."""
    return _CLEAN_RE.sub("", text).lower()


def inject_caption_emojis(words: list[dict]) -> list[dict]:
    """Appends contextual emojis to keyword words in the caption list.

    Preserves original timestamps and other metadata while updating text.
    """
    out = []
    for w in words:
        item = dict(w)
        raw_text = str(w.get("text", ""))
        cleaned = clean_word(raw_text)
        if cleaned in EMOJI_KEYWORDS:
            emoji = EMOJI_KEYWORDS[cleaned]
            item["text"] = f"{raw_text} {emoji}"
        out.append(item)
    return out
