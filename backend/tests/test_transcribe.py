import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_transcribe_atomic_write():
    """Atomic write pattern (plan Section 4.1 bug trap): tmp -> os.replace -> final.
    Verifies output JSON valid, schema benar, tmp file bersih."""
    with tempfile.TemporaryDirectory() as tmp:
        old_cwd = os.getcwd()
        os.chdir(tmp)
        try:
            Path("data/raw").mkdir(parents=True)
            Path("data/raw/job.mp4").touch()
            Path("data/raw/job.wav").touch()  # skip ffmpeg extraction

            fake_segments = [
                {
                    "text": "halo",
                    "start": 0.0,
                    "end": 1.0,
                    "words": [{"text": "halo", "start": 0.0, "end": 1.0}],
                }
            ]

            from stages import transcribe
            orig_run_whisper = transcribe.run_whisper
            transcribe.run_whisper = lambda audio, m, d, initial_prompt="": fake_segments

            from stages.transcribe import TranscribeStage
            config = SimpleNamespace(whisper_model="medium", whisper_device="cpu")
            try:
                result = TranscribeStage().run("job", None, config)
            finally:
                transcribe.run_whisper = orig_run_whisper

            assert result.status.value == "done", f"status={result.status}"
            out = Path("data/transcripts/job.json")
            assert out.exists(), "Output JSON tidak ditulis"
            data = json.loads(out.read_text())
            assert data == fake_segments, "Isi JSON tidak sesuai mock"
            assert not Path("data/transcripts/job.json.tmp").exists(), "Tmp file tertinggal"
            print("OK test_transcribe_atomic_write")
        finally:
            os.chdir(old_cwd)


if __name__ == "__main__":
    test_transcribe_atomic_write()


def test_whisper_compute_type():
    from stages.transcribe import whisper_compute_type
    assert whisper_compute_type("cpu") == "int8"
    assert whisper_compute_type("cuda") == "int8_float16"


def test_run_whisper_language_auto_and_initial_prompt(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    model = MagicMock()
    seg = SimpleNamespace(text="halo", start=0.0, end=1.0, words=[])
    info = SimpleNamespace(duration=10.0)
    model.transcribe.return_value = (iter([seg]), info)

    with patch("faster_whisper.WhisperModel", return_value=model) as mock_cls:
        from stages.transcribe import run_whisper
        run_whisper(audio, "large-v3-turbo", "cpu", initial_prompt="Somethinc Creatine")

    assert mock_cls.call_args.kwargs["compute_type"] == "int8"
    kwargs = model.transcribe.call_args.kwargs
    assert kwargs["language"] is None
    assert kwargs["initial_prompt"] == "Somethinc Creatine"
