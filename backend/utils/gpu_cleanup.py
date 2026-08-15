import gc


def clean_gpu_memory() -> None:
    """Explicitly garbage collect and clear CUDA cache to prevent VRAM fragmentation."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass
