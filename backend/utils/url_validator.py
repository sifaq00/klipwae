import re

YOUTUBE_RE = re.compile(r"^https?://(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)/")


def is_valid_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_RE.match(url))
