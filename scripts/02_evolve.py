"""Script 02: Level 1 (edit the pipeline source) + Level 2 (the improver edits ITSELF).
Usage: python scripts/02_evolve.py [--quick] [--no-level2] [--tag NAME]

Level 1 loop: pick a parent -> the improver proposes an edited child source -> static safety check -> the
FIXED evaluator scores it -> accept only if dev F1 beats the parent by min_delta. Accepted AND rejected
versions are archived (rejected ones flagged) for the UI and failure analysis.
Level 2 (every K generations, STOP-style): the improver proposes an edited copy of its own file. Old and new
improver each try B edits from the SAME parent with the SAME seeds; the new one is kept only if its edits are
worth more on meta_dev (a split the pipeline was never selected on).
"""
import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import asdict, replace
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
    """Store one pipeline version (accepted or rejected) in the archive."""
    v = Version(archive.next_id("pipeline"), "pipeline", parent_id, proposer, edit, accepted, reason, gen,
                outcome.metrics if outcome and outcome.ok else None)
    archive.add(v, child, outcome.model_path if outcome else None)
    return v


class Level2:
    """Level 2: propose an edit of the improver's own source; keep it only if it is a better improver."""

    def __init__(self, cfg: Config, archive: Archive, evaluate_fn: Callable[[str], EvalOutcome],
                 log: Callable[[str], None] = print, on_event: Callable[[dict], None] | None = None) -> None:
        self.cfg, self.archive, self.evaluate_fn, self.log, self.on_event = cfg, archive, evaluate_fn, log, on_event
        self.id = "improver_v000"
        self.source = archive.source(self.id)
        self.cache: dict[str, dict | None] = {}  # evaluation is deterministic: the same child is scored once

    def _metrics(self, source: str) -> dict | None:
        """dev / meta_dev F1 of a probe child (None if it failed). Probes are never archived as pipelines."""
        if source not in self.cache:
            out = self.evaluate_fn(source)
            if out.model_path:
                Path(out.model_path).unlink(missing_ok=True)
            self.cache[source] = out.metrics if out.ok else None
        return self.cache[source]

    def utility(self, module, parent: Version, seed: int) -> tuple[float, list[dict]]:
        """Mean value of B edits from a FIXED parent. An edit is worth its meta_dev gain only if it would
        have passed the Level 1 dev gate; otherwise 0. So the improver is paid for edits that help on data
        the pipeline was not selected on, and is not rewarded for edits that merely overfit dev."""
        rng, probes = random.Random(seed), []
        parent_src = self.archive.source(parent.id)
        for _ in range(self.cfg.improver_budget):
            child, edit = module.propose_child(parent_src, rng)
            gain, outcome = 0.0, "no_change"
            if child != normalize_source(parent_src):
                m = self._metrics(child) if safety.check(child).ok else "unsafe"
                if m == "unsafe":
                    outcome = "unsafe"
                elif m is None:
                    outcome = "failed"
                elif m["dev_macro_f1"] - parent.metrics["dev_macro_f1"] >= self.cfg.min_delta:
                    gain, outcome = m["meta_dev_macro_f1"] - parent.metrics["meta_dev_macro_f1"], "kept"
                else:
                    outcome = "no_improvement"
            probes.append({"edit": edit, "gain": gain, "outcome": outcome})
        return sum(p["gain"] for p in probes) / len(probes), probes

    def _record(self, gen: int, edit: str, accepted: bool, reason: str, source: str, metrics: dict | None) -> Version:
        v = Version(self.archive.next_id("improver"), "improver", self.id, "rule_based", edit, accepted, reason,
                    gen, metrics)
        self.archive.add(v, source)
        if self.on_event:
            self.on_event({"type": "improver", "version": asdict(v)})
        return v

    def __call__(self, gen: int, improver):
        """Try one self-edit; return the improver module to use from now on (new if accepted, else the old one)."""
        proposal = improver.propose_self_edit(self.source, random.Random(self.cfg.seed * 7919 + gen))
        known = {normalize_source(self.archive.source(v.id)) for v in self.archive.versions if v.kind == "improver"}
        if proposal is None:
            self._record(gen, "no_edit", False, "no_edit", self.source, None)
            return improver
        new_src, edit = proposal
        if new_src in known:
            self._record(gen, edit, False, "duplicate", new_src, None)
            return improver
        report = safety.check(new_src, "improver")
        if not report.ok:
            self._record(gen, edit, False, "unsafe: " + ", ".join(report.reasons[:2]), new_src, None)
            self.log(f"level 2 | {edit} | rejected: unsafe")
            return improver
        new_mod = import_source(new_src, f"improver_candidate_{gen}")
        parent = max(self.archive.accepted(), key=lambda v: v.metrics["dev_macro_f1"])  # fixed for both improvers
        seed = self.cfg.seed * 104729 + gen  # SAME seed for both: they differ only in their settings
        u_old, probes_old = self.utility(improver, parent, seed)
        u_new, probes_new = self.utility(new_mod, parent, seed)
        # STOP-style gate: accept the new improver only if it improves pipelines MORE than the old one did
        ok = u_new > u_old + self.cfg.min_delta
        metrics = {"utility": u_new, "utility_old": u_old, "probe_parent": parent.id,
                   "probes": probes_new, "probes_old": probes_old}
        self._record(gen, edit, ok, "accepted" if ok else "no_improvement", new_src, metrics)
        self.log(f"level 2 | {edit} | utility new {u_new:+.3f} vs old {u_old:+.3f} | "
                 f"{'ACCEPTED' if ok else 'rejected: no_improvement'}")
        if ok:
            self.id, self.source = self.archive.versions[-1].id, new_src
            return new_mod
        return improver


