import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_settings_defaults():
    """Default values without .env should still work for optional fields."""
    os.environ["GOOGLE_API_KEY"] = "test-key"
    try:
        from config import Settings
        s = Settings(_env_file=None)
        assert s.analyze_model == "gemini-flash-latest"
        assert s.whisper_model == "medium"
        assert s.max_concurrent_jobs == 2
        assert s.confidence_threshold == 0.6
        assert s.min_hold_sec == 1.2
        assert s.video_download_resolution == 720
        assert s.chunk_duration_min == 20
        assert s.chunk_overlap_min == 2
        print("OK test_settings_defaults")
    finally:
        del os.environ["GOOGLE_API_KEY"]


def test_settings_chunk_validation():
    """overlap >= duration should raise."""
    os.environ["GOOGLE_API_KEY"] = "test-key"
    os.environ["CHUNK_DURATION_MIN"] = "10"
    os.environ["CHUNK_OVERLAP_MIN"] = "15"
    try:
        from config import Settings
        try:
            Settings()
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "CHUNK_OVERLAP_MIN" in str(e)
        print("OK test_settings_chunk_validation")
    finally:
        del os.environ["GOOGLE_API_KEY"]
        del os.environ["CHUNK_DURATION_MIN"]
        del os.environ["CHUNK_OVERLAP_MIN"]


def test_settings_chunk_equal():
    """overlap == duration should also raise."""
    os.environ["GOOGLE_API_KEY"] = "test-key"
    os.environ["CHUNK_DURATION_MIN"] = "10"
    os.environ["CHUNK_OVERLAP_MIN"] = "10"
    try:
        from config import Settings
        try:
            Settings()
            assert False, "Should raise ValueError"
        except ValueError:
            pass
        print("OK test_settings_chunk_equal")
    finally:
        del os.environ["GOOGLE_API_KEY"]
        del os.environ["CHUNK_DURATION_MIN"]
        del os.environ["CHUNK_OVERLAP_MIN"]


def test_settings_custom_values():
    os.environ["GOOGLE_API_KEY"] = "test-key"
    os.environ["ANALYZE_MODEL"] = "gemini-2.5-pro"
    os.environ["WHISPER_MODEL"] = "large-v3"
    os.environ["WHISPER_DEVICE"] = "cuda"
    os.environ["MAX_CONCURRENT_JOBS"] = "4"
    os.environ["CONFIDENCE_THRESHOLD"] = "0.8"
    os.environ["LOG_LEVEL"] = "DEBUG"
    try:
        from config import Settings
        s = Settings()
        assert s.analyze_model == "gemini-2.5-pro"
        assert s.whisper_model == "large-v3"
        assert s.whisper_device == "cuda"
        assert s.max_concurrent_jobs == 4
        assert s.confidence_threshold == 0.8
        assert s.log_level == "DEBUG"
        print("OK test_settings_custom_values")
    finally:
        for key in ("GOOGLE_API_KEY", "ANALYZE_MODEL", "WHISPER_MODEL",
                     "WHISPER_DEVICE", "MAX_CONCURRENT_JOBS",
                     "CONFIDENCE_THRESHOLD", "LOG_LEVEL"):
            os.environ.pop(key, None)


if __name__ == "__main__":
    test_settings_defaults()
    test_settings_chunk_validation()
    test_settings_chunk_equal()
    test_settings_custom_values()
    print("\nAll config tests passed.")
