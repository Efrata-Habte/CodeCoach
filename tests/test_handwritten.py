"""Quality checks on the hand-written final-test set. NO model is involved: only the sandbox and the verifier."""
import ast
import importlib.util
from collections import Counter

from codecoach.generator import normalize_names
from codecoach.misconceptions import LABELS
from codecoach.problems import PROBLEMS, Problem
from codecoach.sandbox import run_tests_many
from codecoach.utils import ROOT
from codecoach.verifier import verify

spec = importlib.util.spec_from_file_location("handwritten_cases", ROOT / "data" / "handwritten" / "cases.py")
cases_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cases_mod)
CASES = cases_mod.CASES


def test_balanced_labels_and_enough_cases() -> None:
    counts = Counter(c["label"] for c in CASES)
    assert set(counts) == set(LABELS) and len(CASES) >= 25 and min(counts.values()) >= 5


def test_style_differs_from_training_problems() -> None:
    trained = {p.func_name for p in PROBLEMS}
    assert not {c["name"] for c in CASES} & trained  # new problems, new names
    assert sum("while " in c["code"] for c in CASES) >= 3  # includes while loops
    assert sum("for v in " in c["code"] for c in CASES) >= 3  # loops over elements, not range(len(...))


def test_every_case_is_a_real_bug_that_its_own_label_can_fix() -> None:
    # Validates the DATA (sandbox + verifier only; no model, no search step touches it).
    for c in CASES:
        code = normalize_names(c["code"])
        ast.parse(code)
        assert not run_tests_many([code], "f", c["tests"])[0].passed, f"{c['name']} is not actually buggy"
        problem = Problem(c["name"], code, "f", c["tests"])
        verdict = verify(code, c["label"], problem)
        assert verdict.accepted, f"{c['name']}: no {c['label']} repair passes the tests ({verdict.reason})"
