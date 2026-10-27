"""Turn code text into numbers, train a classifier on it, and predict. Shared by every level.

The pipeline module (evolvable/pipeline.py, or any archived version) supplies the CHOICES
(n-gram range, extra features, network shape, learning rate); this file supplies the MECHANICS.
"""
from dataclasses import dataclass
from types import ModuleType

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.feature_extraction.text import TfidfVectorizer

from codecoach.evaluation import classification_report
from codecoach.misconceptions import LABELS
from codecoach.utils import set_seed


class Featurizer:
    """Character n-gram TF-IDF of the code + the pipeline's hand-made structural features."""

    def __init__(self, pipe: ModuleType) -> None:
        self.pipe = pipe
        self.tfidf = TfidfVectorizer(analyzer="char", ngram_range=tuple(pipe.NGRAM_RANGE),
                                     max_features=int(pipe.MAX_FEATURES), sublinear_tf=True)

    def fit(self, codes: list[str]) -> "Featurizer":
        """Learn the n-gram vocabulary. Uses code only (no labels), so unlabeled pool code is fine."""
        self.tfidf.fit(codes)
        return self

    def transform(self, codes: list[str]) -> np.ndarray:
        """Feature matrix [n_samples, n_features] as float32."""
        text = self.tfidf.transform(codes).toarray()
        extra = np.array([self.pipe.extra_features(c) for c in codes], dtype=float).reshape(len(codes), -1)
        extra = np.sign(extra) * np.log1p(np.abs(extra))  # counts -> same scale as TF-IDF values
        return np.nan_to_num(np.hstack([text, extra])).astype(np.float32)


def train_model(pipe: ModuleType, X: np.ndarray, y: np.ndarray, seed: int) -> nn.Module:
    """Train a fresh network from scratch (mini-batch Adam + cross-entropy) and return it in eval mode."""
    set_seed(seed)
    model = pipe.build_teacher(X.shape[1], len(LABELS))
    opt = torch.optim.Adam(model.parameters(), lr=pipe.LR)
    Xt, yt = torch.tensor(X), torch.tensor(y)
    model.train()
    for _ in range(int(pipe.EPOCHS)):
        order = torch.randperm(len(Xt))
        for i in range(0, len(Xt), 32):
            batch = order[i:i + 32]
            opt.zero_grad()
            F.cross_entropy(model(Xt[batch]), yt[batch]).backward()
            opt.step()
    return model.eval()


@dataclass
class Teacher:
    """A trained model together with the featurizer it needs."""
    model: nn.Module
    featurizer: Featurizer

    def proba(self, codes: list[str]) -> np.ndarray:
        """Class probabilities, one row per code, columns in LABELS order."""
        with torch.no_grad():  # inference only: no gradients
            return F.softmax(self.model(torch.tensor(self.featurizer.transform(codes))), dim=1).numpy()

    def predict(self, codes: list[str]) -> tuple[list[str], list[float]]:
        """(predicted label, confidence) per code."""
        p = self.proba(codes)
        return [LABELS[i] for i in p.argmax(1)], p.max(1).tolist()

    def n_params(self) -> int:
        """Number of trainable parameters."""
        return sum(p.numel() for p in self.model.parameters())


def fit_teacher(pipe: ModuleType, featurizer: Featurizer, examples: list[tuple[str, str]], seed: int) -> Teacher:
    """Train a Teacher on (code, label) pairs."""
    X = featurizer.transform([c for c, _ in examples])
    y = np.array([LABELS.index(lab) for _, lab in examples])
    return Teacher(train_model(pipe, X, y, seed), featurizer)


def evaluate(teacher: Teacher, samples: list) -> dict:
    """Classification report of a teacher on labeled samples (dev, meta_dev, test...)."""
    preds, _ = teacher.predict([s.code for s in samples])
    return classification_report([s.label for s in samples], preds)
