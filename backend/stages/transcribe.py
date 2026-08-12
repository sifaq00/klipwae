import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path

from stages.base import Stage, StageResult, StageStatus
from stages.registry import register
import runtime


def _add_nvidia_dll_paths():
    if sys.platform != "win32":
        return
    for pkg, sub in (("nvidia.cublas", "bin"), ("nvidia.cudnn", "bin")):
        spec = importlib.util.find_spec(pkg)
        if not spec or not spec.submodule_search_locations:
            continue
        dll_dir = Path(spec.submodule_search_locations[0]) / sub
        if dll_dir.exists():
            os.add_dll_directory(str(dll_dir))
            os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")


_add_nvidia_dll_paths()


@register
class TranscribeStage(Stage):
    name = "transcribe"
    depends_on = ["ingest"]

    def max_retries(self) -> int:
        return 1

    def is_complete(self, job_id: str, db) -> bool:
        return Path(f"data/transcripts/{job_id}.json").exists()

    def run(self, job_id: str, db, config):
        import subprocess

        raw_path = Path(f"data/raw/{job_id}.mp4")
        if not raw_path.exists():
            return StageResult(status=StageStatus.FAILED, error=f"Raw video not found: {raw_path}")

        audio_path = Path(f"data/raw/{job_id}.wav")
        if not audio_path.exists():
            subprocess.run([
                "ffmpeg", "-y", "-i", str(raw_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(audio_path),
            ], capture_output=True, check=True, timeout=600)

        segments = run_whisper(audio_path, config.whisper_model, config.whisper_device)

        out_dir = Path("data/transcripts")
        out_dir.mkdir(parents=True, exist_ok=True)

        final_path = out_dir / f"{job_id}.json"
        tmp_path = out_dir / f"{job_id}.json.tmp"
        tmp_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2))
        os.replace(str(tmp_path), str(final_path))

        return StageResult(status=StageStatus.DONE, output_path=str(final_path))


def whisper_compute_type(device: str) -> str:
    """int8_float16 untuk cuda: RTX 2050 4GB tidak muat float16 penuh,
    int8_float16 kualitas hampir setara dengan VRAM ~1.3GB."""
    return "int8" if device == "cpu" else "int8_float16"


def run_whisper(audio_path: Path, model_size: str = "medium", device: str = "cpu") -> list[dict]:
    from faster_whisper import WhisperModel

    local_path = Path(__file__).parent.parent / "models" / f"whisper-{model_size}"
    model_path = str(local_path) if local_path.exists() else model_size

    sys.stdout.write("\r" + " " * 60 + "\r")  # clear line from any previous failed attempt
    sys.stdout.flush()
    print("    Loading model...", end="", flush=True)
    model = WhisperModel(model_path, device=device, compute_type=whisper_compute_type(device))
    print("done", flush=True)

    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language="id",
        vad_filter=True,
    )

    total = info.duration
    transcribed = 0.0
    result = []

    alive = threading.Event()

    def _spinner():
        dots = 0
        while not alive.is_set():
            time.sleep(2)
            dots = (dots + 1) % 8
            sys.stdout.write(f"\r    Transcribing  {'.......'[:dots]}{' ' * (7 - dots)}  0s/{total:.0f}s    ")
            sys.stdout.flush()

    t = threading.Thread(target=_spinner, daemon=True)
    t.start()

    for seg in segments:
        if runtime.stop_requested():
            print("\n    Killed")
            break
        if transcribed == 0:
            alive.set()
            t.join(0.1)
        words = []
        if seg.words:
            words = [{"text": w.word.strip(), "start": w.start, "end": w.end} for w in seg.words]
        result.append({
            "text": seg.text.strip(),
            "start": seg.start,
            "end": seg.end,
            "words": words,
        })
        transcribed += seg.end - seg.start
        pct = transcribed / total * 100
        bar_len = 30
        filled = int(pct / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r    Transcribing |{bar}| {pct:5.1f}% {transcribed:6.0f}s/{total:.0f}s    ")
        sys.stdout.flush()

    alive.set()
    t.join(0.5)
    print()

    return result
