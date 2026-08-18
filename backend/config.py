from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_api_key: str
    analyze_model: str = "gemini-flash-latest"
    analyze_model_fallback: str = "gemini-3.6-flash"
    worker_token: str = ""
    worker_queue: bool = False  # True: job baru masuk antrean worker (bukan runner lokal)
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "cuda"
    whisper_initial_prompt: str = ""
    max_concurrent_jobs: int = 2
    confidence_threshold: float = 0.6
    min_hold_sec: float = 1.2
    video_download_resolution: int = 720
    storage_retention_days: int = 14
    chunk_duration_min: int = 20
    chunk_overlap_min: int = 2
    clip_align_sentence: bool = True
    reframe_zoom_min: float = 1.15
    reframe_zoom_max: float = 2.0
    reframe_zoom_fit: float = 0.6
    reframe_head_bias: float = 0.22
    reframe_zoom_idle: float = 1.05
    reframe_zoom_ease: float = 0.04
    reframe_zoom_deadband: float = 0.05
    reframe_min_headroom_ratio: float = 0.12
    reframe_track_step: int = 3
    reframe_track_cache: bool = True
    reframe_track_imgsz: int = 320
    log_level: str = "INFO"
    hf_token: str | None = None

    @model_validator(mode="after")
    def validate_chunking(self):
        if self.chunk_overlap_min >= self.chunk_duration_min:
            raise ValueError("CHUNK_OVERLAP_MIN harus lebih kecil dari CHUNK_DURATION_MIN")
        return self

