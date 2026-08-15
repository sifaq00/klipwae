"""Render 9:16 dengan kamera halus mengikuti pembicara aktif (YOLO boxes).

Loop frame per frame di Python → crop mengikuti box target (EMA smoothing) →
pipe ke ffmpeg NVENC. Audio di-mux dari source. Gaya Opus Clip: pan halus
+ zoom dalam saat bicara.
"""
import subprocess
from pathlib import Path

import cv2
import numpy as np

from utils.ffmpeg_helpers import run_ffmpeg

CONF_MIN = 0.35        # box di bawah confidence ini diabaikan


def _apply_soft_deadzone(displacement: float, deadband: float) -> float:
    """Calculate excess displacement beyond deadband.
    Starts smoothly from 0.0 at the deadband threshold."""
    if abs(displacement) <= deadband:
        return 0.0
    import math
    return math.copysign(abs(displacement) - deadband, displacement)


def _update_target_zoom(raw_zoom: float, active_target: float, deadband: float) -> float:
    """Apply hysteresis / deadband to target zoom to eliminate breathing effect."""
    if abs(raw_zoom - active_target) > deadband:
        return raw_zoom
    return active_target


def _clamp_headroom(cy: float, box_top: float, crop_h: float, min_headroom_ratio: float = 0.12) -> float:
    """Ensures that the top of the speaker's bounding box (`box_top`) has at least
    `crop_h * min_headroom_ratio` padding below the top of the crop frame (`cy - crop_h / 2`).
    If `box_top < (cy - crop_h / 2) + crop_h * min_headroom_ratio`, adjust `cy` upward
    (lower value in image coords) to preserve headroom and avoid cutting off the speaker's head/hair.
    """
    min_headroom = crop_h * min_headroom_ratio
    crop_top = cy - crop_h / 2.0
    if box_top < crop_top + min_headroom:
        cy = box_top - min_headroom + crop_h / 2.0
    return cy


