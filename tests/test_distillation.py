"""Distillation loss, student training and the size/latency measurements."""
import numpy as np
import torch
import torch.nn.functional as F

from codecoach.distillation import build_student, distillation_loss, train_student
from codecoach.evaluation import latency_ms, model_size_kb, n_params


def _logits(seed: int = 0, n: int = 8):
    g = torch.Generator().manual_seed(seed)
    return torch.randn(n, 5, generator=g), torch.randn(n, 5, generator=g), torch.randint(0, 5, (n,), generator=g)


def test_alpha_one_is_plain_cross_entropy_even_with_a_teacher() -> None:
    s, t, y = _logits()
    assert torch.allclose(distillation_loss(s, t, y, T=3.0, alpha=1.0), F.cross_entropy(s, y))
    assert torch.allclose(distillation_loss(s, None, y, T=3.0, alpha=0.3), F.cross_entropy(s, y))  # no teacher = CE


def test_alpha_zero_with_identical_student_and_teacher_is_zero() -> None:
    s, _, y = _logits()
    assert distillation_loss(s, s.clone(), y, T=2.0, alpha=0.0).item() < 1e-6  # KL(p || p) = 0


def test_loss_is_the_formula_from_the_slides() -> None:
    s, t, y = _logits(1)
    T, a = 4.0, 0.3
    kl = F.kl_div(F.log_softmax(s / T, 1), F.softmax(t / T, 1), reduction="batchmean") * T * T
    expected = a * F.cross_entropy(s, y) + (1 - a) * kl
    assert torch.allclose(distillation_loss(s, t, y, T, a), expected)
    assert kl.item() >= 0


def test_student_shape_and_size_are_much_smaller_than_a_teacher() -> None:
    student = build_student(800, 16)
    assert student(torch.zeros(3, 800)).shape == (3, 5)
    assert n_params(student) == 800 * 16 + 16 + 16 * 5 + 5
    assert model_size_kb(student) < model_size_kb(torch.nn.Sequential(torch.nn.Linear(800, 256), torch.nn.Linear(256, 5)))


def test_training_lowers_the_loss_and_reports_every_epoch() -> None:
    rng = np.random.default_rng(0)
    y = rng.integers(0, 5, 60)
    X = (np.eye(5)[y] + rng.normal(0, 0.1, (60, 5))).astype(np.float32)  # easy, learnable data
    seen = []
    model, hist = train_student(X, y, None, 1.0, 1.0, hidden=8, epochs=25, lr=1e-2, seed=0,
                                on_epoch=lambda e, loss: seen.append(e))
    assert len(hist) == 25 and hist[-1] < hist[0] and seen == list(range(25))
    assert (model(torch.tensor(X)).argmax(1).numpy() == y).mean() > 0.9


def test_training_is_reproducible_for_a_seed() -> None:
    X = np.random.default_rng(1).normal(size=(40, 6)).astype(np.float32)
    y = np.random.default_rng(2).integers(0, 5, 40)
    a = train_student(X, y, None, 1.0, 1.0, hidden=4, epochs=5, lr=1e-2, seed=3)[1]
    b = train_student(X, y, None, 1.0, 1.0, hidden=4, epochs=5, lr=1e-2, seed=3)[1]
    assert a == b


def test_latency_is_a_positive_median_of_single_sample_passes() -> None:
    ms = latency_ms(build_student(800, 16), np.zeros(800, dtype=np.float32), runs=30, warmup=5)
    assert 0 < ms < 50
