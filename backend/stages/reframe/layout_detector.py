from pathlib import Path
from typing import Literal

import cv2
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode
from mediapipe.tasks.python.vision.core.image import Image, ImageFormat

from stages.reframe._models import get_face_landmarker_path


def detect_layout(video_path: Path) -> Literal["split_screen", "single_shot"]:
    frames = _sample_frames(video_path)
    if not frames:
        return "single_shot"

    opts = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(get_face_landmarker_path())),
        running_mode=RunningMode.IMAGE,
        num_faces=6,
        min_face_detection_confidence=0.3,
    )
    with FaceLandmarker.create_from_options(opts) as landmarker:
        two_face = 0
        for frame in frames:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image(image_format=ImageFormat.SRGB, data=rgb)
            result = landmarker.detect(img)
            if result.face_landmarks and len(result.face_landmarks) >= 2:
                two_face += 1

    return "split_screen" if two_face / len(frames) >= 0.35 else "single_shot"


def _sample_frames(video_path: Path, n: int = 20) -> list:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []
    frame_step = max(1, total // n)
    frames = []
    for pos in range(0, total, frame_step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    return frames