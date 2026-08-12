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

SMOOTH_ALPHA = 0.12    # EMA posisi kamera (lebih lambat = makin buttery)
TARGET_ALPHA = 0.35    # EMA box target (buang noise deteksi per-frame)
DEADBAND = 0.006       # fraksi frame: target geser di bawah ini → kamera DIAM
CONF_MIN = 0.35        # box di bawah confidence ini diabaikan
HOLD_SEC = 0.5         # tahan posisi kamera berapa detik kalau track hilang
HEAD_BIAS = 0.32       # target vertikal: 32% dari atas box (framing kepala)
ZOOM_FIT = 0.62        # tinggi orang ≈ 62% frame saat aktif (auto-zoom)
ZOOM_MIN = 1.1
ZOOM_MAX = 1.8
ZOOM_IDLE = 1.05       # zoom zona pas nggak ngomong
ZOOM_EASE = 0.06       # kecepatan zoom berubah per frame (ease halus)


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
         # Bug ffmpeg 8.1.1: NVENC + rawvideo bgr24 → pix_fmt gbrp (plane
         # GBR ke-swap) yang bikin Chrome render hijau. Paksa yuv420p +
         # tag smpte170m (BT.601) biar player decode benar.
         "-vf", "format=yuv420p",
         "-colorspace", "smpte170m", "-color_primaries", "smpte170m", "-color_trc", "smpte170m",
         "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-an",
         str(output_path)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )

    cx, cy = w / 2, h / 2
    t_cx, t_cy = w / 2, h / 2   # target halus (EMA kedua)
    zoom = ZOOM_IDLE
    db_x = w * DEADBAND
    db_y = h * DEADBAND
    hold_left = 0
    hold_frames = int(HOLD_SEC * fps)
    idx = 0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    while True:
        ret, frame = cap.read()
        if not ret:
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
                by = box[2] + (box[4] - box[2]) * HEAD_BIAS
                # EMA kedua: target box sendiri dihaluskan dulu (buang jitter deteksi)
                t_cx += (bx - t_cx) * TARGET_ALPHA
                t_cy += (by - t_cy) * TARGET_ALPHA
                # Deadband: target geser dikit → kamera DIAM (kill micro-jitter)
                dx = t_cx - cx
                dy = t_cy - cy
                if abs(dx) > db_x:
                    cx += dx * SMOOTH_ALPHA
                if abs(dy) > db_y:
                    cy += dy * SMOOTH_ALPHA
                # Auto-zoom dari ukuran box: orang pas ~62% tinggi frame
                box_h = max(1.0, box[4] - box[2])
                target_zoom = max(ZOOM_MIN, min(ZOOM_MAX, (h * ZOOM_FIT) / box_h))
                hold_left = hold_frames
            else:
                # Track hilang sesaat → TAHAN posisi (jangan drift langsung)
                if hold_left > 0:
                    hold_left -= 1
                else:
                    cx += (w / 2 - cx) * 0.02
                    cy += (h / 2 - cy) * 0.02
                    target_zoom = ZOOM_IDLE
        else:
            target_zoom = ZOOM_IDLE

        if target_zoom is not None:
            zoom += (target_zoom - zoom) * ZOOM_EASE

        crop_w = (w / zoom)
        crop_h = crop_w * (target_h / target_w)
        if crop_h > h:
            crop_h = h
            crop_w = crop_h * (target_w / target_h)
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
    if proc.returncode != 0:
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
