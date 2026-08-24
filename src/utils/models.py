import torch


def pick_device() -> tuple[torch.device, torch.dtype]:
    """Best available torch device plus the dtype that is safe on it."""
    if torch.cuda.is_available():
        return torch.device("cuda"), torch.bfloat16
    if torch.backends.mps.is_available():
        # MPS support for bfloat16 is partial; float32 is the safe choice.
        return torch.device("mps"), torch.float32
    return torch.device("cpu"), torch.float32
