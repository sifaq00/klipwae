"""Scraper: cari video YouTube via yt-dlp flat-playlist (cepat, tanpa download)
— feed halaman Scraper UI (natural-language query → daftar video → tambah ke
Studio)."""
import json
import re
import subprocess
from pathlib import Path

_MAX_LIMIT = 100
_TIMEOUT = 60
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def parse_scrape_output(stdout: str) -> list[dict]:
    """Parse baris 'id|title|channel|duration|description' dari yt-dlp --print.

    Format via --print "%(id)s|%(title)s|%(channel)s|%(duration)s|%(description)s".
    Channel/duration/description bisa None (flat playlist) → kosong/None.
    """
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 4)
        vid = parts[0].strip()
        if not vid or len(vid) > 20 or not _YT_ID_RE.match(vid):
            continue
        title = parts[1].strip() if len(parts) > 1 else ""
        channel = parts[2].strip() if len(parts) > 2 else ""
        dur_raw = parts[3].strip() if len(parts) > 3 else ""
        desc = parts[4].strip() if len(parts) > 4 else ""
        try:
            duration = int(dur_raw) if dur_raw else None
        except ValueError:
            duration = None
        out.append({
            "id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": title,
            "channel": channel,
            "duration": duration,
            "description": desc[:400],
            "score": 0,
        })
    # dedupe by id, urutan tetap
    seen = set()
    deduped = []
    for v in out:
        if v["id"] not in seen:
            seen.add(v["id"])
            deduped.append(v)
    return deduped


def scrape_youtube(query: str, limit: int = 50) -> list[dict]:
    """Search YouTube dengan query natural-language via yt-dlp.

    ytsearchN:query — flat-playlist = metadata saja (judul/channel/durasi/
    deskripsi), tanpa download → cepat + hemat. Gagal → raise RuntimeError
    (server map ke 502).
    """
    limit = max(1, min(limit, _MAX_LIMIT))
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--no-warnings",
             "--print", "%(id)s|%(title)s|%(channel)s|%(duration)s|%(description)s",
             f"ytsearch{limit}:{query}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"yt-dlp search timed out (> {_TIMEOUT}s)") from None
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp search failed: {result.stderr.strip()[:300]}")
    return parse_scrape_output(result.stdout)


def scrape_channel(channel_url: str, limit: int = 100) -> list[dict]:
    """List video dari channel/playlist URL (flat, metadata saja)."""
    limit = max(1, min(limit, _MAX_LIMIT))
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--no-warnings",
             "--print", "%(id)s|%(title)s|%(channel)s|%(duration)s|%(description)s",
             "--playlist-items", f"1-{limit}", channel_url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"yt-dlp channel scrape timed out (> {_TIMEOUT}s)") from None
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp channel scrape failed: {result.stderr.strip()[:300]}")
    return parse_scrape_output(result.stdout)


# ---- Lapis 1+3: skor relevansi + expander Gemini + multi-query ----

def score_item(item: dict, keywords: list[str]) -> float:
    """Skor relevansi: keyword di judul bobot 2x, di deskripsi 1x.
    Case-insensitive. Tanpa match → 0."""
    hay_title = item.get("title", "").lower()
    hay_desc = item.get("description", "").lower()
    score = 0.0
    for kw in keywords:
        k = kw.lower()
        if k in hay_title:
            score += 2.0
        if k in hay_desc:
            score += 1.0
    return score


def _gemini_expand(query: str, count: int = 4):
    """Gemini: query natural-language → daftar variasi kata kunci pencarian."""
    from google import genai
    from pydantic import BaseModel

    class QueryList(BaseModel):
        queries: list[str]

    from config import Settings
    cfg = Settings()
    client = genai.Client(api_key=cfg.google_api_key)
    return client.models.generate_content(
        model=cfg.analyze_model,
        contents=(
            f"User ingin mencari video YouTube. Ubah keinginan ini menjadi "
            f"{count} query pencarian yang BERBEDA namun tetap relevan (bahasa "
            f"Indonesia, frasa yang orang biasa ketik di YouTube, spesifik ke "
            f"topik produk/sponsor kalau disebut). Jangan tambahkan quotes.\n\n"
            f"Keinginan: {query}"
        ),
        config={
            "response_mime_type": "application/json",
            "response_schema": QueryList,
            "temperature": 0.4,
        },
    )


_STOPWORDS = {
    "seperti", "podcastnya", "podcast", "indonesia", "yang", "di", "dalam",
    "dalamnya", "ada", "pembahasan", "dan", "serta", "nya", "dll", "dst",
    "dsb", "buat", "untuk", "sama", "dengan", "misal", "contoh", "tolong",
    "cari", "carikan", "mau", "pengen", "ingin", "sejenisnya", "juga",
    "atau", "saya", "aku", "kamu", "gw", "gue", "bisa", "tidak", "bukan",
}


def _fallback_queries(query: str, count: int = 3) -> list[str]:
    """Pecah query kalimat panjang jadi frasa pendek yang bisa dicari —
    TANPA Gemini. Query utuh yang panjang > 60 char bikin yt-dlp 0 hasil.
    Kalau query asli menyebut 'podcast', frasa di-prefix 'podcast' biar
    search kontekstual (bukan 'kecantikan' generik)."""
    want_podcast = "podcast" in query.lower()
    parts = [p.strip() for p in re.split(r"[,;()/]+", query) if p.strip()]
    frases = []
    for p in parts:
        words = [w for w in re.findall(r"[a-zA-Z0-9]+", p) if w.lower() not in _STOPWORDS]
        if words:
            frases.append(" ".join(words))
    # ambil frasa dengan kata terbanyak dulu (paling spesifik)
    frases.sort(key=lambda f: len(f.split()), reverse=True)
    frases = [f for f in frases if len(f) <= 60][:count]
    if want_podcast:
        frases = [f"podcast {f}" if not f.lower().startswith("podcast") else f for f in frases]
    if not frases:
        words = [w for w in re.findall(r"[a-zA-Z0-9]+", query) if w.lower() not in _STOPWORDS]
        frases = [" ".join(words[:6])] if words else [query[:60]]
        if want_podcast and not frases[0].lower().startswith("podcast"):
            frases[0] = f"podcast {frases[0]}"
    return frases or [query[:60]]


_EXPAND_CACHE: dict[str, list[str]] = {}
_EXPAND_CACHE_MAX = 256


def expand_query(query: str, count: int = 4) -> list[str]:
    """Query → variasi pencarian via Gemini (retry 2x + jeda — rawan
    rate-limit kalau pipeline sedang jalan). Gagal → fallback frasa pendek
    (bukan query utuh — yang panjang bikin yt-dlp 0 hasil).

    Cache per query: kuota free-tier 20 request/hari, query yang sama
    dipakai ulang TIDAK boleh makan request Gemini baru."""
    cached = _EXPAND_CACHE.get(query)
    if cached:
        return cached
    import time
    for attempt in range(2):
        try:
            resp = _gemini_expand(query, count)
            qs = [q.strip() for q in resp.parsed.queries if q and q.strip()]
            if qs:
                result = qs[:count]
                if len(_EXPAND_CACHE) < _EXPAND_CACHE_MAX:
                    _EXPAND_CACHE[query] = result
                return result
        except Exception:
            pass
        time.sleep(1.0 * (attempt + 1))
    return _fallback_queries(query, count)


def scrape_multi(query: str, limit: int = 50, min_duration: int = 0,
                 keywords: list[str] | None = None) -> list[dict]:
    """Lapis 1+3: expand query → scrape tiap variasi → merge + dedupe →
    filter durasi → skor relevansi → urutkan menurun → cap limit.

    min_duration > 0: video lebih pendek dibuang (podcast = panjang).
    keywords: kalau diberikan, dipakai untuk skor (default: pecahan query).
    """
    queries = expand_query(query)
    per = max(1, limit // len(queries))
    merged: dict[str, dict] = {}
    for q in queries:
        try:
            for item in scrape_youtube(q, limit=per):
                merged[item["id"]] = item
        except RuntimeError:
            continue  # satu sub-query gagal → lanjut yang lain

    if keywords is None:
        words = re.findall(r"[a-zA-Z0-9]+", query.lower())
        keywords = [w for w in words if len(w) > 3 and w not in _STOPWORDS] or [query]

    result = []
    for item in merged.values():
        if min_duration > 0 and item["duration"] is not None and item["duration"] < min_duration:
            continue
        item["score"] = round(score_item(item, keywords), 1)
        result.append(item)
    result.sort(key=lambda i: i["score"], reverse=True)
    return result[:limit]