def run_level1(cfg: Config, archive: Archive, improver, evaluate_fn: Callable[[str], EvalOutcome],
               rng: random.Random, log: Callable[[str], None] = print, level2: Level2 | None = None,
               on_event: Callable[[dict], None] | None = None) -> None:
    """Run up to cfg.generations pipeline edits (plus a Level 2 step every K gens if `level2` is given)."""
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
        if on_event:
            on_event({"type": "pipeline", "version": asdict(v)})
        stale = 0 if v.accepted and f1 > best else stale + 1
        best = max(best, f1) if v.accepted else best
        if level2 and gen % cfg.improver_every == 0:  # Level 2: the improver edits ITSELF
            improver = level2(gen, improver)
        if stale >= cfg.patience:  # stop rule: budget is not spent on a search that has stalled
            log(f"stop: no improvement for {cfg.patience} generations")
            break


def summarize(archive: Archive) -> dict:
    """Headline numbers of a finished run (also what the web app shows first)."""
    pipes = [v for v in archive.versions if v.kind == "pipeline"]
    imps = [v for v in archive.versions if v.kind == "improver"]
    base, best = pipes[0], max(archive.accepted(), key=lambda v: v.metrics["dev_macro_f1"])
    reasons = Counter(v.reason.split(":")[0] for v in pipes[1:])
    return {"baseline_id": base.id, "best_id": best.id, "n_generations": len(pipes) - 1,
            "n_accepted": sum(v.accepted for v in pipes[1:]),
            "rejected_by_reason": {k: n for k, n in reasons.items() if k != "accepted"},
            "baseline_dev_f1": base.metrics["dev_macro_f1"], "best_dev_f1": best.metrics["dev_macro_f1"],
            "baseline_meta_dev_f1": base.metrics["meta_dev_macro_f1"], "best_meta_dev_f1": best.metrics["meta_dev_macro_f1"],
            "improver_proposals": len(imps) - 1, "improver_accepted": sum(v.accepted for v in imps[1:]),
            "final_improver_id": next(v.id for v in reversed(imps) if v.accepted)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--no-level2", action="store_true", help="ablation: the improver never edits itself")
    ap.add_argument("--tag", default="", help="store in archive/<tag>/ (ablation runs need their own archive)")
    args = ap.parse_args()
    cfg = get_config(args.quick)
    cfg = replace(cfg, ablate_level2=True) if args.no_level2 else cfg
    if not (ROOT / "data" / "generated" / "verdicts.json").exists():
        sys.exit("No data yet: run `python scripts/01_generate_data.py` first.")
    archive = Archive(ROOT / "archive" / args.tag if args.tag else None)
    if archive.versions:
        sys.exit(f"{archive.root} is not empty: delete it for a fresh run (every run starts from v000).")
    rng = random.Random(cfg.seed)
    imp_src = normalize_source((ROOT / "evolvable" / "improver.py").read_text(encoding="utf-8"))
    archive.add(Version("improver_v000", "improver", None, "baseline", "baseline", True, "baseline", 0), imp_src)
    improver = import_source(imp_src, "improver_v000")
    baseline = normalize_source((ROOT / "evolvable" / "pipeline.py").read_text(encoding="utf-8"))
    evaluate_fn = lambda src: evaluate_pipeline(src, cfg)  # noqa: E731
    out = evaluate_fn(baseline)
    if not out.ok:
        sys.exit(f"baseline pipeline failed to evaluate: {out.reason} {out.detail}")
    record(archive, out, baseline, None, "baseline", 0, True, "baseline", "baseline")
    print(f"v000 baseline | dev {out.metrics['dev_macro_f1']:.3f} | meta_dev {out.metrics['meta_dev_macro_f1']:.3f}")
    level2 = None if cfg.ablate_level2 else Level2(cfg, archive, evaluate_fn)
    run_level1(cfg, archive, improver, evaluate_fn, rng, level2=level2)
    summary = summarize(archive)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / f"evolution_summary{'_' + args.tag if args.tag else ''}.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
