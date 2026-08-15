"""Tracking orang per-frame pakai YOLO11n + ByteTrack (CUDA).

Optimasi (ponytail: terukur via benchmark — track 52s/klip vs render 11s):
- Subsample: inference YOLO tiap `step` frame, sisanya carry-forward box
  terakhir. Kamera punya EMA + deadband yang sudah membuang jitter deteksi,
  jadi hasil visual setara.
- Cache: hasil tracking ditulis ke data/tracks/ supaya re-render / A/B
  tuning parameter kamera tidak nge-track ulang.
"""
import json
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_model = None
TRACK_STEP = 3
TRACK_IMGSZ = 320  # YOLO input 320: 0 frame-miss vs 640, ~2.3x lebih cepat
CACHE_DIR = Path("data/tracks")


def get_tracker():
    global _model
    if _model is None:
        from ultralytics import YOLO
        _model = YOLO("yolo11n.pt")
    return _model


def _cache_path(video_path: Path, step: int, imgsz: int) -> Path:
    return CACHE_DIR / f"{video_path.stem}_s{step}_i{imgsz}.json"


def _extract_boxes(result) -> list:
    """Ambil (track_id, x1, y1, x2, y2, conf) dari Results YOLO."""
    boxes = []
    if result.boxes is not None and result.boxes.id is not None:
        ids = result.boxes.id.int().tolist()
        for bid, xyxy, conf in zip(ids, result.boxes.xyxy.tolist(), result.boxes.conf.tolist()):
            boxes.append((int(bid), *[float(v) for v in xyxy], float(conf)))
    return boxes


def _interpolate_boxes(boxes_a: list, boxes_b: list, t: float) -> list:
    """Linearly interpolate boxes with matching track IDs between two sampled frames."""
    if not boxes_b or t <= 0.0:
        return boxes_a
    if not boxes_a or t >= 1.0:
        return boxes_b

    b_map = {b[0]: b for b in boxes_b}
    out = []
    for a in boxes_a:
        bid = a[0]
        if bid in b_map:
            b = b_map[bid]
            x1 = a[1] + (b[1] - a[1]) * t
            y1 = a[2] + (b[2] - a[2]) * t
            x2 = a[3] + (b[3] - a[3]) * t
            y2 = a[4] + (b[4] - a[4]) * t
            conf = a[5] + (b[5] - a[5]) * t
            out.append((bid, x1, y1, x2, y2, conf))
        else:
            out.append(a)
    return out


def track_persons(video_path: Path, device: str = "cuda", clip_no: str = "",
                  step: int = TRACK_STEP, use_cache: bool = True,
                  imgsz: int = TRACK_IMGSZ) -> list[dict] | None:
    """Track per-frame → [{"frame": i, "boxes": [(track_id, x1,y1,x2,y2, conf), ...]}].

    step>1 = inference tiap frame ke-N, frame antara diinterpolasi linier (lerp).
    imgsz=320 = 4x murah FLOPs YOLO tanpa menambah frame-miss (terukur).
    Hasil di-cache (key: nama file + ukuran + step + imgsz) — A/B tuning
    parameter kamera tidak nge-track ulang. Gagal → None (stage fallback).
    """
    try:
        cache = _cache_path(video_path, step, imgsz)
        if use_cache and cache.exists():
            data = json.loads(cache.read_text(encoding="utf-8"))
            st = video_path.stat()
            if (data.get("size") == st.st_size and data.get("mtime") == st.st_mtime
                    and data.get("step") == step):
                return data["frames"]

        model = get_tracker()
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Phase 1: baca cepat semua frame, simpan hanya frame ke-`step`.
        sampled = []
        i = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if i % step == 0:
                sampled.append(frame)
            i += 1
        cap.release()
        if not sampled:
            return []

        # Phase 2: track semua frame tersampling dalam CHUNK 32-frame.
        # persist=True → ByteTrack nyambungin ID antar chunk (state model
        # bertahan antar call). Chunking: 200 frame 1080p ≈ 1.2GB di RAM —
        # diproses 32-frame (~200MB) biar gak OOM di klip panjang.
        sampled_boxes = []
        TRACK_CHUNK = 32
        for k in range(0, len(sampled), TRACK_CHUNK):
            res = model.track(sampled[k:k + TRACK_CHUNK], persist=True, device=device,
                              conf=0.3, imgsz=imgsz, verbose=False, save=False)
            sampled_boxes.extend([_extract_boxes(r) for r in res])
        del sampled  # bebaskan RAM segera

        # Phase 3: expand dengan interpolasi linier antar frame sampel.
        out = []
        prefix = f"reframe track {clip_no} " if clip_no else "reframe track "
        num_samples = len(sampled_boxes)

        for idx in range(i):
            sample_idx = idx // step
            if sample_idx >= num_samples - 1:
                frame_boxes = sampled_boxes[-1] if sampled_boxes else []
            else:
                t = (idx % step) / float(step)
                frame_boxes = _interpolate_boxes(sampled_boxes[sample_idx], sampled_boxes[sample_idx + 1], t)
            out.append({"frame": idx, "boxes": frame_boxes})
            # progres per ~10% — biar bar reframe gerak realtime
            if total and (idx % max(1, total // 10) == 0):
                print(f"    {prefix}{idx / total * 100:.0f}%")

        if use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({
                "size": video_path.stat().st_size,
                "mtime": video_path.stat().st_mtime,
                "step": step,
                "imgsz": imgsz,
                "frames": out,
            }, ensure_ascii=False), encoding="utf-8")
        return out
    except Exception as e:
        logger.warning("yolo_track_failed", error=str(e))
        return None


def assign_zones(boxes_by_frame, n_zones: int = 2) -> dict[int, int]:
    """Cluster track ID ke zona (kiri/kanan) berdasarkan mean x-center."""
    track_xs: dict[int, list[float]] = {}
    for f in boxes_by_frame:
        for bid, x1, y1, x2, y2, conf in f["boxes"]:
            track_xs.setdefault(bid, []).append((x1 + x2) / 2)
    if not track_xs:
        return {}
    means = sorted((sum(v) / len(v), bid) for bid, v in track_xs.items())
    n = len(means)
    zone_map = {}
    for i, (_, bid) in enumerate(means):
        zone = min(i * n_zones // n, n_zones - 1)
        zone_map[bid] = zone
    return zone_map


def largest_box_in_zone(boxes_by_frame, frame_idx: int, zone: int, zone_map: dict,
                        conf_min: float = 0.35) -> list | None:
    """Box terbesar (conf >= conf_min) dari track di zona tertentu pada frame idx."""
    if frame_idx >= len(boxes_by_frame):
        return None
    best = None
    best_area = 0
    for bid, x1, y1, x2, y2, conf in boxes_by_frame[frame_idx]["boxes"]:
        if zone_map.get(bid) != zone or conf < conf_min:
            continue
        area = (x2 - x1) * (y2 - y1)
        if area > best_area:
            best_area = area
            best = (bid, x1, y1, x2, y2, conf)
    return best


def largest_box_any(boxes_by_frame, frame_idx: int, conf_min: float = 0.35) -> list | None:
    """Box terbesar (conf >= conf_min) di frame — buat single_shot follow."""
    if frame_idx >= len(boxes_by_frame):
        return None
    best = None
    best_area = 0
    for bid, x1, y1, x2, y2, conf in boxes_by_frame[frame_idx]["boxes"]:
        if conf < conf_min:
            continue
        area = (x2 - x1) * (y2 - y1)
        if area > best_area:
            best_area = area
            best = (bid, x1, y1, x2, y2, conf)
    return best