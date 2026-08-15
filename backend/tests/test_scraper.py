"""Scraper tests — parser + endpoint (yt-dlp di-mock, tanpa network)."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.scraper import parse_scrape_output, scrape_youtube, scrape_channel


def test_parse_scrape_output_basic():
    out = """dQw4w9WgXcQ|Never Gonna Give You Up|Rick Astley|213
    abc1234567x|Podcast Skincare Hari Ini|Kanal Sehat|1500
    """
    items = parse_scrape_output(out)
    assert len(items) == 2
    v = items[0]
    assert v["id"] == "dQw4w9WgXcQ"
    assert v["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert v["title"] == "Never Gonna Give You Up"
    assert v["channel"] == "Rick Astley"
    assert v["duration"] == 213


def test_parse_scrape_output_missing_fields():
    # channel/duration kosong (flat playlist kadang None)
    out = "abc123|Judul Saja||||extra\n"
    items = parse_scrape_output(out)
    assert items[0]["channel"] == ""
    assert items[0]["duration"] is None


def test_parse_scrape_output_dedupes_and_filters():
    out = "aaa|T1|c1|10\naaa|T1|c1|10\nbbb|T2|c2|20\n!@#invalid!!|T3|c3|30\n"
    items = parse_scrape_output(out)
    ids = [v["id"] for v in items]
    assert ids == ["aaa", "bbb"], f"dedupe urut: {ids}"
    assert all(v["id"].isalnum() for v in items)


def test_scrape_youtube_builds_correct_command():
    fake = type("R", (), {"returncode": 0, "stdout": "x|Y|c|1\n", "stderr": ""})()
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return fake

    with patch("utils.scraper.subprocess.run", fake_run):
        items = scrape_youtube("podcast indonesia skincare", limit=25)
    args = calls[0]
    assert "ytsearch25:podcast indonesia skincare" in args, args
    assert "--flat-playlist" in args
    assert "--print" in args
    assert items[0]["id"] == "x"


def test_scrape_youtube_nonzero_rc_raises():
    fake = type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom"})()
    with patch("utils.scraper.subprocess.run", lambda *a, **k: fake):
        try:
            scrape_youtube("q")
            assert False, "harus raise"
        except RuntimeError as e:
            assert "boom" in str(e)


def test_scrape_channel_limits_playlist_items():
    fake = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return fake

    with patch("utils.scraper.subprocess.run", fake_run):
        scrape_channel("https://www.youtube.com/@channel", limit=50)
    args = calls[0]
    assert "--playlist-items" in args
    assert "1-50" in args


if __name__ == "__main__":
    test_parse_scrape_output_basic()
    test_parse_scrape_output_missing_fields()
    test_parse_scrape_output_dedupes_and_filters()
    test_scrape_youtube_builds_correct_command()
    test_scrape_youtube_nonzero_rc_raises()
    test_scrape_channel_limits_playlist_items()
    print("all ok")