"""Every edit operator must give parseable, DIFFERENT, safe source that still runs."""
import importlib.util
import random

import pytest

from codecoach import code_editor as ce
from codecoach.safety import check
from codecoach.utils import ROOT

BASE = ce.normalize_source((ROOT / "evolvable" / "pipeline.py").read_text(encoding="utf-8"))


def _import(source: str, tmp_path, name: str):
    """Import a candidate pipeline from a file, the way the evaluator will."""
    path = tmp_path / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("op", sorted(ce.PIPELINE_OPERATORS))
def test_operator_gives_different_safe_runnable_source(op, tmp_path) -> None:
    produced = 0
    for seed in range(25):
        res = ce.PIPELINE_OPERATORS[op](BASE, random.Random(seed), 0.3)
        if res is None:
            continue
        new, desc = res
        assert new != BASE and desc.startswith(op)
        assert check(new).ok, (desc, check(new).reasons)
        mod = _import(new, tmp_path, f"cand_{op}_{seed}")
        assert len(mod.extra_features("def f(v1):\n    return v1[0] < 1")) >= 1
        assert mod.build_teacher(10, 5) is not None
        produced += 1
    assert produced >= 5, f"{op} almost never applies"


def test_tweak_constant_respects_bounds_and_keeps_ints_int() -> None:
    src = BASE
    for seed in range(200):  # many repeated edits must never leave the allowed range
        res = ce.tweak_constant(src, random.Random(seed), 0.9)
        if res:
            src = res[0]
    ns: dict = {}
    exec(src, ns)  # noqa: S102 - our own generated pipeline text
    for name, (lo, hi) in ce.PIPELINE_BOUNDS.items():
        values = ns[name] if isinstance(ns[name], tuple) else [ns[name]]
        assert all(lo <= v <= hi for v in values), name
    assert isinstance(ns["EPOCHS"], int) and isinstance(ns["MAX_FEATURES"], int)
    assert ns["NGRAM_RANGE"][0] <= ns["NGRAM_RANGE"][1]


def test_add_then_remove_feature_changes_the_feature_list() -> None:
    new, desc = ce.add_feature(BASE, random.Random(0), 0.3)
    name = desc.split(": ")[1]
    assert f"fb.{name}(code)" in new and f"fb.{name}(code)" not in BASE
    shorter, desc2 = ce.remove_feature(new, random.Random(1), 0.3)
    assert desc2.startswith("remove_feature") and shorter.count("fb.") == new.count("fb.") - 1


def test_remove_feature_keeps_at_least_one() -> None:
    src = BASE
    for seed in range(20):
        res = ce.remove_feature(src, random.Random(seed), 0.3)
        src = res[0] if res else src
    assert src.count("fb.count") >= 1


def test_change_layer_keeps_1_to_4_valid_layers() -> None:
    src = BASE
    for seed in range(60):
        res = ce.change_layer(src, random.Random(seed), 0.3)
        src = res[0] if res else src
        ns: dict = {}
        exec(src, ns)  # noqa: S102
        assert 1 <= len(ns["HIDDEN_SIZES"]) <= 4 and all(s in ce.LAYER_SIZES for s in ns["HIDDEN_SIZES"])


def test_swap_curation_picks_a_different_allowed_strategy() -> None:
    new, desc = ce.swap_curation(BASE, random.Random(0), 0.3)
    assert "dedup_cap -> " in desc and desc.split("-> ")[1] in ce.CURATION_CHOICES


def test_edits_are_deterministic_for_a_seed() -> None:
    assert ce.tweak_constant(BASE, random.Random(7), 0.3) == ce.tweak_constant(BASE, random.Random(7), 0.3)


def test_improver_operators_work_on_an_improver_like_file() -> None:
    src = ('OPERATOR_WEIGHTS = {"tweak_constant": 1.0, "add_feature": 1.0}\nEDITS_PER_CHILD = 1\n'
           'PARENT_SELECTION = "tournament"\nTOURNAMENT_K = 3\nSTEP_SCALE = 0.3\n')
    seen = set()
    for seed in range(40):
        for op in ce.IMPROVER_OPERATORS.values():
            res = op(src, random.Random(seed), 0.3)
            if res:
                seen.add(res[1].split(":")[0])
                assert res[0] != ce.normalize_source(src)
    assert seen == {"tweak_constant", "swap_parent_selection"}
