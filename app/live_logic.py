"""Streamlit-free logic behind the live pages, so it can be unit-tested.

Live learning, in four steps: (1) a model diagnoses a pasted snippet, (2) the VERIFIER checks the diagnosis
against the hidden tests, (3) verified snippets go into a buffer, (4) a candidate teacher is retrained on
seed + buffer and must pass the same dev GATE as in Level 0, otherwise it is rolled back.
"""
import json
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F

from config import Config
from codecoach.archive import Archive, import_source
from codecoach.distillation import load_student
from codecoach.generator import Splits, load_splits, normalize_names
from codecoach.misconceptions import LABELS, repair
from codecoach.problems import BY_NAME, Problem
from codecoach.sandbox import run_tests
from codecoach.self_training import effective_min_delta, gate
from codecoach.teacher import Featurizer, Teacher, evaluate, fit_teacher, load_teacher
from codecoach.utils import ROOT
from codecoach.verifier import Verdict, verify


@dataclass
class StudentHandle:
    """A student network + the featurizer it reads, behind the same .proba() as a Teacher."""
    model: torch.nn.Module
    featurizer: Featurizer

    def proba(self, codes: list[str]) -> np.ndarray:
        with torch.no_grad():
            return F.softmax(self.model(torch.tensor(self.featurizer.transform(codes))), dim=1).numpy()


def load_handles(archive: Archive, best_id: str) -> dict:
    """Every model the Try-it page can use: v000 teacher, best teacher, and saved students (if script 03 ran)."""
    pipes = {i: import_source(archive.source(i), f"app_{i}") for i in {"v000", best_id}}
    handles = {"teacher v000": load_teacher(pipes["v000"], archive.root / "v000" / "model.pt"),
               f"teacher best ({best_id})": load_teacher(pipes[best_id], archive.root / best_id / "model.pt")}
    for name in ("student_hard", "student_distilled_best"):
        path = ROOT / "results" / "models" / f"{name}.pt"
        if path.exists():
            handles[name.replace("_", " ")] = StudentHandle(*load_student(path, pipes[best_id]))
    return handles


def load_data() -> tuple[Splits, dict]:
    """Splits and the verdict table from data/generated/."""
    d = ROOT / "data" / "generated"
    return load_splits(d / "splits.json"), json.loads((d / "verdicts.json").read_text(encoding="utf-8"))


def snippet_problem(code: str, problem_name: str | None) -> tuple[str, Problem | None]:
    """Normalize a pasted function (name -> f, locals -> v1..) and attach the chosen problem's hidden tests."""
    normalized = normalize_names(code)
    if not problem_name:
        return normalized, None
    p = BY_NAME[problem_name]
    return normalized, Problem(p.name, normalized, "f", p.tests)


def diagnose(handle, normalized: str) -> dict:
    """Class probabilities and the predicted class of one model for one normalized snippet."""
    probs = handle.proba([normalized])[0]
    return {"probs": dict(zip(LABELS, probs.tolist())), "label": LABELS[int(probs.argmax())]}


def check_fix(normalized: str, label: str, problem: Problem | None) -> dict:
    """Verifier verdict for a claimed label; without hidden tests only an UNVERIFIED repair candidate is offered."""
    if problem is None:
        candidates = repair(normalized, label)
        return {"verified": None, "fixed": candidates[0][0] if candidates else None,
                "note": "no hidden tests for this snippet: the repair below is NOT verified"}
    verdict: Verdict = verify(normalized, label, problem)
    return {"verified": verdict.accepted, "fixed": verdict.fixed_source,
            "note": f"{verdict.reason}" + (f" ({verdict.fix_description})" if verdict.accepted else "")}


def tests_pass(normalized: str, problem: Problem) -> bool:
    """Does the pasted code already pass the problem's hidden tests?"""
    return run_tests(normalized, "f", problem.tests).passed


def new_live_learner(pipe, splits: Splits, cfg: Config, seed: int = 0) -> dict:
    """The starting point of live learning: a teacher trained on the labeled seed ONLY (weak on purpose)."""
    featurizer = Featurizer(pipe).fit([s.code for s in splits.seed] + [p.code for p in splits.pool])
    seed_ex = [(s.code, s.label) for s in splits.seed]
    teacher = fit_teacher(pipe, featurizer, seed_ex, seed)
    return {"teacher": teacher, "featurizer": featurizer, "seed_ex": seed_ex, "dev": evaluate(teacher, splits.dev),
            "buffer": [], "history": [], "seed": seed}


def retrain_with_buffer(learner: dict, pipe, splits: Splits, cfg: Config) -> dict:
    """Train a CANDIDATE on seed + verified buffer; promote it only if it passes the dev gate (else rollback)."""
    candidate = fit_teacher(pipe, learner["featurizer"], learner["seed_ex"] + learner["buffer"], learner["seed"] + 1)
    report = evaluate(candidate, splits.dev)
    ok, why = gate(report, learner["dev"], effective_min_delta(cfg, pipe), cfg.max_class_drop)
    result = {"accepted": ok, "reason": why, "dev_before": learner["dev"]["macro_f1"], "dev_after": report["macro_f1"],
              "n_buffer": len(learner["buffer"])}
    if ok:  # promote the copy; on rejection the old teacher object is untouched (rollback)
        learner["teacher"], learner["dev"] = candidate, report
    learner["history"].append(result)
    return result
