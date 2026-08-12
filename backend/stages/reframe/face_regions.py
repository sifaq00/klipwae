from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode
from mediapipe.tasks.python.vision.core.image import Image, ImageFormat

from stages.reframe._models import get_face_landmarker_path


@dataclass
class FaceRegion:
    x: int
    y: int
    w: int
    h: int


def compute_face_regions(video_path: Path) -> dict[str, FaceRegion] | None:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if total <= 0:
        return None

    frame_step = max(1, total // 10)
    samples = []
    cap = cv2.VideoCapture(str(video_path))
    for pos in range(0, total, frame_step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if ret:
            samples.append(frame)
    cap.release()

    if not samples:
        return None

    opts = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(get_face_landmarker_path())),
        running_mode=RunningMode.IMAGE,
        num_faces=6,
        min_face_detection_confidence=0.3,
    )
    boxes = []
    with FaceLandmarker.create_from_options(opts) as landmarker:
        for frame in samples:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image(image_format=ImageFormat.SRGB, data=rgb)
            result = landmarker.detect(img)
            if not result.face_landmarks:
                continue
            for fl in result.face_landmarks:
                xs = [p.x * w for p in fl]
                ys = [p.y * h for p in fl]
                cx = np.mean(xs)
                boxes.append({
                    "side": "left" if cx < w / 2 else "right",
                    "x": int(min(xs)), "y": int(min(ys)),
                    "w": int(max(xs) - min(xs)), "h": int(max(ys) - min(ys)),
                })

    if not boxes:
        return None

    regions = {}
    for side in ("left", "right"):
        side_boxes = [b for b in boxes if b["side"] == side]
        if not side_boxes:
            continue
        x = min(b["x"] for b in side_boxes)
        y = min(b["y"] for b in side_boxes)
        x_max = max(b["x"] + b["w"] for b in side_boxes)
        y_max = max(b["y"] + b["h"] for b in side_boxes)
        margin_x = int((x_max - x) * 0.5)
        margin_y = int((y_max - y) * 0.5)
        regions[side] = FaceRegion(
            x=max(0, x - margin_x),
            y=max(0, y - margin_y),
            w=min(w - max(0, x - margin_x), (x_max - x) + 2 * margin_x),
            h=min(h - max(0, y - margin_y), (y_max - y) + 2 * margin_y),
        )

    return regions if len(regions) == 2 else None
