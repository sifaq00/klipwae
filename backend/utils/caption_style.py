"""Konfigurasi gaya subtitle: global (default) + override per job.

Lokasi global: data/caption_style.json. Override per job: kolom jobs.caption_style.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
GLOBAL_STYLE_PATH = DATA_DIR / "caption_style.json"

DEFAULT_STYLE: dict = {
    "enabled": True,
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

# Tipe per key — dipakai validasi PUT supaya nilai rusak (size="abc")
# tidak sampai ke ffmpeg/libass dan bikin preview/burn 500.
INT_KEYS = {"size", "spacing", "line_spacing", "outline", "shadow", "margin_v"}
BOOL_KEYS = {"enabled", "bold", "italic", "uppercase", "pop"}
STR_KEYS = {
    "font", "text_color", "highlight_color", "outline_color",
    "shadow_color", "position", "border_style", "style",
}


def validate(style: dict) -> dict | None:
    """Coerce & validasi nilai (body parsial dianggap full default).
    Invalid → None; valid → style lengkap."""
    clean = {k: style.get(k, DEFAULT_STYLE[k]) for k in KEYS}
    for k, v in list(clean.items()):
        if k not in KEYS:
            continue
        try:
            if k in INT_KEYS:
                clean[k] = int(v)
            elif k in BOOL_KEYS:
                clean[k] = bool(v) if isinstance(v, bool) else str(v).lower() == "true"
        except (TypeError, ValueError):
            return None
    if clean.get("style") not in ("highlight", "bg", "classic", "pop"):
        return None
    if clean.get("position") not in ("bottom", "top"):
        return None
    if clean.get("border_style") not in ("outline", "box"):
        return None
    for k in STR_KEYS:
        if k not in clean:
            continue
        v = str(clean[k])
        if len(v) > 200:
            return None
        clean[k] = v
    return clean


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
