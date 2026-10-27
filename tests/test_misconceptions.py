"""Structural checks on mutate/repair. (Tests that RUN the code come after the sandbox exists.)"""
import ast

from codecoach.misconceptions import LABELS, mutate, normalize, repair
from codecoach.problems import PROBLEMS


def test_every_class_applies_to_several_problems() -> None:
    # If a class had few host functions, its data would be tiny and repetitive.
    for label in LABELS:
        hosts = [p.name for p in PROBLEMS if mutate(p.source, label)]
        assert len(hosts) >= 3, f"{label} only applies to {hosts}"


def test_mutants_parse_and_differ_from_original() -> None:
    for p in PROBLEMS:
        for label in LABELS:
            for src, _ in mutate(p.source, label):
                ast.parse(src)
                assert src != normalize(p.source)


def test_every_mutation_can_be_undone_by_its_own_repair() -> None:
    # Strongest check we can do without running code: repair candidates of the bugged
    # program must include the original program.
    for p in PROBLEMS:
        original = normalize(p.source)
        for label in LABELS:
            for bug, desc in mutate(p.source, label):
                fixes = {src for src, _ in repair(bug, label)}
                assert original in fixes, f"{p.name}/{label}/{desc}: repair cannot undo it"


def test_classes_do_not_produce_identical_bugs() -> None:
    # The same buggy text under two labels would make the label ambiguous.
    for p in PROBLEMS:
        seen: dict[str, str] = {}
        for label in LABELS:
            for src, _ in mutate(p.source, label):
                assert seen.setdefault(src, label) == label, f"{p.name}: {label} vs {seen[src]}"
