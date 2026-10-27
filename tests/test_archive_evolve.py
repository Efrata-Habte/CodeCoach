"""Archive round-trip, the Level 1 loop (with a fake evaluator), and the real isolated evaluator."""
import importlib.util
import random
from dataclasses import replace
from pathlib import Path

import pytest

import evolvable.improver as improver
from config import Config
from codecoach import archive as archive_mod
from codecoach import safety
from codecoach.archive import Archive, Version
from codecoach.code_editor import normalize_source
from codecoach.evaluator import EvalOutcome, evaluate_pipeline
from codecoach.utils import ROOT

BASE = normalize_source((ROOT / "evolvable" / "pipeline.py").read_text(encoding="utf-8"))
HAS_DATA = (ROOT / "data" / "generated" / "verdicts.json").exists()


def _load_script():
    """scripts/02_evolve.py has a digit-first name, so import it by path."""
    spec = importlib.util.spec_from_file_location("evolve_script", ROOT / "scripts" / "02_evolve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sandboxed_archive(tmp_path, monkeypatch) -> Archive:
    """An Archive in a temp dir; the write whitelist is pointed at the temp dir too."""
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    monkeypatch.setattr(archive_mod, "ROOT", tmp_path)
    return Archive(tmp_path / "archive")


def _fake_eval(source: str) -> EvalOutcome:
    """Cheap stand-in for the evaluator: more feature calls = better score; one setting 'crashes'."""
    if "CURATION = 'none'" in source:
        return EvalOutcome(False, "crash", detail="boom")
    f1 = 0.30 + 0.04 * source.count("fb.count") + 0.02 * source.count("fb.max") + 0.00001 * len(source) % 0.01
    return EvalOutcome(True, "ok", {"dev_macro_f1": f1, "meta_dev_macro_f1": f1})


def _baseline(arch: Archive, evaluate=_fake_eval) -> None:
    out = evaluate(BASE)
    arch.add(Version("v000", "pipeline", None, "baseline", "baseline", True, "baseline", 0, out.metrics), BASE)


# ---- archive ------------------------------------------------------------------------------------------
def test_archive_roundtrip_lineage_and_model_handling(sandboxed_archive, tmp_path) -> None:
    arch = sandboxed_archive
    _baseline(arch)
    model = tmp_path / "archive" / "_tmp" / "m.pt"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"weights")
    arch.add(Version("v001", "pipeline", "v000", "rule_based", "edit A", True, "accepted", 1, {"dev_macro_f1": 0.5}),
             BASE + "\n# a", model)
    rejected_model = tmp_path / "archive" / "_tmp" / "r.pt"
    rejected_model.write_bytes(b"weights")
    arch.add(Version("v002", "pipeline", "v001", "rule_based", "edit B", False, "no_improvement", 2, {"dev_macro_f1": 0.1}),
             BASE, rejected_model)
    again = Archive(tmp_path / "archive")  # reload from disk
    assert [v.id for v in again.versions] == ["v000", "v001", "v002"]
    assert [v.id for v in again.lineage("v002")] == ["v000", "v001", "v002"]
    assert [v.id for v in again.accepted()] == ["v000", "v001"]
    assert again.source("v001").endswith("# a\n") and again.get("v002").accepted is False
    assert (tmp_path / "archive" / "v001" / "model.pt").read_bytes() == b"weights"   # accepted keeps weights
    assert not (tmp_path / "archive" / "v002" / "model.pt").exists() and not rejected_model.exists()
    assert again.next_id("pipeline") == "v003" and again.next_id("improver") == "improver_v000"


def test_archive_cannot_write_outside_archive_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(safety, "ROOT", tmp_path)
    arch = Archive(tmp_path / "elsewhere")  # a directory that is NOT <ROOT>/archive
    with pytest.raises(PermissionError):
        arch.add(Version("v000", "pipeline", None, "baseline", "baseline", True, "baseline", 0), BASE)


# ---- the Level 1 loop (fake evaluator) -------------------------------------------------------------------
def test_loop_records_everything_and_gate_is_applied(sandboxed_archive) -> None:
    arch, script = sandboxed_archive, _load_script()
    _baseline(arch)
    cfg = replace(Config(), generations=25, patience=100)
    script.run_level1(cfg, arch, improver, _fake_eval, random.Random(0), log=lambda s: None)
    assert len(arch.versions) == 26                      # baseline + one record per generation, accepted or not
    reasons = {v.reason.split(":")[0] for v in arch.versions[1:]}
    assert reasons <= {"accepted", "no_improvement", "duplicate", "unsafe", "crash"}
    for v in arch.versions[1:]:
        parent = arch.get(v.parent_id)
        assert parent.accepted                           # only accepted versions become parents
        if v.accepted:                                   # the gate: beat the PARENT by min_delta
            assert v.metrics["dev_macro_f1"] >= parent.metrics["dev_macro_f1"] + cfg.min_delta
        elif v.reason == "no_improvement":
            assert v.metrics["dev_macro_f1"] < parent.metrics["dev_macro_f1"] + cfg.min_delta
    assert any(v.accepted for v in arch.versions[1:]) and any(not v.accepted for v in arch.versions[1:])


