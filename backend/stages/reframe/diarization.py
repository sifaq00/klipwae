"""Speaker diarization via PyAnnote 3.1 (model lokal, CUDA).

Ngukur siapa yang bicara dari AUDIO — jatuh lebih akurat dari gerak bibir
(mediapipe MAR) yang gagal kalau wajah ketutup atau miring. Semua model
di-bundle lokal: models/pyannote/{diarization-3.1, wespeaker, segmentation-3.0}.
"""
import os
import structlog

logger = structlog.get_logger(__name__)

_pipeline = None


def _ensure_hf_token():
    """pyannote 4.x fetch beberapa asset (xvec_transform) dari HF — butuh
    HF_TOKEN dari .env biar bisa akses repo gated yang sudah di-accept."""
    from dotenv import load_dotenv
    load_dotenv()
    if os.environ.get("HF_TOKEN"):
        os.environ.setdefault("HF_TOKEN", os.environ["HF_TOKEN"])


def get_diarizer():
    global _pipeline
    if _pipeline is None:
        from pathlib import Path
        from pyannote.audio import Pipeline
        import torch
        _ensure_hf_token()
        cfg_dir = Path(__file__).parent.parent.parent / "models" / "pyannote" / "diarization-3.1"
        _pipeline = Pipeline.from_pretrained(str(cfg_dir))
        if torch.cuda.is_available():
            _pipeline.to(torch.device("cuda"))
    return _pipeline


def _load_audio(video_path) -> dict | None:
    """Decode audio via ffmpeg → torch tensor (1, N) @16kHz — menghindari
    dependency torchcodec yang DLL-nya bentrok dengan torch 2.11."""
    import subprocess
    import numpy as np
    import torch
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video_path),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True, timeout=300,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    audio = np.frombuffer(result.stdout, dtype=np.float32)
    if len(audio) < 1600:
        return None
    return {"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": 16000}


def diarize(video_path) -> list[tuple[float, float, str]] | None:
    """[(start, end, speaker_id)] — dari audio video. Gagal → None (fallback MAR)."""
    try:
        waveform = _load_audio(video_path)
        if waveform is None:
            return None
        result = get_diarizer()(waveform)
        # pyannote 4.x: pipeline returns DiarizeOutput → .speaker_diarization
        ann = getattr(result, "speaker_diarization", result)
        return [(seg.start, seg.end, label) for seg, _, label in ann.itertracks(yield_label=True)]
    except Exception as e:
        logger.warning("diarization_failed", error=str(e))
        return None


def map_speakers_to_sides(diar: list[tuple[float, float, str]], mar: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Petakan speaker (dari audio) → sisi kamera (dari MAR bibir).

    Untuk tiap window diarization, ambil sisi mayoritas window MAR yang
    overlap. Kalau nggak ada overlap → "previous" (dibiarkan camera_path
    memutuskan). MAR di sini cuma jembatan audio→posisi.
    """
    if not diar:
        return mar
    if not mar:
        return [("previous" if s != "previous" else s, e, s) if False else (s, e, "left") for s, e, _ in diar]

    out = []
    for ds, de, speaker in diar:
        side_votes: dict[str, int] = {}
        for ms, me, side in mar:
            if side == "previous":
                continue
            overlap = min(de, me) - max(ds, ms)
            if overlap > 0.15:
                side_votes[side] = side_votes.get(side, 0) + overlap
        if side_votes:
            out.append((ds, de, max(side_votes, key=side_votes.get)))
        else:
            out.append((ds, de, "previous"))
    return out