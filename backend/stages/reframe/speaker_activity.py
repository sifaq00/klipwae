from math import dist
from pathlib import Path

import cv2
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode
from mediapipe.tasks.python.vision.core.image import Image, ImageFormat

from stages.reframe._models import get_face_landmarker_path

UPPER_LIP = 13
LOWER_LIP = 14
LEFT_MOUTH = 61
RIGHT_MOUTH = 291


def compute_speaker_activity(
    video_path: Path, fps: float, duration: float
) -> list[tuple[float, float, str]]:
    SAMPLE_INTERVAL = 3
    WINDOW_SEC = 0.3
    MAR_DIFF_MARGIN = 0.03

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    opts = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(get_face_landmarker_path())),
        running_mode=RunningMode.IMAGE,
        num_faces=2,
        min_face_detection_confidence=0.5,
    )

    frame_idx = 0
    window_data: list[dict] = []
    current_window: list[dict] = []

    with FaceLandmarker.create_from_options(opts) as landmarker:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % SAMPLE_INTERVAL != 0:
                frame_idx += 1
                continue

            ts = frame_idx / fps
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image(image_format=ImageFormat.SRGB, data=rgb)
            result = landmarker.detect(img)
            h, w = frame.shape[:2]

            faces = {}
            if result.face_landmarks:
                for fl in result.face_landmarks:
                    cx = np.mean([p.x * w for p in fl])
                    side = "left" if cx < w / 2 else "right"
                    mar = _calc_mar(fl, w, h)
                    faces[side] = mar

            current_window.append({"ts": ts, "faces": faces})

            if ts >= (len(window_data) + 1) * WINDOW_SEC:
                window_data.append(_resolve_window(current_window, MAR_DIFF_MARGIN))
                current_window = []

            frame_idx += 1

    cap.release()

    if current_window:
        window_data.append(_resolve_window(current_window, MAR_DIFF_MARGIN))

    return [
        (i * WINDOW_SEC, min((i + 1) * WINDOW_SEC, duration), entry["side"])
        for i, entry in enumerate(window_data)
    ]


def _calc_mar(face_landmarks, w: int, h: int) -> float:
    p13 = (face_landmarks[UPPER_LIP].x * w, face_landmarks[UPPER_LIP].y * h)
    p14 = (face_landmarks[LOWER_LIP].x * w, face_landmarks[LOWER_LIP].y * h)
    p61 = (face_landmarks[LEFT_MOUTH].x * w, face_landmarks[LEFT_MOUTH].y * h)
    p291 = (face_landmarks[RIGHT_MOUTH].x * w, face_landmarks[RIGHT_MOUTH].y * h)
    mouth_open = dist(p13, p14)
    mouth_width = dist(p61, p291)
    return mouth_open / mouth_width if mouth_width > 0 else 0.0


def _resolve_window(frames: list[dict], margin: float) -> dict:
    left_mar = [f["faces"]["left"] for f in frames if "left" in f["faces"]]
    right_mar = [f["faces"]["right"] for f in frames if "right" in f["faces"]]
    left_avg = np.mean(left_mar) if left_mar else 0.0
    right_avg = np.mean(right_mar) if right_mar else 0.0
    diff = left_avg - right_avg
    if abs(diff) < margin:
        return {"side": "previous"}
    return {"side": "left" if diff > 0 else "right"}
