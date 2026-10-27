"""Script 02: Level 1 - the system edits ITS OWN pipeline source. Usage: python scripts/02_evolve.py [--quick]

Loop: pick a parent from the archive -> the improver proposes an edited child source -> static safety
check -> the FIXED evaluator scores it -> accept only if dev F1 beats the parent by min_delta.
Accepted AND rejected versions are archived (rejected ones flagged) for the UI and failure analysis.
(Level 2 - the improver editing itself - is added in the next step.)
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config, get_config
from codecoach import safety
from codecoach.archive import Archive, Version, import_source
from codecoach.code_editor import normalize_source
from codecoach.evaluator import EvalOutcome, evaluate_pipeline
from codecoach.utils import ROOT


def record(archive: Archive, outcome: EvalOutcome | None, child: str, parent_id: str | None, edit: str,
           gen: int, accepted: bool, reason: str, proposer: str = "rule_based") -> Version:
    """Store one version (accepted or rejected) in the archive."""
    v = Version(archive.next_id("pipeline"), "pipeline", parent_id, proposer, edit, accepted, reason, gen,
                outcome.metrics if outcome and outcome.ok else None)
    archive.add(v, child, outcome.model_path if outcome else None)
    return v


def run_level1(cfg: Config, archive: Archive, improver, evaluate_fn: Callable[[str], EvalOutcome],
               rng: random.Random, log: Callable[[str], None] = print) -> None:
    """Run up to cfg.generations pipeline edits. `evaluate_fn` is injected so tests can fake it."""
    seen = {normalize_source(archive.source(v.id)) for v in archive.versions if v.kind == "pipeline"}
    best = max(v.metrics["dev_macro_f1"] for v in archive.accepted())
    stale = 0  # generations since the best score last improved
    for gen in range(1, cfg.generations + 1):
        pool = [{"id": v.id, "dev_f1": v.metrics["dev_macro_f1"], "order": i} for i, v in enumerate(archive.accepted())]
        parent = archive.get(improver.choose_parent(pool, rng))
        child, edit = improver.propose_child(archive.source(parent.id), rng)
        if child in seen:  # same code as an existing version: re-evaluating wastes budget
            v = record(archive, None, child, parent.id, edit, gen, False, "duplicate")
        elif not (report := safety.check(child, "pipeline")).ok:
            v = record(archive, None, child, parent.id, edit, gen, False, "unsafe: " + ", ".join(report.reasons[:2]))
        else:
            seen.add(child)
            out = evaluate_fn(child)
            gain = (out.metrics["dev_macro_f1"] - parent.metrics["dev_macro_f1"]) if out.ok else None
            # Gate: accept only if dev F1 beats the PARENT by min_delta -> no drift from noise
            ok = out.ok and gain >= cfg.min_delta
            v = record(archive, out, child, parent.id, edit, gen, ok,
                       "accepted" if ok else ("no_improvement" if out.ok else out.reason))
        f1 = v.metrics["dev_macro_f1"] if v.metrics else float("nan")
        log(f"gen {gen:02d} | {v.id} <- {parent.id} | {edit[:52]:52s} | dev {f1:.3f} | "
            f"{'ACCEPTED' if v.accepted else 'rejected: ' + v.reason}")
        stale = 0 if v.accepted and f1 > best else stale + 1
        best = max(best, f1) if v.accepted else best
        if stale >= cfg.patience:  # stop rule: budget is not spent on a search that has stalled
            log(f"stop: no improvement for {cfg.patience} generations")
            break


def summarize(archive: Archive) -> dict:
    """Headline numbers of a finished run (also what the web app shows first)."""
    pipes = [v for v in archive.versions if v.kind == "pipeline"]
    base = pipes[0]
    best = max(archive.accepted(), key=lambda v: v.metrics["dev_macro_f1"])
    reasons = Counter(v.reason.split(":")[0] for v in pipes[1:])
    return {"baseline_id": base.id, "best_id": best.id, "n_generations": len(pipes) - 1,
            "n_accepted": sum(v.accepted for v in pipes[1:]),
            "rejected_by_reason": {k: n for k, n in reasons.items() if k != "accepted"},
            "baseline_dev_f1": base.metrics["dev_macro_f1"], "best_dev_f1": best.metrics["dev_macro_f1"],
            "baseline_meta_dev_f1": base.metrics["meta_dev_macro_f1"], "best_meta_dev_f1": best.metrics["meta_dev_macro_f1"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    cfg = get_config(ap.parse_args().quick)
    if not (ROOT / "data" / "generated" / "verdicts.json").exists():
        sys.exit("No data yet: run `python scripts/01_generate_data.py` first.")
    archive = Archive()
    if archive.versions:
        sys.exit("archive/ is not empty: delete it for a fresh run (every run starts from v000).")
    rng = random.Random(cfg.seed)
    improver = import_source(normalize_source((ROOT / "evolvable" / "improver.py").read_text(encoding="utf-8")), "improver_v000")
    baseline = normalize_source((ROOT / "evolvable" / "pipeline.py").read_text(encoding="utf-8"))
    out = evaluate_pipeline(baseline, cfg)
    if not out.ok:
        sys.exit(f"baseline pipeline failed to evaluate: {out.reason} {out.detail}")
    record(archive, out, baseline, None, "baseline", 0, True, "baseline", "baseline")
    print(f"v000 baseline | dev {out.metrics['dev_macro_f1']:.3f} | meta_dev {out.metrics['meta_dev_macro_f1']:.3f}")
    run_level1(cfg, archive, improver, lambda src: evaluate_pipeline(src, cfg), rng)
    summary = summarize(archive)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "evolution_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
