"""Scraper: cari video YouTube via yt-dlp flat-playlist (cepat, tanpa download)
— feed halaman Scraper UI (natural-language query → daftar video → tambah ke
Studio)."""
import re
import subprocess
from pathlib import Path

_MAX_LIMIT = 100
_TIMEOUT = 60
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def parse_scrape_output(stdout: str) -> list[dict]:
    """Parse baris 'id|title|channel|duration' dari yt-dlp --print.

    Format via --print "%(id)s|%(title)s|%(channel)s|%(duration)s".
    Channel/duration bisa None (flat playlist) → direpresentasikan kosong.
    """
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 3)
        vid = parts[0].strip()
        if not vid or len(vid) > 20 or not _YT_ID_RE.match(vid):
            continue
        title = parts[1].strip() if len(parts) > 1 else ""
        channel = parts[2].strip() if len(parts) > 2 else ""
        dur_raw = parts[3].strip() if len(parts) > 3 else ""
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

    ytsearchN:query — flat-playlist = metadata saja (judul/channel/durasi),
    tanpa download → cepat + hemat. Gagal → raise RuntimeError (server
    map ke 502).
    """
    limit = max(1, min(limit, _MAX_LIMIT))
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--no-warnings",
         "--print", "%(id)s|%(title)s|%(channel)s|%(duration)s",
         f"ytsearch{limit}:{query}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp search failed: {result.stderr.strip()[:300]}")
    return parse_scrape_output(result.stdout)


def scrape_channel(channel_url: str, limit: int = 100) -> list[dict]:
    """List video dari channel/playlist URL (flat, metadata saja)."""
    limit = max(1, min(limit, _MAX_LIMIT))
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--no-warnings",
         "--print", "%(id)s|%(title)s|%(channel)s|%(duration)s",
         "--playlist-items", f"1-{limit}", channel_url],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp channel scrape failed: {result.stderr.strip()[:300]}")
    return parse_scrape_output(result.stdout)
