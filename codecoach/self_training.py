"""Level 0: verified self-training. Changes the model's WEIGHTS; the code stays as it is.

Each round: the teacher diagnoses unlabeled buggy programs -> only diagnoses the VERIFIER confirms
(a repair of that class makes the hidden tests pass) become new training data -> a COPY of the
teacher is trained on seed + verified examples -> the copy replaces the teacher only if it passes
the dev gate; otherwise rollback. All tunable knobs come from the pipeline module `pipe`.
"""
import random
import time
from collections import Counter
from dataclasses import dataclass
from types import ModuleType
from typing import Callable

from config import Config
from codecoach.generator import PoolSample, Splits, normalized_problem
from codecoach.misconceptions import LABELS
from codecoach.problems import BY_NAME
from codecoach.teacher import Featurizer, Teacher, evaluate, fit_teacher
from codecoach.verifier import verdict_key, verify


@dataclass
class SelfTrainResult:
    """What Level 0 returns: the final teacher plus a log of every round."""
    teacher: Teacher
    rounds: list[dict]       # one dict per round (see self_train)
    initial_dev: dict        # report of teacher v0 (seed only)
    final_dev: dict          # report of the last accepted teacher
    n_verified: int          # pseudo-labels in the final accepted training set
    train_time_s: float


def gate(new: dict, best: dict, min_delta: float, max_class_drop: float) -> tuple[bool, str]:
    """Accept/reject a candidate teacher using dev reports.

    Gate: reject if dev F1 does not improve -> prevents self-confirming errors.
    Also reject if any single class gets much worse, even when the average rises (an average can
    hide a class being sacrificed).
    """
    if new["macro_f1"] < best["macro_f1"] + min_delta:
        return False, "no_improvement"
    if max(best["per_class_f1"][c] - new["per_class_f1"][c] for c in LABELS) > max_class_drop:
        return False, "class_dropped"
    return True, "accepted"


def effective_min_delta(cfg: Config, pipe: ModuleType) -> float:
    """The pipeline file may TIGHTEN the gate but never loosen it below the config floor.

    Otherwise a self-edit could set MIN_DELTA = -1, accept every round, and the gate would protect nothing.
    """
    return max(cfg.min_delta, pipe.MIN_DELTA)


def filter_pseudo_labels(items: list[PoolSample], preds: list[str], confs: list[float], cfg: Config,
                         verdicts: dict[str, str]) -> tuple[list[int], Counter]:
    """Indices of accepted pseudo-labels + a count of rejection reasons.

    Default: the independent verifier decides (it never sees `confs`). Ablation
    (cfg.ablate_verifier): trust the model's own confidence instead, to test if the verifier matters.
    """
    kept: list[int] = []
    reasons: Counter = Counter()
    for k, (item, label, conf) in enumerate(zip(items, preds, confs)):
        if cfg.ablate_verifier:
            reason = "verified" if conf >= cfg.confidence_threshold else "low_confidence"
        else:
            key = verdict_key(item.code, label)  # precomputed answer of verify(); same result
            reason = verdicts[key] if key in verdicts else verify(
                item.code, label, normalized_problem(BY_NAME[item.problem])).reason
        if reason == "verified":
            kept.append(k)
        else:
            reasons[reason] += 1
    return kept, reasons


def _mean(flags: list[bool]) -> float | None:
    """Fraction of True values (None for an empty list)."""
    return sum(flags) / len(flags) if flags else None


def self_train(pipe: ModuleType, splits: Splits, cfg: Config, seed: int = 0,
               verdicts: dict[str, str] | None = None,
               on_round: Callable[[dict], None] | None = None) -> SelfTrainResult:
    """Run Level 0 with the settings in `pipe`. Reads only `.code` of pool items while looping.

    `on_round` (optional) receives each round's log dict the moment the round ends: the live demo
    uses it to draw charts while training is still running.
    """
    start, rng, verdicts = time.time(), random.Random(seed), verdicts or {}
    featurizer = Featurizer(pipe).fit([s.code for s in splits.seed] + [p.code for p in splits.pool])
    seed_ex = [(s.code, s.label) for s in splits.seed]
    teacher = fit_teacher(pipe, featurizer, seed_ex, seed)          # teacher v0: labeled seed only
    best = initial = evaluate(teacher, splits.dev)
    accepted_ex: list[tuple[str, str]] = []                          # verified pseudo-labels kept so far
    used: set[int] = set()                                           # pool items already absorbed
    min_delta = effective_min_delta(cfg, pipe)
    bad_rounds, logs = 0, []
    for rnd in range(1, min(int(pipe.SELF_TRAIN_ROUNDS), cfg.max_rounds) + 1):
        free = [i for i in range(len(splits.pool)) if i not in used]
        if not free:
            break
        idx = rng.sample(free, min(int(pipe.POOL_PER_ROUND), len(free)))
        items = [splits.pool[i] for i in idx]
        preds, confs = teacher.predict([it.code for it in items])
        kept, reasons = filter_pseudo_labels(items, preds, confs, cfg, verdicts)
        new_ex = [(items[k].code, preds[k]) for k in kept]
        # hidden labels are read ONLY here, for the log; they never influence a decision
        log = {"round": rnd, "pool_size": len(items), "n_verified": len(kept), "rejected": dict(reasons),
               "precision": _mean([items[k].hidden_label == preds[k] for k in kept]),
               "raw_accuracy": _mean([it.hidden_label == p for it, p in zip(items, preds)])}
        if kept:
            train_ex = seed_ex + pipe.curate(accepted_ex + new_ex, rng)
            candidate = fit_teacher(pipe, featurizer, train_ex, seed + rnd)  # a COPY, trained separately
            report = evaluate(candidate, splits.dev)
            ok, why = gate(report, best, min_delta, cfg.max_class_drop)
            log.update(n_train=len(train_ex), dev_f1=report["macro_f1"], per_class_f1=report["per_class_f1"])
        else:
            ok, why, report = False, "nothing_verified", None
        if ok:
            teacher, best = candidate, report                        # promote the copy
            accepted_ex += new_ex
            used.update(idx[k] for k in kept)
            bad_rounds = 0
        else:
            bad_rounds += 1                                          # rollback: old teacher was never touched
        logs.append({**log, "decision": "accepted" if ok else "rejected", "reason": why,
                     "best_dev_f1": best["macro_f1"]})
        if on_round:
            on_round(logs[-1])
        if bad_rounds >= cfg.max_bad_rounds:                        # stop rule: no budget wasted on a stuck loop
            break
    return SelfTrainResult(teacher, logs, initial, best, len(accepted_ex), time.time() - start)
