"""Script 04: the FINAL TEST on hand-written code. Usage: python scripts/04_final_test.py --final

Runs ONCE. Without --final it refuses (so no one can run it by accident while still tuning). It writes
results/FINAL_TEST_DONE; running again needs --again and prints a loud warning: once you have seen this
result and changed anything, the set is no longer a fair test. Nothing here is ever used to select a model.
"""
import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codecoach.archive import Archive, import_source
from codecoach.distillation import load_student, predict_labels
from codecoach.evaluation import classification_report
from codecoach.generator import normalize_names
from codecoach.problems import Problem
from codecoach.teacher import load_teacher
from codecoach.utils import ROOT
from codecoach.verifier import verify

DONE = ROOT / "results" / "FINAL_TEST_DONE"


def load_cases() -> list[dict]:
    """The hand-written cases (data/handwritten/cases.py)."""
    spec = importlib.util.spec_from_file_location("handwritten_cases", ROOT / "data" / "handwritten" / "cases.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CASES


def evaluate_models(predictors: dict[str, Callable[[list[str]], list[str]]], cases: list[dict]) -> dict:
    """Score each predictor on the cases: macro-F1, accuracy, per-class F1, and the 'useful diagnosis' rate
    (how often the verifier confirms that a repair of the PREDICTED class fixes the program)."""
    codes = [normalize_names(c["code"]) for c in cases]  # same normalization the models were trained with
    truth = [c["label"] for c in cases]
    out = {}
    for name, predict in predictors.items():
        preds = predict(codes)
        fixed = [verify(code, p, Problem(c["name"], code, "f", c["tests"])).accepted
                 for code, p, c in zip(codes, preds, cases)]
        report = classification_report(truth, preds)
        out[name] = {**report, "accuracy": sum(a == b for a, b in zip(preds, truth)) / len(cases),
                     "verified_fix_rate": sum(fixed) / len(cases), "predictions": preds}
    return out


def build_predictors(archive: Archive) -> dict[str, Callable[[list[str]], list[str]]]:
    """Teachers (v000, best) and, if script 03 saved them, the two seed-0 students."""
    best = max(archive.accepted(), key=lambda v: v.metrics["dev_macro_f1"])
    pipes = {i: import_source(archive.source(i), f"final_{i}") for i in ("v000", best.id)}
    preds = {}
    for label, vid in (("teacher_v000", "v000"), (f"teacher_best ({best.id})", best.id)):
        teacher = load_teacher(pipes[vid], archive.root / vid / "model.pt")
        preds[label] = lambda codes, t=teacher: t.predict(codes)[0]
    for name in ("student_hard", "student_distilled_best"):
        path = ROOT / "results" / "models" / f"{name}.pt"
        if path.exists():
            model, feat = load_student(path, pipes[best.id])
            preds[name] = lambda codes, m=model, f=feat: predict_labels(m, f.transform(codes))
    return preds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true", help="required: confirms you really want to spend the final test")
    ap.add_argument("--again", action="store_true", help="re-run after FINAL_TEST_DONE exists (invalidates it as a final test)")
    args = ap.parse_args()
    if not args.final:
        sys.exit("REFUSED: this is the final test on hand-written code and may be run ONCE.\n"
                 "Add your own cases to data/handwritten/cases.py first, then run:  python scripts/04_final_test.py --final")
    if DONE.exists():
        print("!" * 72 + f"\n!! THE FINAL TEST WAS ALREADY RUN ({DONE.read_text().strip()}).\n"
              "!! Running it again after seeing the results makes it a tuning set, not a final test.\n" + "!" * 72)
        if not args.again:
            sys.exit("Refusing to re-run. Pass --again only if you accept that it is no longer a fair final test.")
    archive = Archive()
    if not archive.versions:
        sys.exit("No archive yet: run scripts/02_evolve.py first.")
    cases = load_cases()
    results = evaluate_models(build_predictors(archive), cases)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "final_test.json").write_text(json.dumps({"n_cases": len(cases), "models": results}, indent=1), encoding="utf-8")
    DONE.write_text(time.strftime("run at %Y-%m-%d %H:%M:%S") + f" on {len(cases)} cases\n", encoding="utf-8")
    print(f"FINAL TEST on {len(cases)} hand-written cases")
    for name, r in results.items():
        print(f"{name:28s} macro-F1 {r['macro_f1']:.3f} | accuracy {r['accuracy']:.2f} | verified-fix rate {r['verified_fix_rate']:.2f}")


if __name__ == "__main__":
    main()
