"""Speaker diarization alias and re-exports."""
from stages.reframe.camera_path import smooth_rapid_speaker_turns
from stages.reframe.diarization import (
    diarize,
    get_diarizer,
    map_speakers_to_sides,
    _load_audio,
    _ensure_hf_token,
)

__all__ = [
    "diarize",
    "get_diarizer",
    "map_speakers_to_sides",
    "smooth_rapid_speaker_turns",
    "_load_audio",
    "_ensure_hf_token",
]
