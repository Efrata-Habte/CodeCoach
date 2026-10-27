"""Pipeline v0: THE FILE THE SYSTEM REWRITES (Level 1 target).

Everything the self-improvement search may change lives here: features, model shape, training
settings and how verified pseudo-labels are curated. The fixed library (codecoach/) reads these
names; the evaluator scores whatever this file says. Keep it short and readable.
"""
import random

import torch.nn as nn

from codecoach import feature_blocks as fb

# --- text features -----------------------------------------------------------
NGRAM_RANGE = (2, 4)      # character n-gram sizes read from the code
MAX_FEATURES = 4096       # vocabulary cap

# --- model & training --------------------------------------------------------
HIDDEN_SIZES = [256, 128]
DROPOUT = 0.2
LR = 1e-3
EPOCHS = 30

# --- Level 0 self-training ---------------------------------------------------
SELF_TRAIN_ROUNDS = 4     # at most this many pseudo-labeling rounds (also capped by config)
POOL_PER_ROUND = 300      # unlabeled programs diagnosed per round
MIN_DELTA = 0.005         # dev-F1 gain needed to accept a round (can only make the gate STRICTER)

# --- curation of verified pseudo-labels --------------------------------------
CURATION = "dedup_cap"    # one of: "none", "dedup_cap", "balance"
PER_CLASS_CAP = 30        # "dedup_cap": keep at most this many verified examples per class


def extra_features(code: str) -> list[float]:
    """Structural features appended to the n-gram vector (calls to whitelisted blocks only)."""
    return [fb.count_comparisons(code), fb.count_range_calls(code), fb.count_subscripts(code)]


def build_teacher(input_dim: int, n_classes: int) -> nn.Module:
    """MLP classifier: input -> hidden layers (ReLU + dropout) -> class scores."""
    layers, width = [], input_dim
    for size in HIDDEN_SIZES:
        layers += [nn.Linear(width, size), nn.ReLU(), nn.Dropout(DROPOUT)]
        width = size
    layers.append(nn.Linear(width, n_classes))
    return nn.Sequential(*layers)


def curate(verified_examples: list, rng: random.Random) -> list:
    """Choose which verified (code, label) pairs to train on.

    Why curate at all: verified examples are still skewed toward easy, common classes. Capping per
    class is a diversity guard against model collapse (the teacher teaching itself only what it
    already knows best).
    """
    examples = list(verified_examples)
    if CURATION == "none":
        return examples
    examples = list({code: (code, label) for code, label in examples}.values())  # drop duplicate programs
    by_class: dict[str, list] = {}
    for ex in examples:
        by_class.setdefault(ex[1], []).append(ex)
    cap = min(len(g) for g in by_class.values()) if CURATION == "balance" else PER_CLASS_CAP
    return [ex for group in by_class.values() for ex in rng.sample(group, min(len(group), cap))]
