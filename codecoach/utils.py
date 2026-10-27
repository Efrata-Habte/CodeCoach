"""Small shared helpers (seeding, hashing, paths)."""
import hashlib
import random
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent  # project root, independent of cwd


def set_seed(seed: int) -> None:
    """Seed python, numpy and torch so every run is reproducible.

    Also pins torch to 1 thread: CPU latency numbers are far more stable that way.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)


def sha256_text(text: str) -> str:
    """Hash a string (used to cache sandbox runs and to detect tampering)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file's bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
