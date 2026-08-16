"""Render 9:16 dengan kamera halus mengikuti pembicara aktif (YOLO boxes).

Loop frame per frame di Python → crop mengikuti box target (EMA smoothing) →
pipe ke ffmpeg NVENC. Audio di-mux dari source. Gaya Opus Clip: pan halus
+ zoom dalam saat bicara.
"""
import subprocess
from pathlib import Path

import cv2
import numpy as np

from utils.ffmpeg_helpers import run_ffmpeg, video_encode_args

CONF_MIN = 0.35        # box di bawah confidence ini diabaikan


def _follow_target(cur: float, target: float, snap: bool, alpha: float = 0.25) -> float:
    """EMA target. Saat snap=True (boost switch aktif): langsung ke target —
    EMA target (0.25) jadi bottleneck kalau tak di-snap: kamera ngejar target
    yang melayang pelan, settle tetap ~1.3s walau camera alpha 0.5."""
    if snap:
        return target
    return cur + (target - cur) * alpha


def _segment_anchors(boxes_by_frame: list, zone_map: dict[int, int],
                     camera_path: list[tuple[float, float, str]], fps: float,
                     head_bias: float = 0.22, conf_min: float = 0.35) -> dict[tuple, tuple[float, float]]:
    """Anchor PER SEGMEN camera_path — bukan per klip. Orang bisa bergeser
    antar segmen (ganti posisi duduk); anchor global bikin orang off-center
    di sebagian klip. Dipakai box TERBESAR per frame (dominant speaker) →
    median, buang outlier."""
    import statistics
    # frame range per segmen
    seg_ranges: dict[int, tuple[int, int]] = {}
    for i, (s, e, _side) in enumerate(camera_path):
        seg_ranges[i] = (int(s * fps), max(int(s * fps), int(e * fps)))
    xs: dict[tuple, list[float]] = {}
    ys: dict[tuple, list[float]] = {}
    for i, (f0, f1) in seg_ranges.items():
        for fi in range(f0, min(f1, len(boxes_by_frame))):
            best = None
            best_area = 0.0
            for bid, x1, y1, x2, y2, conf in boxes_by_frame[fi]["boxes"]:
                zone = zone_map.get(bid)
                if zone is None or conf < conf_min:
                    continue
                area = (x2 - x1) * (y2 - y1)
                if area > best_area:
                    best_area = area
                    best = (zone, (x1 + x2) / 2, y1 + (y2 - y1) * head_bias)
            if best:
                zone, bx, by = best
                key = (zone, i)
                xs.setdefault(key, []).append(bx)
                ys.setdefault(key, []).append(by)
    anchors = {}
    for key in xs:
        if xs[key]:
            anchors[key] = (statistics.median(xs[key]), statistics.median(ys[key]))
    return anchors


def _zone_anchors(boxes_by_frame: list, zone_map: dict[int, int],
                  head_bias: float = 0.22, conf_min: float = 0.35) -> dict[int, tuple[float, float]]:
    """Anchor per zona: median (x-center, y+head_bias) SEMUA box track di zona
    itu. Orang podcast duduk di posisi tetap → median stabil, kamera terkunci
    di sini (mode no-pan, zoom-only). Kalau satu zona kosong → fallback ke
    center frame."""
    import statistics
    xs: dict[int, list[float]] = {}
    ys: dict[int, list[float]] = {}
    for f in boxes_by_frame:
        for bid, x1, y1, x2, y2, conf in f["boxes"]:
            zone = zone_map.get(bid)
            if zone is None or conf < conf_min:
                continue
            xs.setdefault(zone, []).append((x1 + x2) / 2)
            ys.setdefault(zone, []).append(y1 + (y2 - y1) * head_bias)
    anchors = {}
    for zone in sorted(set(zone_map.values())):
        if xs.get(zone):
            anchors[zone] = (statistics.median(xs[zone]), statistics.median(ys[zone]))
        else:
            anchors[zone] = (0.0, 0.0)  # fallback: dipenuhi caller dengan center frame
    return anchors


