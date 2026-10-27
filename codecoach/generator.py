"""Build the dataset: buggy variants of every problem, split BY PROBLEM.

Pipeline: style variants of each reference -> normalize names -> inject every single-place bug ->
drop equivalent mutants (still pass all tests = not really bugs) -> cap per (problem, class) ->
split problems into train/dev/meta_dev/test.

Why split by PROBLEM, not by sample: variants of one function look almost identical. If they were
spread over train and test, the model could "recognise the function" instead of learning the
misconception, and test scores would be inflated.
Splits (each exists for exactly one purpose):
  train -> seed (small labeled part) + pool (unlabeled; true label hidden, only used to measure the
           verifier's precision afterwards)
  dev      -> fitness: Level 0 accept/reject gates and Level 1 pipeline selection
  meta_dev -> ONLY accepts/rejects improver edits (Level 2), so the improver is not judged on the
              data the pipeline was selected on
  test     -> synthetic test, touched only for final reporting tables
"""
import ast
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from config import Config
from codecoach.misconceptions import LABELS, mutate
from codecoach.problems import PROBLEMS, Problem
from codecoach.sandbox import run_tests_many
from codecoach.styles import style_variants

SPLIT_NAMES = ("train", "dev", "meta_dev", "test")


@dataclass(frozen=True)
class Sample:
    """A labeled buggy function. `edit` says which change was injected (for failure analysis)."""
    code: str
    problem: str
    label: str
    edit: str


@dataclass(frozen=True)
class PoolSample:
    """An UNLABELED buggy function. The true label is named `hidden_label` on purpose: the
    self-training loop must read only `.code`; the label is for measuring precision afterwards."""
    code: str
    problem: str
    hidden_label: str


@dataclass
class Splits:
    """All data the experiments use."""
    seed: list[Sample]
    pool: list[PoolSample]
    dev: list[Sample]
    meta_dev: list[Sample]
    test: list[Sample]
    problems: dict[str, list[str]]  # split name -> problem names (to prove splits are disjoint)


class _Renamer(ast.NodeTransformer):
    """Rename the function to `f` and parameters/locals to v1, v2, ... in order of appearance."""

    def __init__(self) -> None:
        self.names: dict[str, str] = {}

    def _new(self, old: str) -> str:
        return self.names.setdefault(old, f"v{len(self.names) + 1}")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.name = "f"
        for a in node.args.args:
            a.arg = self._new(a.arg)
        node.body = [self.visit(s) for s in node.body]
        return node

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if isinstance(node.ctx, ast.Store) or node.id in self.names:
            node.id = self._new(node.id)  # builtins like len/range are only Loads -> untouched
        return node


def normalize_names(source: str) -> str:
    """Hide naming style so the model must read the STRUCTURE of the bug, not variable names."""
    return ast.unparse(_Renamer().visit(ast.parse(source)))


def normalized_problem(p: Problem) -> Problem:
    """Same tests, but the function is now called `f` (what the verifier must call)."""
    return Problem(p.name, normalize_names(p.source), "f", p.tests)


def make_variants(p: Problem, cfg: Config, rng: random.Random) -> list[Sample]:
    """All real bugs (fail the tests) for one problem, at most `variants_per_problem` per class."""
    found: dict[str, tuple[str, str]] = {}  # buggy code -> (label, edit); dict keeps order = deterministic
    ambiguous: set[str] = set()
    for style in style_variants(p.source):  # same function, several equivalent writing styles
        for label in LABELS:
            for code, edit in mutate(normalize_names(style), label):
                if code in found and found[code][0] != label:
                    ambiguous.add(code)  # identical text under two labels -> label is meaningless
                found.setdefault(code, (label, edit))
    cands = [(code, label, edit) for code, (label, edit) in found.items() if code not in ambiguous]
    results = run_tests_many([c[0] for c in cands], "f", p.tests)
    # Equivalent-mutant filter: a "bug" that still passes every test is not a bug we can label.
    real = [Sample(code, p.name, label, edit) for (code, label, edit), r in zip(cands, results)
            if not r.passed]
    kept: list[Sample] = []
    for label in LABELS:
        group = [s for s in real if s.label == label]
        kept += rng.sample(group, min(len(group), cfg.variants_per_problem))
    return kept


