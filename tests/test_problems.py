"""Sanity checks on the problem set: the answer key itself must be correct."""
from codecoach.problems import PROBLEMS


def _run_reference(problem) -> list:
    """Run the reference solution on its tests in-process (trusted code, so no sandbox needed)."""
    scope: dict = {}
    exec(problem.source, scope)  # noqa: S102 - our own reference code, never model output
    fn = scope[problem.func_name]
    return [fn(*args) == expected for args, expected in problem.tests]


def test_problem_count() -> None:
    assert 18 <= len(PROBLEMS) <= 24


def test_names_are_unique() -> None:
    names = [p.name for p in PROBLEMS]
    assert len(names) == len(set(names))


def test_reference_solutions_pass_their_own_tests() -> None:
    # If this fails, either the solution or a test is wrong -> everything downstream is wrong.
    for p in PROBLEMS:
        assert all(_run_reference(p)), f"{p.name} fails its own tests"


NEEDS_TWO_ELEMENTS = {"second_largest"}  # a 1-element list has no second largest: not a valid input


def test_enough_tests_with_boundary_case() -> None:
    for p in PROBLEMS:
        assert 5 <= len(p.tests) <= 10, p.name
        if p.name in NEEDS_TWO_ELEMENTS:
            continue  # its boundary cases are the 2-element tests ([1, 2], [4, 4])
        # a boundary case = some argument that is empty/single-element (or n <= 1)
        small = any(
            (hasattr(a, "__len__") and len(a) <= 1) or (isinstance(a, int) and a <= 1)
            for args, _ in p.tests for a in args
        )
        assert small, f"{p.name} has no boundary test"
