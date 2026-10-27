"""Fix-and-test verifier: the INDEPENDENT judge of a diagnosis.

    A model agreeing with itself is not proof. Executable tests are.

A diagnosis ("this bug is class X") is accepted ONLY IF applying a class-X repair makes ALL
the problem's hidden tests pass. The verifier never sees the model's confidence or the true
label: its inputs are just (buggy code, predicted label, problem). That independence is what
stops self-training from confirming its own mistakes.
"""
from dataclasses import dataclass

from codecoach.generator import PoolSample, normalized_problem
from codecoach.misconceptions import LABELS, repair
from codecoach.problems import BY_NAME, Problem
from codecoach.sandbox import DEFAULT_TIMEOUT_S, run_tests_many
from codecoach.utils import sha256_text


@dataclass(frozen=True)
class Verdict:
    """Result of verifying one diagnosis."""
    accepted: bool
    reason: str          # "verified" | "no_repair_applicable" | "tests_still_fail" | "timeout"
    fixed_source: str | None = None   # the repaired code that passed (if accepted)
    fix_description: str = ""         # e.g. "range stop +1 (line 3)"


def verify(buggy_source: str, predicted_label: str, problem: Problem,
           timeout: float = DEFAULT_TIMEOUT_S) -> Verdict:
    """Accept `predicted_label` iff some repair of that class makes every test pass."""
    # Only the PREDICTED class's repairs are tried: a wrong label should find no working fix.
    candidates = repair(buggy_source, predicted_label)
    if not candidates:
        return Verdict(False, "no_repair_applicable")  # e.g. predicted LOGIC_OPERATOR but no and/or
    results = run_tests_many([src for src, _ in candidates], problem.func_name, problem.tests, timeout)
    for (src, desc), res in zip(candidates, results):
        if res.passed:
            return Verdict(True, "verified", src, desc)
    if all(r.reason == "timeout" for r in results):
        return Verdict(False, "timeout")
    return Verdict(False, "tests_still_fail")


def verdict_key(code: str, label: str) -> str:
    """Lookup key of one (program, claimed label) question."""
    return f"{sha256_text(code)[:16]}:{label}"


def build_verdict_table(pool: list[PoolSample]) -> dict[str, str]:
    """Answer EVERY (program, label) question once: key -> verdict reason ("verified" if accepted).

    The verifier is fixed and deterministic and does not depend on any model, so its answers can be
    computed once and looked up. Each pipeline version evaluated later then costs milliseconds
    instead of thousands of sandbox runs. The lookup returns exactly what verify() would.
    """
    table = {}
    for item in pool:
        problem = normalized_problem(BY_NAME[item.problem])
        for label in LABELS:
            table[verdict_key(item.code, label)] = verify(item.code, label, problem).reason
    return table