def render_tracked(
    input_path: Path,
    camera_path: list[tuple[float, float, str]],
    boxes_by_frame: list[dict],
    zone_map: dict[int, int],
    fps: float,
    output_path: Path,
    target_w: int = 1080,
    target_h: int = 1920,
    clip_no: str = "",
    smooth_alpha: float = 0.08,
    target_alpha: float = 0.25,
    deadband: float = 0.012,
    hold_sec: float = 0.8,
    head_bias: float = 0.22,
    zoom_fit: float = 0.6,
    zoom_min: float = 1.15,
    zoom_max: float = 2.0,
    zoom_idle: float = 1.05,
    zoom_ease: float = 0.04,
    zoom_deadband: float = 0.05,
    min_headroom_ratio: float = 0.12,
):
    # zone_names: side string → zona int (dari assign_zones median)
    zone_names = {0: "left", 1: "right"}
    has_path = bool(camera_path)

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        return False
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{target_w}x{target_h}", "-r", str(fps),
         "-i", "-",
         # Bug ffmpeg 8.1.1: NVENC + rawvideo bgr24 ? pix_fmt gbrp (plane
         # GBR ke-swap) yang bikin Chrome render hijau. Paksa yuv420p +
         # tag smpte170m (BT.601) biar player decode benar.
         "-vf", "format=yuv420p",
         "-colorspace", "smpte170m", "-color_primaries", "smpte170m", "-color_trc", "smpte170m",
         "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-an",
         str(output_path)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    import runtime
    runtime.set_proc(proc)

    cx, cy = w / 2, h / 2
    t_cx, t_cy = w / 2, h / 2   # target halus (EMA kedua)
    zoom = zoom_idle
    active_target_zoom = zoom_idle
    db_x = w * deadband
    db_y = h * deadband
    hold_left = 0
    hold_frames = int(hold_sec * fps)
    idx = 0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if runtime.stop_requested():
            # killed saat render: abort tanpa menulis output setengah jadi
            proc.terminate()
            break
        t = idx / fps
        # progres render per ~10% — bar tetap gerak selama ffmpeg pipe
        if total_frames and idx % max(1, total_frames // 10) == 0:
            print(f"    reframe render {clip_no} {idx / total_frames * 100:.0f}%")
        seg = None
        if has_path:
            for s, e, side in camera_path:
                if s <= t < e:
                    seg = side
                    break
        # tanpa path (single_shot): selalu aktif, follow box terbesar
        target_zoom = None
        if not has_path or seg:
            box = None
            if has_path and seg:
                zone = next((z for z, n in zone_names.items() if n == seg), None)
                if zone is not None:
                    from stages.reframe.tracker import largest_box_in_zone
                    box = largest_box_in_zone(boxes_by_frame, idx, zone, zone_map)
            else:
                from stages.reframe.tracker import largest_box_any
                box = largest_box_any(boxes_by_frame, idx)

            if box:
                bx = (box[1] + box[3]) / 2
                by = box[2] + (box[4] - box[2]) * head_bias
                # EMA kedua: target box sendiri dihaluskan dulu (buang jitter deteksi)
                t_cx += (bx - t_cx) * target_alpha
                t_cy += (by - t_cy) * target_alpha
                # soft deadzone: kamera gerak mulus tanpa hentakan stop-and-go
                dx = t_cx - cx
                dy = t_cy - cy
                excess_x = _apply_soft_deadzone(dx, db_x)
                excess_y = _apply_soft_deadzone(dy, db_y)
                if excess_x != 0.0:
                    cx += excess_x * smooth_alpha
                if excess_y != 0.0:
                    cy += excess_y * smooth_alpha
                # Auto-zoom stabil dari ukuran box dengan filter hysteresis
                box_h = max(1.0, box[4] - box[2])
                raw_zoom = max(zoom_min, min(zoom_max, (h * zoom_fit) / box_h))
                active_target_zoom = _update_target_zoom(raw_zoom, active_target_zoom, zoom_deadband)
                target_zoom = active_target_zoom
                hold_left = hold_frames
            else:
                # Track hilang sesaat → TAHAN posisi (jangan drift langsung)
                if hold_left > 0:
                    hold_left -= 1
                else:
                    cx += (w / 2 - cx) * 0.02
                    cy += (h / 2 - cy) * 0.02
                    active_target_zoom = _update_target_zoom(zoom_idle, active_target_zoom, zoom_deadband)
                    target_zoom = active_target_zoom
        else:
            active_target_zoom = _update_target_zoom(zoom_idle, active_target_zoom, zoom_deadband)
            target_zoom = active_target_zoom

        if target_zoom is not None:
            zoom += (target_zoom - zoom) * zoom_ease

        crop_w = (w / zoom)
        crop_h = crop_w * (target_h / target_w)
        if crop_h > h:
            crop_h = h
            crop_w = crop_h * (target_w / target_h)

        if box:
            cy = _clamp_headroom(cy, box[2], crop_h, min_headroom_ratio=min_headroom_ratio)

        x1 = int(cx - crop_w / 2)
        y1 = int(cy - crop_h / 2)
        x1 = max(0, min(x1, w - int(crop_w)))
        y1 = max(0, min(y1, h - int(crop_h)))
        x2, y2 = x1 + int(crop_w), y1 + int(crop_h)

        cropped = frame[y1:y2, x1:x2]
        resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        proc.stdin.write(resized.tobytes())
        idx += 1

    proc.stdin.close()
    proc.wait()
    cap.release()
    runtime.clear_proc(proc)
    if proc.returncode != 0:
        # Abort karena kill juga sampai sini � jangan buat fallback/render lanjut
        return False

    # Mux audio dari source
    muxed = output_path.with_name(output_path.stem + "_mux.mp4")
    result = run_ffmpeg([
        "-i", str(output_path), "-i", str(input_path),
        "-map", "0:v", "-map", "1:a",
        "-c", "copy", "-shortest",
        str(muxed),
    ], timeout=120)
    if result.returncode == 0 and muxed.exists():
        muxed.replace(output_path)
    return True
