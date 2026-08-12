"""Tracking orang per-frame pakai YOLO11n + ByteTrack (CUDA)."""
import cv2

_model = None


def get_tracker():
    global _model
    if _model is None:
        from ultralytics import YOLO
        _model = YOLO("yolo11n.pt")
    return _model


def track_persons(video_path, device: str = "cuda", clip_no: str = "") -> list[dict] | None:
    """Track per-frame → [{"frame": i, "boxes": [(track_id, x1,y1,x2,y2, conf), ...]}].

    Gagal (model rusak/GPU habis) → None, biar stage fallback ke crop biasa.
    """
    try:
        model = get_tracker()
        out = []
        total = None
        prefix = f"reframe track {clip_no} " if clip_no else "reframe track "
        for i, r in enumerate(model.track(
            str(video_path), persist=True, stream=True,
            device=device, conf=0.3, verbose=False, save=False,
        )):
            if total is None:
                import cv2 as _cv2
                cap = _cv2.VideoCapture(str(video_path))
                total = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
            # progres tracking per ~10% — biar bar reframe gerak realtime
            if total and (i % max(1, total // 10) == 0):
                print(f"    {prefix}{i / total * 100:.0f}%")
            boxes = []
            if r.boxes is not None and r.boxes.id is not None:
                ids = r.boxes.id.int().tolist()
                for bid, xyxy, conf in zip(ids, r.boxes.xyxy.tolist(), r.boxes.conf.tolist()):
                    boxes.append((int(bid), *[float(v) for v in xyxy], float(conf)))
            out.append({"frame": i, "boxes": boxes})
        return out
    except Exception as e:
        import structlog
        structlog.get_logger(__name__).warning("yolo_track_failed", error=str(e))
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