def test_loop_is_deterministic_for_a_seed(tmp_path, monkeypatch) -> None:
    edits = []
    for run in ("a", "b"):
        monkeypatch.setattr(safety, "ROOT", tmp_path / run)
        arch = Archive(tmp_path / run / "archive")
        _baseline(arch)
        _load_script().run_level1(replace(Config(), generations=8, patience=100), arch, improver, _fake_eval,
                                  random.Random(5), log=lambda s: None)
        edits.append([(v.edit, v.reason) for v in arch.versions])
    assert edits[0] == edits[1]


def test_unsafe_child_is_rejected_without_being_evaluated(sandboxed_archive) -> None:
    arch, calls = sandboxed_archive, []
    _baseline(arch)

    class Evil:  # an improver that proposes a file importing os
        choose_parent = staticmethod(lambda pool, rng: "v000")
        propose_child = staticmethod(lambda src, rng: ("import os\n" + src, "evil edit"))

    _load_script().run_level1(replace(Config(), generations=2), arch, Evil, lambda s: calls.append(s) or _fake_eval(s),
                              random.Random(0), log=lambda s: None)
    # unsafe children are never evaluated, so they are not remembered as 'seen': the repeat is flagged unsafe again
    assert [v.reason.split(":")[0] for v in arch.versions[1:]] == ["unsafe", "unsafe"]
    assert calls == [] and "import os" in arch.versions[1].reason


def test_crashing_child_is_rejected_and_loop_continues(sandboxed_archive) -> None:
    arch = sandboxed_archive
    _baseline(arch)

    class Crashy:
        choose_parent = staticmethod(lambda pool, rng: "v000")
        propose_child = staticmethod(lambda src, rng: (src.replace("CURATION = 'dedup_cap'", "CURATION = 'none'"), "swap"))

    _load_script().run_level1(replace(Config(), generations=2), arch, Crashy, _fake_eval, random.Random(0),
                              log=lambda s: None)
    assert arch.versions[1].reason == "crash" and arch.versions[1].accepted is False
    assert len(arch.versions) == 3  # the second try was a duplicate; nothing aborted


def test_loop_stops_when_search_stalls(sandboxed_archive) -> None:
    arch = sandboxed_archive
    _baseline(arch, lambda s: EvalOutcome(True, "ok", {"dev_macro_f1": 0.5, "meta_dev_macro_f1": 0.5}))
    flat = lambda s: EvalOutcome(True, "ok", {"dev_macro_f1": 0.5, "meta_dev_macro_f1": 0.5})  # noqa: E731
    _load_script().run_level1(replace(Config(), generations=30, patience=4), arch, improver, flat, random.Random(0),
                              log=lambda s: None)
    assert len(arch.versions) == 1 + 4  # stopped by patience, not by the generation budget


def test_tamper_error_aborts_the_run(sandboxed_archive) -> None:
    _baseline(sandboxed_archive)

    def tampered(source: str) -> EvalOutcome:
        raise safety.TamperError("protected files changed: ['codecoach/verifier.py']")

    with pytest.raises(safety.TamperError):
        _load_script().run_level1(replace(Config(), generations=3), sandboxed_archive, improver, tampered,
                                  random.Random(0), log=lambda s: None)


# ---- the real evaluator (isolated child process) ------------------------------------------------------------
needs_data = pytest.mark.skipif(not HAS_DATA, reason="run scripts/01_generate_data.py first")


@needs_data
def test_real_evaluator_scores_baseline_and_keeps_protected_files_untouched() -> None:
    before = safety.protected_hashes()
    out = evaluate_pipeline(BASE, replace(Config(), eval_timeout_s=120))
    assert out.ok and 0.0 <= out.metrics["dev_macro_f1"] <= 1.0 and "meta_dev_macro_f1" in out.metrics
    assert out.metrics["rounds"] and out.model_path.exists()
    out.model_path.unlink()
    safety.assert_unchanged(before)


@needs_data
@pytest.mark.parametrize("body,reason", [
    ("    return [1 / 0]", "crash"),
    ("    return [len([0] * (10 ** 11))]", "memory"),
])
def test_real_evaluator_reports_crash_and_memory(body, reason) -> None:
    bad = BASE.replace("return [fb.count_comparisons(code), fb.count_range_calls(code), fb.count_subscripts(code)]",
                       body.strip())
    assert bad != BASE, "replace matched nothing: the test would evaluate the unmodified baseline"
    assert safety.check(bad).ok  # passes the STATIC check, so the runtime containment is what is tested
    out = evaluate_pipeline(bad, replace(Config(), eval_timeout_s=120))
    assert not out.ok and out.reason == reason


@needs_data
def test_real_evaluator_kills_an_infinite_loop() -> None:
    target = "    layers, width = ([], input_dim)"  # ast.unparse adds the parentheses
    bad = BASE.replace(target, "    while True:\n        pass\n" + target)
    assert bad != BASE, "replace matched nothing: the test would evaluate the unmodified baseline"
    assert safety.check(bad).ok
    out = evaluate_pipeline(bad, replace(Config(), eval_timeout_s=10))  # imports take ~4s; the loop never ends
    assert not out.ok and out.reason == "timeout"
