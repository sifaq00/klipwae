import subprocess
from pathlib import Path


def get_video_info(video_path: Path) -> tuple[float, float]:
    """(fps, duration) via ffprobe — satu implementasi untuk semua pemanggil
    (sebelumnya di-duplikat: __init__._get_video_info vs render.py parse
    stderr ffmpeg -f null)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate,duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, timeout=30,
    )
    parts = result.stdout.strip().split(",")
    if len(parts) < 2:
        return 30.0, 0.0
    fps_str = parts[0]
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if den != "0" else 30.0
    else:
        fps = float(fps_str)
    try:
        duration = float(parts[1])
    except ValueError:
        duration = 0.0
    return fps, duration
