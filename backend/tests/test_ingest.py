import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.ingest import extract_video_id


def test_extract_video_id():
    cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/abc1234567x", "abc1234567x"),
        ("https://m.youtube.com/watch?v=abcdefghijk", "abcdefghijk"),
        ("https://youtube.com/shorts/123456789ab", "123456789ab"),
        ("https://vimeo.com/12345", None),
        ("not a url", None),
        ("", None),
    ]
    for url, expected in cases:
        got = extract_video_id(url)
        assert got == expected, f"{url!r} -> {got!r}, expected {expected!r}"
    print("OK test_extract_video_id")


if __name__ == "__main__":
    test_extract_video_id()
