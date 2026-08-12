import shutil
import tempfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve

MODELS_DIR = Path("models")

FACE_DETECTION_MODEL = "blaze_face_short_range.tflite"
FACE_DETECTION_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_detector/blaze_face_short_range/float16/latest/"
    "blaze_face_short_range.tflite"
)

FACE_LANDMARKER_MODEL = "face_landmarker.task"
FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/"
    "face_landmarker.task"
)


def get_model_path(name: str) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / name
    if dest.exists():
        return dest

    url = _MODEL_URLS.get(name)
    if url is None:
        raise ValueError(f"Unknown model: {name}")

    tmp = Path(tempfile.mkdtemp()) / f"{name}.download"
    try:
        urlretrieve(url, str(tmp))
        shutil.move(str(tmp), str(dest))
    except (URLError, OSError) as e:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"Failed to download {name}: {e}") from e

    return dest


def get_face_detection_path() -> Path:
    return get_model_path(FACE_DETECTION_MODEL)


def get_face_landmarker_path() -> Path:
    return get_model_path(FACE_LANDMARKER_MODEL)


_MODEL_URLS = {
    FACE_DETECTION_MODEL: FACE_DETECTION_URL,
    FACE_LANDMARKER_MODEL: FACE_LANDMARKER_URL,
}
