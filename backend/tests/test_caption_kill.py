"""Kill-aware caption: pas stop_requested, burn dibatalkan — bukan cuma
mematikan ffmpeg yang jalan lalu sisanya tetap encode berjam-jam."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import runtime
from stages.caption import CaptionStage


def test_caption_stops_on_kill():
    jid = "killtest"
    tdir = Path("data/transcripts")
    tdir.mkdir(parents=True, exist_ok=True)
    tp = tdir / f"{jid}.json"
    tp.write_text(json.dumps([{"start": 0, "end": 10, "words": [{"text": "a", "start": 0, "end": 1}]}]), encoding="utf-8")
    db = MagicMock()
    db.get_job_segments.return_value = [{"id": 1, "clip_path": "data/clips_raw/killtest.mp4"}]
    db.get_job_style.return_value = None

    orig = runtime.stop_requested
    runtime.stop_requested = lambda job_id: True
    try:
        res = CaptionStage().run(jid, db, MagicMock())
    finally:
        runtime.stop_requested = orig
        tp.unlink(missing_ok=True)

    assert res.metadata["clips_captioned"] == 0, res.metadata
    db.update_segment_by_id.assert_not_called()
    print("OK test_caption_stops_on_kill")


if __name__ == "__main__":
    test_caption_stops_on_kill()
    print("all ok")