def split_problems(variants: dict[str, list[Sample]], sizes: tuple, rng: random.Random,
                   min_class: int) -> dict:
    """Shuffle problems into splits; retry until EVERY split has >= `min_class` samples of EVERY class.
    Only class COUNTS are looked at (never model scores), so this cannot leak anything. Without it a
    split could hold 2 samples of a class: its F1 would jump by ~0.3 per mistake and the gates would
    react to noise."""
    assert sum(sizes) == len(variants), "split_sizes must add up to the number of problems"
    names = sorted(variants)
    best, best_score = None, -1
    for _ in range(3000):
        rng.shuffle(names)
        parts, start = {}, 0
        for split, size in zip(SPLIT_NAMES, sizes):
            parts[split], start = names[start:start + size], start + size
        counts = {s: Counter(x.label for n in parts[s] for x in variants[n]) for s in SPLIT_NAMES}
        if all(len(counts[s]) == len(LABELS) and min(counts[s].values()) >= min_class for s in SPLIT_NAMES):
            score = min(counts["train"].values())  # among valid splits, favour the best-fed training set
            if score > best_score:
                best, best_score = {k: list(v) for k, v in parts.items()}, score
    if best is None:
        raise RuntimeError("no problem split has enough samples of every class; lower min_class_per_split")
    return best


def build_splits(cfg: Config) -> Splits:
    """Generate the whole dataset from code (nothing is hand-edited -> fully reproducible)."""
    rng = random.Random(cfg.seed)
    variants = {p.name: make_variants(p, cfg, rng) for p in PROBLEMS}
    parts = split_problems(variants, cfg.split_sizes, rng, cfg.min_class_per_split)
    get = lambda split: [s for n in parts[split] for s in variants[n]]  # noqa: E731
    train = get("train")
    seed: list[Sample] = []
    for label in LABELS:  # stratified: ~seed_fraction of each class, but never fewer than the minimum
        group = [s for s in train if s.label == label]
        seed += rng.sample(group, max(cfg.min_seed_per_class, round(cfg.seed_fraction * len(group))))
    pool = [PoolSample(s.code, s.problem, s.label) for s in train if s not in seed]
    return Splits(seed, pool, get("dev"), get("meta_dev"), get("test"), parts)


def class_table(splits: Splits) -> str:
    """Printable class counts per split."""
    rows = {"seed": [s.label for s in splits.seed], "pool (hidden)": [s.hidden_label for s in splits.pool],
            "dev": [s.label for s in splits.dev], "meta_dev": [s.label for s in splits.meta_dev],
            "test": [s.label for s in splits.test]}
    head = f"{'split':14s}" + "".join(f"{lab[:10]:>11s}" for lab in LABELS) + f"{'total':>8s}"
    lines = [head] + [f"{name:14s}" + "".join(f"{Counter(ls)[lab]:11d}" for lab in LABELS) + f"{len(ls):8d}"
                      for name, ls in rows.items()]
    return "\n".join(lines)


def save_splits(splits: Splits, path: Path) -> None:
    """Write the dataset as JSON (data/generated/ is git-ignored: it is always regenerated)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(splits), indent=1), encoding="utf-8")


def load_splits(path: Path) -> Splits:
    """Read a dataset written by save_splits."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return Splits([Sample(**x) for x in d["seed"]], [PoolSample(**x) for x in d["pool"]],
                  [Sample(**x) for x in d["dev"]], [Sample(**x) for x in d["meta_dev"]],
                  [Sample(**x) for x in d["test"]], d["problems"])
