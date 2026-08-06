"""Device and dtype selection for the local transformers backend.

Split out of ``local_transformers_backend`` to keep that module within the size
budget. Both policies here depend only on the hardware, never on the
checkpoint, so they stand alone.
"""

from __future__ import annotations

import torch

__all__ = ["pick_default_dtype", "select_default_device"]


def select_default_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def pick_default_dtype(device: str) -> torch.dtype:
    """Half precision on an accelerator, but never float16.

    A model trained in bfloat16 keeps activations far outside float16's
    range, so loading it as float16 overflows to inf and the first sampling
    step dies on a probability tensor full of nan. Measured on gemma-3-4b:
    float16 logits come back nan, bfloat16 come back finite. bfloat16 has
    the same exponent range as float32, so it costs a little precision and
    no range, which is the trade this wants.
    """
    if device == "cpu":
        return torch.float32
    return torch.bfloat16
