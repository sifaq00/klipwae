"""Scraper tests â€” parser + endpoint (yt-dlp di-mock, tanpa network)."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.scraper import (
    parse_scrape_output, scrape_youtube, scrape_channel,
    score_item, expand_query, scrape_multi,
)


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


# ---- Lapis 1+3: skor relevansi, expander Gemini, multi-query ----

def test_score_item_ranks_title_over_description():
    base = {"id": "x", "title": "", "channel": "", "duration": None, "description": ""}
    # title match bobot 2x, description 1x
    t = score_item({**base, "title": "Review Skincare Sponsor Podcast"}, ["skincare", "sponsor"])
    d = score_item({**base, "description": "review skincare sponsor podcast"}, ["skincare", "sponsor"])
    assert t > d, f"title harus > description: {t} vs {d}"
    # case-insensitive
    assert score_item({**base, "title": "REVIEW SKINCARE"}, ["skincare"]) > 0
    # tanpa match = 0
    assert score_item({**base, "title": "Vlog Liburan"}, ["skincare"]) == 0


def test_expand_query_uses_gemini_and_falls_back():
    # fallback: gemini gagal â†’ frasa pendek ber-prefix podcast (kontekstual)
    with patch("utils.scraper._gemini_expand", side_effect=RuntimeError("no key")):
        qs = expand_query("podcast skincare sponsor")
    assert "podcast skincare sponsor" in qs, f"fallback: {qs}"

    # sukses: parse JSON array
    class FakeResp:
        parsed = type("P", (), {"queries": ["q1", "q2", "q3"]})()
    with patch("utils.scraper._gemini_expand", return_value=FakeResp()):
        qs = expand_query("cari podcast")
    assert qs == ["q1", "q2", "q3"]


def test_fallback_queries_splits_long_query():
    """Gemini mati + query kalimat panjang â†’ yt-dlp 0 hasil. Fallback harus
    pecah jadi frasa pendek yang bisa dicari, bukan query utuh."""
    from utils.scraper import _fallback_queries
    q = ("podcast indonesia seperti podcastnya radityadika, kasisolusi, pwk dll, "
         "yang di dalamnya ada pembahasan produk kecantikan/kesehatan/kebugaran dan sejenisnya")
    qs = _fallback_queries(q)
    assert qs, "harus ada frasa"
    assert all(len(fr) <= 60 for fr in qs), f"frasa kebanyakan panjang: {qs}"
    # query utuh TIDAK boleh jadi fallback (pasti 0 hasil di yt-dlp)
    assert q not in qs, qs
    print("OK test_fallback_queries_splits_long_query")


def test_scrape_multi_uses_fallback_when_gemini_down():
    """Gemini down â†’ fallback frasa pendek tetap kasih hasil."""
    fake = type("R", (), {"returncode": 0, "stdout": "x|T|C|100|d\n", "stderr": ""})()

    def fake_run(args, **kw):
        q = args[-1]
        assert "ytsearch" in q
        return fake

    with patch("utils.scraper.subprocess.run", fake_run), \
         patch("utils.scraper._gemini_expand", side_effect=RuntimeError("down")):
        items = scrape_multi("podcast indonesia bahas skincare sponsor, produk kecantikan", limit=3,
                             min_duration=0, keywords=["skincare"])
    assert len(items) >= 1, "fallback harus tetap kasih hasil"


def test_scrape_multi_merges_dedupes_scores_and_caps():
    fake = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    def fake_run(args, **kw):
        q = args[-1]
        if "q1" in q:
            out = ("aaa|Podcast Skincare Review|C1|1800|deskripsi sponsor produk\n"
                   "bbb|Vlog Liburan|C2|600|jalan jalan\n")
        else:
            out = ("aaa|Podcast Skincare Review|C1|1800|deskripsi sponsor produk\n"
                   "ccc|Review Produk Kecantikan|C3|2400|sponsor skincare\n")
        return type("R", (), {"returncode": 0, "stdout": out, "stderr": ""})()

    with patch("utils.scraper.subprocess.run", fake_run), \
         patch("utils.scraper.expand_query", return_value=["q1", "q2"]):
        items = scrape_multi("podcast skincare", limit=5, min_duration=900,
                             keywords=["skincare", "sponsor", "review"])
    ids = [i["id"] for i in items]
    assert ids == ["aaa", "ccc"], f"dedupe + urut skor: {ids}"
    assert len(items) == 2
    assert all(i["duration"] is None or i["duration"] >= 900 for i in items)
    # aaa dapat skor lebih tinggi (3 keyword di title) daripada ccc
    assert items[0]["score"] > items[1]["score"], items


def test_expand_query_caches_identical_queries():
    """Query sama â†’ Gemini dipanggil SEKALI (cache) â€” kuota free-tier
    20/hari, tiap pencarian ulang tak boleh makan request baru."""
    import utils.scraper as scraper
    calls = {"n": 0}

    class FakeResp:
        parsed = type("P", (), {"queries": ["q1", "q2", "q3"]})()

    def fake_expand(query, count=4):
        calls["n"] += 1
        return FakeResp()

    scraper._EXPAND_CACHE.clear()
    orig = scraper._gemini_expand
    scraper._gemini_expand = fake_expand
    try:
        a = scraper.expand_query("podcast skincare sponsor")
        b = scraper.expand_query("podcast skincare sponsor")
        assert a == b == ["q1", "q2", "q3"]
    finally:
        scraper._gemini_expand = orig
        scraper._EXPAND_CACHE.clear()
    assert calls["n"] == 1, f"Gemini harus 1x utk query sama, got {calls['n']}"


def test_expand_query_cache_misses_on_different_query():
    import utils.scraper as scraper

    class FakeResp:
        parsed = type("P", (), {"queries": ["q1"]})()

    orig = scraper._gemini_expand
    scraper._gemini_expand = lambda query, count=4: FakeResp()
    scraper._EXPAND_CACHE.clear()
    try:
        scraper.expand_query("query satu")
        scraper.expand_query("query dua")
        assert len(scraper._EXPAND_CACHE) == 2
    finally:
        scraper._gemini_expand = orig
        scraper._EXPAND_CACHE.clear()


def test_scrape_multi_respects_cap():
    fake = type("R", (), {"returncode": 0, "stdout": "x|T|C|100|d\n", "stderr": ""})()
    with patch("utils.scraper.subprocess.run", lambda *a, **k: fake), \
         patch("utils.scraper.expand_query", return_value=["q"]):
        items = scrape_multi("q", limit=3, min_duration=0, keywords=["t"])
    assert len(items) <= 3


if __name__ == "__main__":
    test_parse_scrape_output_basic()
    test_parse_scrape_output_missing_fields()
    test_parse_scrape_output_dedupes_and_filters()
    test_scrape_youtube_builds_correct_command()
    test_scrape_youtube_nonzero_rc_raises()
    test_scrape_channel_limits_playlist_items()
    print("all ok")