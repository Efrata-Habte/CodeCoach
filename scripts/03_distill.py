"""Script 03: distil the teachers into a tiny student. Usage: python scripts/03_distill.py [--quick]

For each of 3 seeds, on the SAME examples (labeled seed + pool items the verifier confirmed) and the SAME budget:
  (1) hard-label student            alpha = 1 (no distillation)
  (2) student distilled from the v000 teacher
  (3) student distilled from the best evolved teacher
(T, alpha) for (2) and (3) is chosen on dev. The synthetic `test` split is only REPORTED, never used to choose.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config, get_config
from codecoach.archive import Archive, import_source
from codecoach.distillation import predict_labels, shared_examples, teacher_logits, train_student
from codecoach.evaluation import classification_report, latency_ms, model_size_kb, n_params
from codecoach.generator import Splits, load_splits
from codecoach.misconceptions import LABELS
from codecoach.self_training import self_train
from codecoach.utils import ROOT

MODELS = ["teacher_v000", "teacher_best", "student_hard", "student_distilled_v000", "student_distilled_best"]


def metrics_row(model, x_sample: np.ndarray, dev_pred: list[str], test_pred: list[str], splits: Splits, cfg: Config) -> dict:
    """Quality (dev + test), size and speed of one model."""
    dev = classification_report([s.label for s in splits.dev], dev_pred)
    test = classification_report([s.label for s in splits.test], test_pred)
    return {"dev_macro_f1": dev["macro_f1"], "test_macro_precision": test["macro_precision"],
            "test_macro_recall": test["macro_recall"], "test_macro_f1": test["macro_f1"],
            "test_per_class_f1": test["per_class_f1"], "params": n_params(model), "size_kb": model_size_kb(model),
            "latency_ms": latency_ms(model, x_sample, cfg.latency_runs)}


def run_seed(seed: int, cfg: Config, splits: Splits, verdicts: dict, pipes: dict, save_dir: Path | None) -> dict:
    """All five models for one seed."""
    t0, tb = (self_train(pipes[k], splits, cfg, seed, verdicts).teacher for k in ("v000", "best"))
    codes, labels = shared_examples(tb, splits, verdicts)
    X, y = tb.featurizer.transform(codes), np.array([LABELS.index(lab) for lab in labels])
    dev_codes, test_codes = [s.code for s in splits.dev], [s.code for s in splits.test]
    Xdev, Xtest = tb.featurizer.transform(dev_codes), tb.featurizer.transform(test_codes)  # students read BEST's features
    rows: dict = {"n_train_examples": len(codes)}
    for name, t in (("teacher_v000", t0), ("teacher_best", tb)):
        rows[name] = metrics_row(t.model, t.featurizer.transform(dev_codes[:1])[0], t.predict(dev_codes)[0],
                                 t.predict(test_codes)[0], splits, cfg)
    args = (X, y)
    kw = dict(hidden=cfg.student_hidden, epochs=cfg.student_epochs, lr=cfg.student_lr, seed=seed)
    runs = {"student_hard": [(train_student(*args, None, 1.0, 1.0, **kw), (None, 1.0))]}  # alpha=1: plain cross-entropy
    for name, teacher in (("student_distilled_v000", t0), ("student_distilled_best", tb)):
        tl = teacher_logits(teacher, codes)
        runs[name] = [(train_student(*args, tl, T, a, **kw), (T, a)) for T in cfg.T_grid for a in cfg.alpha_grid]
    curves = {}
    for name, candidates in runs.items():  # choose (T, alpha) by DEV macro-F1 only
        dev_f1 = lambda c: classification_report([s.label for s in splits.dev], predict_labels(c[0][0], Xdev))["macro_f1"]  # noqa: E731
        (model, history), (T, a) = max(candidates, key=dev_f1)
        rows[name] = metrics_row(model, Xdev[0], predict_labels(model, Xdev), predict_labels(model, Xtest), splits, cfg)
        rows[name].update(T=T, alpha=a)
        curves[name] = history
        if save_dir and seed == cfg.distill_seeds[0] and name != "student_distilled_v000":
            torch.save({"state_dict": model.state_dict(), "hidden": cfg.student_hidden, "tfidf": tb.featurizer.tfidf},
                       save_dir / f"{name}.pt")
    rows["curves"] = curves
    return rows


def summarize(per_seed: dict) -> dict:
    """Mean and std over seeds for every number of every model."""
    out = {}
    for name in MODELS:
        out[name] = {}
        for key in ("dev_macro_f1", "test_macro_precision", "test_macro_recall", "test_macro_f1", "params", "size_kb", "latency_ms"):
            vals = [r[name][key] for r in per_seed.values()]
            out[name][key] = {"mean": float(np.mean(vals)), "std": float(np.std(vals))}
    return out


def write_tables(summary: dict, results: Path) -> None:
    """results_table.csv / .md (one row per model; mean +- std over seeds)."""
    head = ["model", "test_macro_precision", "test_macro_recall", "test_macro_f1", "params", "size_kb", "latency_ms"]
    fmt = lambda s, k: f"{s[k]['mean']:.0f}" if k == "params" else f"{s[k]['mean']:.3f} +- {s[k]['std']:.3f}"  # noqa: E731
    rows = [[m] + [fmt(summary[m], k) for k in head[1:]] for m in MODELS]
    (results / "results_table.csv").write_text("\n".join(",".join(r) for r in [head] + rows), encoding="utf-8")
    md = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]
    (results / "results_table.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    cfg, data, results = get_config(args.quick), ROOT / "data" / "generated", ROOT / "results"
    archive = Archive()
    if not archive.versions:
        sys.exit("No archive yet: run scripts/02_evolve.py first.")
    splits, verdicts = load_splits(data / "splits.json"), json.loads((data / "verdicts.json").read_text())
    best = max(archive.accepted(), key=lambda v: v.metrics["dev_macro_f1"])
    # Both pipelines already survived the static check and sandboxed evaluation, so importing them here is acceptable.
    pipes = {"v000": import_source(archive.source("v000"), "distill_v000"), "best": import_source(archive.source(best.id), "distill_best")}
    (results / "models").mkdir(parents=True, exist_ok=True)
    per_seed = {}
    for seed in cfg.distill_seeds:
        per_seed[str(seed)] = run_seed(seed, cfg, splits, verdicts, pipes, results / "models")
        print(f"seed {seed}: " + " | ".join(f"{m} {per_seed[str(seed)][m]['test_macro_f1']:.3f}" for m in MODELS))
    summary = summarize(per_seed)
    out = {"best_version": best.id, "seeds": list(cfg.distill_seeds), "per_seed": per_seed, "summary": summary}
    (results / "distillation.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    write_tables(summary, results)
    print((results / "results_table.md").read_text())


if __name__ == "__main__":
    main()
