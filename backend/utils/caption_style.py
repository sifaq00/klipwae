"""Konfigurasi gaya subtitle: global (default) + override per job.

Lokasi global: data/caption_style.json. Override per job: kolom jobs.caption_style.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
GLOBAL_STYLE_PATH = DATA_DIR / "caption_style.json"

DEFAULT_STYLE: dict = {
    "font": "Segoe UI",
    "size": 96,
    "bold": True,
    "italic": False,
    "uppercase": False,
    "pop": False,
    "spacing": 0,
    "line_spacing": 0,
    "text_color": "#FFFFFF",
    "highlight_color": "#FFFF00",
    "outline": 6,
    "outline_color": "#000000",
    "border_style": "outline",  # "outline" (garis) | "box" (kotak backdrop)
    "shadow": 3,
    "shadow_color": "#000000",
    "position": "bottom",
    "margin_v": 240,  # TikTok UI safe zone — subtitle tidak ketutup elemen bawah
    "style": "highlight",
}

KEYS = set(DEFAULT_STYLE.keys())


def load_global() -> dict:
    style = dict(DEFAULT_STYLE)
    try:
        data = json.loads(GLOBAL_STYLE_PATH.read_text(encoding="utf-8"))
        for k in KEYS:
            if k in data:
                style[k] = data[k]
    except (OSError, json.JSONDecodeError):
        pass
    return style


def save_global(style: dict) -> dict:
    clean = {k: style.get(k, DEFAULT_STYLE[k]) for k in KEYS}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GLOBAL_STYLE_PATH.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return clean


def style_for_job(job_style: str | None) -> dict:
    """Gabungkan global + override job. Kalau job_style bukan JSON valid,
    return global saja."""
    style = load_global()
    if job_style:
        try:
            data = json.loads(job_style)
            for k in KEYS:
                if k in data:
                    style[k] = data[k]
        except (json.JSONDecodeError, TypeError):
            pass
    return style
