import subprocess
import sys
from functools import lru_cache


def run_ffmpeg(args: list[str], timeout: int = 300, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Jalankan ffmpeg + daftarkan ke runtime biar bisa di-terminate saat kill.

    (sebelumnya subprocess.run — kill job tidak menyentuh ffmpeg: clip/caption/
    burn tetap jalan sampai selesai walau job sudah "killed".)"""
    import runtime

    proc = subprocess.Popen(["ffmpeg", "-y"] + args, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, cwd=cwd)
    runtime.set_proc(proc)
    try:
        _, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, err = proc.communicate()
        raise RuntimeError(f"ffmpeg timeout ({timeout}s)") from None
    finally:
        runtime.clear_proc(proc)
    return subprocess.CompletedProcess(args, proc.returncode, stdout=b"", stderr=err)


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
