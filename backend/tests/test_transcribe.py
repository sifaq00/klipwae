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
            transcribe.run_whisper = lambda audio, m, d: fake_segments

            from stages.transcribe import TranscribeStage
            config = SimpleNamespace(whisper_model="medium", whisper_device="cpu")
            result = TranscribeStage().run("job", None, config)

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
