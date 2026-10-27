"""Dataset tests: splits are clean, bugs are real, names are normalized, build is reproducible."""
import ast
import re

import pytest

from config import Config
from codecoach.generator import (PoolSample, SPLIT_NAMES, build_splits, load_splits, normalize_names,
                                 save_splits)
from codecoach.misconceptions import LABELS
from codecoach.problems import BY_NAME, PROBLEMS
from codecoach.sandbox import run_tests_many


@pytest.fixture(scope="module")
def splits():
    return build_splits(Config())


def test_splits_share_no_problems(splits) -> None:
    seen: set = set()
    for name in SPLIT_NAMES:
        assert not seen & set(splits.problems[name]), f"{name} overlaps an earlier split"
        seen |= set(splits.problems[name])
    assert len(seen) == len(PROBLEMS)  # and nothing is lost


def test_samples_belong_to_their_splits_problems(splits) -> None:
    for name, samples in [("dev", splits.dev), ("meta_dev", splits.meta_dev), ("test", splits.test)]:
        assert {s.problem for s in samples} <= set(splits.problems[name])
    train = set(splits.problems["train"])
    assert {s.problem for s in splits.seed} <= train and {s.problem for s in splits.pool} <= train


def test_every_split_contains_every_class(splits) -> None:
    for samples in (splits.seed, splits.dev, splits.meta_dev, splits.test):
        assert {s.label for s in samples} == set(LABELS)
    assert {s.hidden_label for s in splits.pool} == set(LABELS)


def test_pool_hides_its_label_and_is_disjoint_from_seed(splits) -> None:
    assert all(isinstance(s, PoolSample) and not hasattr(s, "label") for s in splits.pool)
    assert not {s.code for s in splits.seed} & {s.code for s in splits.pool}


def test_every_variant_is_a_real_bug(splits) -> None:
    # Equivalent mutants must have been dropped: each sample FAILS its problem's tests.
    for s in splits.dev + splits.test:
        p = BY_NAME[s.problem]
        norm = normalize_names(p.source)
        assert not run_tests_many([s.code], "f", p.tests)[0].passed, s.edit
        assert s.code != norm


def test_names_are_normalized(splits) -> None:
    for s in splits.seed + splits.dev:
        fn = ast.parse(s.code).body[0]
        assert fn.name == "f"
        assert all(re.fullmatch(r"v\d+", a.arg) for a in fn.args.args)


def test_build_is_reproducible_and_roundtrips(splits, tmp_path) -> None:
    assert build_splits(Config()) == splits  # same seed -> identical data
    save_splits(splits, tmp_path / "s.json")
    assert load_splits(tmp_path / "s.json") == splits
