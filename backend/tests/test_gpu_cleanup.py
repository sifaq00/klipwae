import gc
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.gpu_cleanup import clean_gpu_memory


def test_clean_gpu_memory_runs_safely():
    # Calling directly should not crash in any environment (CPU or GPU)
    clean_gpu_memory()


def test_clean_gpu_memory_invokes_gc_and_cuda_when_available(monkeypatch):
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True

    with patch("gc.collect") as mock_gc:
        with patch.dict("sys.modules", {"torch": mock_torch}):
            clean_gpu_memory()
            mock_gc.assert_called_once()
            mock_torch.cuda.empty_cache.assert_called_once()
            mock_torch.cuda.ipc_collect.assert_called_once()


def test_clean_gpu_memory_handles_torch_unavailable(monkeypatch):
    with patch("gc.collect") as mock_gc:
        with patch.dict("sys.modules", {"torch": None}):
            clean_gpu_memory()
            mock_gc.assert_called_once()


def test_clean_gpu_memory_handles_cuda_not_available(monkeypatch):
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False

    with patch.dict("sys.modules", {"torch": mock_torch}):
        clean_gpu_memory()
        mock_torch.cuda.empty_cache.assert_not_called()
        mock_torch.cuda.ipc_collect.assert_not_called()


def test_clean_gpu_memory_suppresses_exceptions(monkeypatch):
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.side_effect = RuntimeError("CUDA driver error")

    with patch.dict("sys.modules", {"torch": mock_torch}):
        # Should not raise exception
        clean_gpu_memory()
