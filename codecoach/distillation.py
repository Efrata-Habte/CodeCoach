"""Knowledge distillation: a tiny student learns from a bigger teacher's SOFT probabilities.

    L = alpha * CE(y, student) + (1 - alpha) * T^2 * KL( softmax(teacher/T) || softmax(student/T) )

Intuition: a hard label says only "this is WRONG_INDEX". The teacher's soft output also says "...and it
looks a bit like OFF_BY_ONE_RANGE", which tells the student how the classes relate (dark knowledge).
"""
from typing import Callable

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from codecoach.misconceptions import LABELS
from codecoach.teacher import Featurizer, Teacher
from codecoach.utils import set_seed
from codecoach.verifier import verdict_key


def distillation_loss(student_logits: torch.Tensor, teacher_logits: torch.Tensor | None, y: torch.Tensor,
                      T: float, alpha: float) -> torch.Tensor:
    """alpha = 1 means NO distillation (plain cross-entropy): that is the hard-label baseline."""
    ce = F.cross_entropy(student_logits, y)
    if teacher_logits is None:
        return ce
    # Temperature T softens both distributions; the KL gradient shrinks like 1/T^2, so multiply by T^2
    # to keep its size comparable to the CE term (Hinton et al. 2015).
    kl = F.kl_div(F.log_softmax(student_logits / T, dim=1), F.softmax(teacher_logits / T, dim=1),
                  reduction="batchmean") * T * T
    return alpha * ce + (1 - alpha) * kl


def teacher_logits(teacher: Teacher, codes: list[str]) -> torch.Tensor:
    """Raw teacher scores for `codes`. Teacher in eval mode + no_grad: it is a fixed source of targets."""
    teacher.model.eval()
    with torch.no_grad():
        return teacher.model(torch.tensor(teacher.featurizer.transform(codes)))


def build_student(input_dim: int, hidden: int) -> nn.Module:
    """The tiny student: input -> hidden (16) -> classes (5)."""
    return nn.Sequential(nn.Linear(input_dim, hidden), nn.ReLU(), nn.Linear(hidden, len(LABELS)))


def train_student(X: np.ndarray, y: np.ndarray, t_logits: torch.Tensor | None, T: float, alpha: float,
                  hidden: int, epochs: int, lr: float, seed: int,
                  on_epoch: Callable[[int, float], None] | None = None) -> tuple[nn.Module, list[float]]:
    """Train a student with the distillation loss. Returns (model in eval mode, loss per epoch).

    `on_epoch(epoch, loss)` is called after every epoch: the live demo draws the loss curve from it.
    """
    set_seed(seed)
    model = build_student(X.shape[1], hidden)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    Xt, yt = torch.tensor(X), torch.tensor(y)
    history: list[float] = []
    model.train()
    for epoch in range(epochs):
        order, total = torch.randperm(len(Xt)), 0.0
        for i in range(0, len(Xt), 32):
            b = order[i:i + 32]
            opt.zero_grad()
            loss = distillation_loss(model(Xt[b]), None if t_logits is None else t_logits[b], yt[b], T, alpha)
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        history.append(total / len(Xt))
        if on_epoch:
            on_epoch(epoch, history[-1])
    return model.eval(), history


def shared_examples(teacher: Teacher, splits, verdicts: dict) -> tuple[list[str], list[str]]:
    """Seed (true labels) + pool items whose teacher diagnosis the VERIFIER confirmed (the labels the system has)."""
    codes, labels = [s.code for s in splits.seed], [s.label for s in splits.seed]
    preds, _ = teacher.predict([p.code for p in splits.pool])
    for item, lab in zip(splits.pool, preds):
        if verdicts.get(verdict_key(item.code, lab)) == "verified":
            codes.append(item.code)
            labels.append(lab)
    return codes, labels


def load_student(path, pipe) -> tuple[nn.Module, Featurizer]:
    """Rebuild a saved student (and the featurizer it reads) from results/models/*.pt."""
    ckpt = torch.load(path, weights_only=False)  # written by scripts/03_distill.py (contains a vectorizer)
    featurizer = Featurizer(pipe)
    featurizer.tfidf = ckpt["tfidf"]
    dim = len(featurizer.tfidf.vocabulary_) + len(pipe.extra_features("def f(v1):\n    return v1"))
    model = build_student(dim, ckpt["hidden"])
    model.load_state_dict(ckpt["state_dict"])
    return model.eval(), featurizer


def predict_labels(model: nn.Module, X: np.ndarray) -> list[str]:
    """Argmax class names for a feature matrix."""
    with torch.no_grad():
        return [LABELS[i] for i in model(torch.tensor(X)).argmax(1).tolist()]
