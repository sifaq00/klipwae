# STAGE modules di-import EKSPLISIT oleh pemakai pipeline (worker.py /
# orchestrator.run_pipeline) — TIDAK auto-import di sini. Server API mode
# (HF Spaces, requirements ringan) tak boleh menyeret faster-whisper /
# mediapipe / ultralytics / genai lewat package init.
