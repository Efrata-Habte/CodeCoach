"""Metrics: precision / recall / F1 (macro = every class counts equally) and confusion matrix.

(Model size and CPU latency are added in the distillation step.)
"""
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from codecoach.misconceptions import LABELS


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
