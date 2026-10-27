"""Sandbox + verifier tests, including the full mutate -> fail -> repair -> pass loop."""
from codecoach.misconceptions import LABELS, mutate
from codecoach.problems import BY_NAME, PROBLEMS
from codecoach.sandbox import _CACHE, run_tests, run_tests_many
from codecoach.verifier import verify

P = BY_NAME["sum_list"]


def test_reference_solutions_pass_in_sandbox() -> None:
    for p in PROBLEMS:
        assert run_tests(p.source, p.func_name, p.tests).passed, p.name


def test_infinite_loop_times_out() -> None:
    loop = "def sum_list(xs):\n    while True:\n        pass\n"
    assert run_tests(loop, "sum_list", P.tests, timeout=1.0).reason == "timeout"


def test_exception_counts_as_failure_and_syntax_error_is_error() -> None:
    boom = "def sum_list(xs):\n    raise ValueError\n"
    assert run_tests(boom, "sum_list", P.tests).reason == "tests_failed"
    assert run_tests("def sum_list(xs) return", "sum_list", P.tests).reason == "error"


def test_results_are_cached_by_source_hash() -> None:
    src = "def sum_list(xs):\n    return 0\n"
    run_tests(src, "sum_list", P.tests)
    size = len(_CACHE)
    run_tests(src, "sum_list", P.tests)
    assert len(_CACHE) == size  # second call hit the cache, no new entry


def test_bool_is_not_confused_with_int() -> None:
    src = "def is_empty(xs):\n    return 1\n"  # returns 1 where True is expected
    assert not run_tests(src, "is_empty", [(([],), True)]).passed


def test_every_real_bug_is_diagnosed_by_its_own_class_and_none_is_free() -> None:
    # The core guarantee: a mutant that FAILS the tests can always be fixed by its own class's repair.
    checked = 0
    for p in PROBLEMS:
        for label in LABELS:
            mutants = mutate(p.source, label)
            results = run_tests_many([m for m, _ in mutants], p.func_name, p.tests)
            for (bug, desc), res in zip(mutants, results):
                if res.passed:
                    continue  # equivalent mutant (tests cannot tell) -> the generator drops these
                v = verify(bug, label, p)
                assert v.accepted, f"{p.name}/{label}/{desc}: {v.reason}"
                checked += 1
    assert checked > 100  # make sure the loop really exercised many bugs


def test_label_with_nothing_to_repair_is_rejected() -> None:
    v = verify(P.source, "COMPARISON_BOUNDARY", P)  # sum_list has no comparison at all
    assert not v.accepted and v.reason == "no_repair_applicable"
