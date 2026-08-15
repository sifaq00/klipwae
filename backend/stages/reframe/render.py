import shutil
import tempfile
from pathlib import Path

from utils.ffmpeg_helpers import run_ffmpeg, video_encode_args


def render_center_crop(
    input_path: Path, output_path: Path,
    target_w: int = 1080, target_h: int = 1920, zoom: float = 0.35,
):
    if zoom > 0.01:
        # Push-in halus di single_shot juga — bikin klip "hidup" tanpa pan
        fps, duration = _get_video_info(input_path)
        rate = zoom / max(1.0, duration * fps)
        max_z = 1 + zoom
        filter_complex = (
            f"crop='min(iw\\,ih*9/16)':'min(ih\\,iw*16/9)',"
            f"scale=2160:3840:force_original_aspect_ratio=increase,"
            f"crop=2160:3840,"
            f"zoompan=z='min(1+{rate}*on,{max_z})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={target_w}x{target_h}:fps={fps},"
            f"format=yuv420p"
        )
    else:
        filter_complex = (
            f"crop='min(iw\\,ih*9/16)':'min(ih\\,iw*16/9)',"
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black"
        )
    result = run_ffmpeg([
        "-i", str(input_path),
        "-vf", filter_complex,
        *video_encode_args(),
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ], timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg center-crop failed: {result.stderr[-500:].decode('utf-8', errors='replace')}")


def render_split_screen(
    input_path: Path,
    camera_path: list[tuple[float, float, str]],
    regions: dict,
    output_path: Path,
):
    if not camera_path:
        render_center_crop(input_path, output_path)
        return

    fps, _ = _get_video_info(input_path)

    subclips = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (start, end, side) in enumerate(camera_path):
            region = regions.get(side)
            if region is None:
                continue
            sub = Path(tmp) / f"sub_{i}.mp4"
            duration = end - start
            if duration <= 0:
                continue
            # Zoom push-in halus: segmen yang DITAMPILKAN = speaker aktif,
            # slow zoom 1.0 â†’ 1.45 selama durasi segmen (gaya Opus Clip).
            _crop_segment(input_path, start, duration, region, sub, fps=fps, zoom=0.45)
            subclips.append(sub)

        if not subclips:
            render_center_crop(input_path, output_path)
            return

        if len(subclips) == 1:
            shutil.move(str(subclips[0]), str(output_path))
            return

        concat_file = Path(tmp) / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{s.as_posix()}'" for s in subclips) + "\n"
        )
        result = run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            *video_encode_args(),
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ], timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr[-500:].decode('utf-8', errors='replace')}")


def _get_video_info(input_path: Path) -> tuple[float, float]:
    result = run_ffmpeg([
        "-i", str(input_path),
        "-f", "null", "-",
    ], timeout=30)
    fps = 30.0
    duration = 0.0
    stderr = result.stderr
    import re
    for line in stderr.splitlines():
        m = re.search(r"(\d+(?:\.\d+)?) fps", line)
        if m:
            fps = float(m.group(1))
        m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", line)
        if m:
            duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return fps, duration


def _crop_segment(
    input_path: Path, start: float, duration: float, region, output_path: Path,
    fps: float = 30.0, zoom: float = 0.0,
):
    crop_part = f"crop={region.w}:{region.h}:{region.x}:{region.y}"
    if zoom > 0.01:
        # Push-in: upscale dulu biar tajam, zoompan center (tanpa pan â†’ mulus),
        # naik pelan 1.0 â†’ 1+zoom selama durasi segmen.
        rate = zoom / max(1.0, duration * fps)
        max_z = 1 + zoom
        filter_complex = (
            f"{crop_part},"
            f"scale=2160:3840:force_original_aspect_ratio=increase,"
            f"crop=2160:3840,"
            f"zoompan=z='min(1+{rate}*on,{max_z})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps={fps},"
            f"format=yuv420p"
        )
    else:
        filter_complex = (
            f"{crop_part},"
            f"scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
        )
    result = run_ffmpeg([
        "-ss", str(start),
        "-i", str(input_path),
        "-t", str(duration),
        "-vf", filter_complex,
        *video_encode_args(),
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ], timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg crop segment failed: {result.stderr[-500:].decode('utf-8', errors='replace')}")
