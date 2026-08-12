import subprocess
import sys
from functools import lru_cache


def run_ffmpeg(args: list[str], timeout: int = 300, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-y"] + args, capture_output=True, text=True, timeout=timeout, cwd=cwd)


@lru_cache(maxsize=1)
def nvenc_available() -> bool:
    """Probe sekali per proses: NVENC (GPU) ~5-10x lebih cepat dari libx264 CPU."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=15,
        )
        return "h264_nvenc" in r.stdout
    except Exception:
        return False


def video_encode_args() -> list[str]:
    if nvenc_available():
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23"]
    # ponytail: fallback CPU kalau NVENC nggak ada
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
