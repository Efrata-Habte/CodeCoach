"""Level 0 tests: gate, filter, curation, feature blocks, rollback, and 'never reads hidden labels'."""
import random
from dataclasses import replace
from types import SimpleNamespace

import pytest

import evolvable.pipeline as pipe
from config import Config, get_config
from codecoach import feature_blocks as fb
from codecoach.generator import PoolSample, Splits, build_splits
from codecoach.misconceptions import LABELS
from codecoach.self_training import effective_min_delta, filter_pseudo_labels, gate, self_train


def _pipe(**overrides) -> SimpleNamespace:
    """A copy of pipeline v0 with some settings changed (the real module is never modified)."""
    base = {k: getattr(pipe, k) for k in dir(pipe) if not k.startswith("_")}
    return SimpleNamespace(**{**base, **overrides})


def _report(f1: float, **per_class) -> dict:
    return {"macro_f1": f1, "per_class_f1": {**{c: f1 for c in LABELS}, **per_class}}


# ---- gate -------------------------------------------------------------------------------------
def test_gate_accepts_clear_improvement() -> None:
    assert gate(_report(0.60), _report(0.50), 0.005, 0.10) == (True, "accepted")


def test_gate_rejects_no_improvement_and_tiny_gain() -> None:
    assert gate(_report(0.50), _report(0.50), 0.005, 0.10) == (False, "no_improvement")
    assert gate(_report(0.502), _report(0.50), 0.005, 0.10) == (False, "no_improvement")


def test_gate_rejects_when_one_class_collapses_even_if_average_rises() -> None:
    new = _report(0.70, WRONG_INDEX=0.20)  # average up, but WRONG_INDEX fell from 0.50 to 0.20
    assert gate(new, _report(0.50), 0.005, 0.10) == (False, "class_dropped")


def test_pipeline_cannot_loosen_the_gate() -> None:
    assert effective_min_delta(Config(), SimpleNamespace(MIN_DELTA=-1.0)) == Config().min_delta
    assert effective_min_delta(Config(), SimpleNamespace(MIN_DELTA=0.05)) == 0.05


# ---- filter -----------------------------------------------------------------------------------
def test_verifier_ablation_uses_confidence_only() -> None:
    items = [PoolSample("c1", "sum_list", "X"), PoolSample("c2", "sum_list", "X")]
    cfg = replace(Config(), ablate_verifier=True)
    kept, reasons = filter_pseudo_labels(items, ["A", "A"], [0.95, 0.50], cfg, {})
    assert kept == [0] and reasons == {"low_confidence": 1}


# ---- curation & features -------------------------------------------------------------------------
def test_curate_removes_duplicates_and_caps_each_class(monkeypatch) -> None:
    examples = [(f"code{i}", "A") for i in range(100)] + [("dup", "B"), ("dup", "B")]
    monkeypatch.setattr(pipe, "CURATION", "dedup_cap")  # curate() reads module globals, so patch them
    monkeypatch.setattr(pipe, "PER_CLASS_CAP", 10)
    curated = pipe.curate(examples, random.Random(0))
    assert sum(lab == "A" for _, lab in curated) == 10 and sum(lab == "B" for _, lab in curated) == 1


def test_feature_blocks_count_what_they_say() -> None:
    code = "def f(v1):\n    v2 = 0\n    for v3 in range(len(v1) - 1):\n        if v1[v3] <= v1[v3 + 1] and v2 < 5:\n            v2 += 1\n    return v2"
    assert (fb.count_comparisons(code), fb.count_range_calls(code), fb.count_subscripts(code)) == (2, 1, 2)
    assert (fb.count_boolops(code), fb.count_const_assigns(code), fb.has_while(code)) == (1, 1, 0)
    assert fb.count_plus_minus_one(code) == 2 and fb.max_loop_depth(code) == 1
    assert fb.count_comparisons("not python (") == 0  # unparseable code gives 0, no crash


# ---- the loop itself --------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def splits() -> Splits:
    return build_splits(get_config(quick=True))


def test_impossible_gate_means_rollback_and_early_stop(splits) -> None:
    r = self_train(_pipe(MIN_DELTA=10.0), splits, Config(), seed=0)
    assert [x["decision"] for x in r.rounds] == ["rejected", "rejected"]  # stopped after max_bad_rounds=2
    assert r.n_verified == 0 and r.final_dev == r.initial_dev            # nothing was promoted


def test_loop_never_reads_hidden_labels(splits) -> None:
    # Scramble every hidden label. Only the *logged* statistics may change, never a decision.
    scrambled = Splits(splits.seed, [PoolSample(p.code, p.problem, "SCRAMBLED") for p in splits.pool],
                       splits.dev, splits.meta_dev, splits.test, splits.problems)
    a = self_train(_pipe(SELF_TRAIN_ROUNDS=2), splits, Config(), seed=0)
    b = self_train(_pipe(SELF_TRAIN_ROUNDS=2), scrambled, Config(), seed=0)
    strip = lambda rounds: [{k: v for k, v in r.items() if k not in ("precision", "raw_accuracy")}  # noqa: E731
                            for r in rounds]
    assert strip(a.rounds) == strip(b.rounds) and a.final_dev == b.final_dev