def _switch_alpha(prev_side, cur_side, boost_left, base, boost, boost_frames):
    """Alpha untuk frame ini. Saat side BERUBAH → boost (snap cepat, penonton
    langsung lihat speaker baru — glide EMA 0.5-1s terasa "kejar-kejaran" di
    klip multi-speaker). Setelah window boost habis → kembali ke base alpha
    (follow halus, buang jitter)."""
    if boost_left > 0:
        boost_left -= 1
        if boost_left > 0:
            return boost, boost_left
        return base, 0
    if prev_side is not None and cur_side is not None and cur_side != prev_side:
        return boost, boost_frames - 1
    return base, 0


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
         *video_encode_args(), "-an",
         str(output_path)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    import runtime
    runtime.set_proc(proc)

    cx, cy = w / 2, h / 2
    zoom = zoom_idle
    active_target_zoom = zoom_idle
    hold_left = 0
    hold_frames = int(hold_sec * fps)
    # MODE SNAP-FIXED-ZOOM: kamera terkunci di anchor zona (median posisi
    # orang), switch side → SNAP instan (bukan glide). Gerak orang TIDAK
    # diikuti (no-pan) — hanya zoom in/out dari ukuran box.
    if has_path:
        seg_anchors = _segment_anchors(boxes_by_frame, zone_map, camera_path, fps,
                                       head_bias=head_bias, conf_min=CONF_MIN)
    else:
        # single_shot: satu anchor global = median semua track
        all_bids: dict[int, int] = {}
        for f in boxes_by_frame:
            for bid, *_ in f["boxes"]:
                all_bids.setdefault(bid, 0)
        seg_anchors = {}
        fallback_anchor = _zone_anchors(boxes_by_frame, all_bids, head_bias=head_bias,
                                        conf_min=CONF_MIN).get(0)
    prev_side: str | None = None
    cur_seg_idx: int | None = None
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
            zone = None
            if has_path and seg:
                zone = next((z for z, n in zone_names.items() if n == seg), None)
                if zone is not None:
                    from stages.reframe.tracker import largest_box_in_zone
                    box = largest_box_in_zone(boxes_by_frame, idx, zone, zone_map)
            else:
                from stages.reframe.tracker import largest_box_any
                box = largest_box_any(boxes_by_frame, idx)

            if box:
                # SNAP-on-switch: ganti segmen (side berubah) → kamera
                # langsung center di anchor SEGMEN itu (tanpa glide).
                if has_path and seg is not None:
                    seg_idx = next((i for i, (s, e, _) in enumerate(camera_path) if s <= t < e), None)
                    if seg_idx != cur_seg_idx:
                        ax, ay = seg_anchors.get((zone, seg_idx), (w / 2, h / 2))
                        cx, cy = ax, ay
                        cur_seg_idx = seg_idx
                        prev_side = seg
                else:
                    # single_shot: snap sekali di frame pertama ada box
                    if prev_side is None:
                        ax, ay = fallback_anchor or (w / 2, h / 2)
                        cx, cy = ax, ay
                        prev_side = "locked"
                # Auto-zoom stabil dari ukuran box dengan filter hysteresis
                box_h = max(1.0, box[4] - box[2])
                raw_zoom = max(zoom_min, min(zoom_max, (h * zoom_fit) / box_h))
                active_target_zoom = _update_target_zoom(raw_zoom, active_target_zoom, zoom_deadband)
                target_zoom = active_target_zoom
                hold_left = hold_frames
            else:
                # Track hilang sesaat → TAHAN di anchor (no-pan), zoom balik
                # idle. Jangan drift ke center — mode ini kamera tak bergerak.
                if hold_left > 0:
                    hold_left -= 1
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
        # Abort karena kill juga sampai sini — jangan buat fallback/render lanjut
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
