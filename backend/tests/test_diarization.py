import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.reframe.diarization import map_speakers_to_sides


def test_mar_none_falls_back_to_previous():
    diar = [(0.0, 2.0, "SPEAKER_00"), (2.0, 4.0, "SPEAKER_01")]
    out = map_speakers_to_sides(diar, None)
    assert out == [(0.0, 2.0, "previous"), (2.0, 4.0, "previous")]


def test_mar_empty_falls_back_to_previous():
    diar = [(0.0, 2.0, "SPEAKER_00")]
    out = map_speakers_to_sides(diar, [])
    assert out == [(0.0, 2.0, "previous")]


def test_mar_normal_still_votes():
    diar = [(0.0, 3.0, "SPEAKER_00")]
    mar = [(0.0, 3.0, "left")]
    out = map_speakers_to_sides(diar, mar)
    assert out == [(0.0, 3.0, "left")]
