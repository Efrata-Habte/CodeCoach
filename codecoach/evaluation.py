"""Metrics: precision / recall / F1 (macro = every class counts equally) and confusion matrix.

(Model size and CPU latency are added in the distillation step.)
"""
import io
import time

import numpy as np
import torch
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from codecoach.misconceptions import LABELS


def n_params(model: torch.nn.Module) -> int:
    """Number of trainable parameters."""
    return sum(p.numel() for p in model.parameters())


def model_size_kb(model: torch.nn.Module) -> float:
    """Size of the saved weights (state_dict) in KB: what you would actually ship."""
    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    return buf.getbuffer().nbytes / 1024


def latency_ms(model: torch.nn.Module, x: np.ndarray, runs: int = 200, warmup: int = 20) -> float:
    """Median CPU time of ONE forward pass on ONE sample, in ms (after warm-up; features precomputed).

    Median, not mean: a single slow call (OS hiccup) must not distort the number. Single thread (see set_seed).
    """
    model.eval()
    sample = torch.tensor(np.asarray(x, dtype=np.float32).reshape(1, -1))
    times = []
    with torch.no_grad():
        for i in range(warmup + runs):
            t0 = time.perf_counter()
            model(sample)
            if i >= warmup:
                times.append((time.perf_counter() - t0) * 1000)
    return float(np.median(times))


def classification_report(y_true: list[str], y_pred: list[str]) -> dict:
    """Macro P/R/F1, per-class F1 and confusion matrix (rows = true class, cols = predicted).

    Macro-F1 (not accuracy) because classes are imbalanced: a model that only ever says
    WRONG_INDEX would look good on accuracy but be useless to a learner with another mistake.
    """
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, labels=LABELS, average=None,
                                                  zero_division=0)
    return {
        "macro_precision": float(p.mean()), "macro_recall": float(r.mean()), "macro_f1": float(f1.mean()),
        "per_class_f1": {lab: float(v) for lab, v in zip(LABELS, f1)},
        "confusion": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
    }
