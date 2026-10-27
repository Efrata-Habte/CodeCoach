"""Ablation: does the independent verifier matter? Same Level 0 loop, pseudo-labels chosen two ways.

  verifier   : a pseudo-label is kept only if a repair of the predicted class makes the hidden tests pass
  confidence : a pseudo-label is kept if the model's own confidence >= config.confidence_threshold (0.9)
Run on the baseline and the best evolved pipeline, several seeds. Precision uses the HIDDEN true labels and is
only reported (the loop never reads them). Rounds that were rolled back are excluded: only labels that really
entered a promoted teacher count.
"""
from dataclasses import replace
from types import ModuleType

from config import Config
from codecoach.generator import Splits
from codecoach.self_training import self_train
from codecoach.teacher import evaluate


def _precision(rounds: list[dict]) -> float | None:
    """Share of pseudo-labels (in accepted rounds) whose label equals the hidden true label."""
    used = [r for r in rounds if r["decision"] == "accepted" and r["precision"] is not None]
    total = sum(r["n_verified"] for r in used)
    return sum(r["precision"] * r["n_verified"] for r in used) / total if total else None


# mode -> (config changes, description). "confidence" is the specified 0.9 baseline; with a weak, under-confident
# teacher it selects NOTHING (max confidence of the seed-only teacher on the pool is 0.72), so a looser 0.5 baseline
# is added. 0.5 was chosen AFTER seeing that 0.9 is empty: it admits a comparable number of pseudo-labels.
MODES = {"verifier": ({}, "independent verifier (default)"),
         "confidence": ({"ablate_verifier": True, "confidence_threshold": 0.9}, "model confidence >= 0.9"),
         "confidence_loose": ({"ablate_verifier": True, "confidence_threshold": 0.5}, "model confidence >= 0.5")}


def run_verifier_ablation(cfg: Config, pipes: dict[str, ModuleType], splits: Splits, verdicts: dict,
                          seeds: tuple = (0, 1, 2)) -> dict:
    """{"seeds": [...], "modes": {mode: description}, mode: [row...]}: one row per (pipeline, seed)."""
    out: dict = {"seeds": list(seeds), "modes": {m: d for m, (_, d) in MODES.items()}, **{m: [] for m in MODES}}
    for mode, (changes, _) in MODES.items():
        mode_cfg = replace(cfg, **changes)
        for name, pipe in pipes.items():
            for seed in seeds:
                res = self_train(pipe, splits, mode_cfg, seed, verdicts)
                out[mode].append({"pipeline": name, "seed": seed, "pseudo_label_precision": _precision(res.rounds),
                                  "n_pseudo": res.n_verified, "dev_f1": res.final_dev["macro_f1"],
                                  "meta_dev_f1": evaluate(res.teacher, splits.meta_dev)["macro_f1"]})
    return out
