"""Archive round-trip, the Level 1 loop (with a fake evaluator), and the real isolated evaluator."""
import ast
import importlib.util
import random
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

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


# ---- Level 2: the improver edits itself --------------------------------------------------------------------------
IMPROVER_SRC = normalize_source((ROOT / "evolvable" / "improver.py").read_text(encoding="utf-8"))


def _improver_with(weights: dict | None = None, **constants) -> str:
    """The real improver source with some module-level constants replaced (via the AST, like the editor does)."""
    tree = ast.parse(IMPROVER_SRC)
    new = ({"OPERATOR_WEIGHTS": weights} if weights else {}) | constants
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and stmt.targets[0].id in new:
            stmt.value = ast.parse(repr(new[stmt.targets[0].id]), mode="eval").body
    out = ast.unparse(tree)
    assert out != IMPROVER_SRC, "nothing was replaced"
    return out


def _level2_setup(arch: Archive, proposal, cfg=None, evaluate=None):
    """Archive with v000 + improver_v000, a Level2 object, and a stand-in improver whose self-edit is `proposal`."""
    script = _load_script()
    _baseline(arch)
    arch.add(Version("improver_v000", "improver", None, "baseline", "baseline", True, "baseline", 0), IMPROVER_SRC)
    cfg = cfg or replace(Config(), improver_budget=3)
    calls = []
    fn = evaluate or _fake_eval
    level2 = script.Level2(cfg, arch, lambda s: calls.append(s) or fn(s), log=lambda s: None)
    old = SimpleNamespace(choose_parent=improver.choose_parent, propose_child=improver.propose_child,
                          propose_self_edit=lambda src, rng: proposal)
    return level2, old, calls


def test_level2_accepts_an_improver_whose_edits_are_worth_more(sandboxed_archive) -> None:
    better = _improver_with({"add_feature": 1.0})  # only proposes edits the fake evaluator rewards
    level2, old, _ = _level2_setup(sandboxed_archive, (better, "weights: add_feature only"))
    new = level2(3, old)
    rec = sandboxed_archive.get("improver_v001")
    assert rec.accepted and rec.parent_id == "improver_v000" and new is not old
    assert rec.metrics["utility"] > rec.metrics["utility_old"] + Config().min_delta
    assert len(rec.metrics["probes"]) == len(rec.metrics["probes_old"]) == 3
    assert level2.id == "improver_v001" and "add_feature" in sandboxed_archive.source("improver_v001")


def test_level2_rejects_a_worse_improver_and_keeps_the_old_one(sandboxed_archive) -> None:
    worse = _improver_with({"remove_feature": 1.0})  # every edit removes a feature -> never passes the dev gate
    level2, old, _ = _level2_setup(sandboxed_archive, (worse, "weights: remove_feature only"))
    assert level2(3, old) is old
    rec = sandboxed_archive.get("improver_v001")
    assert not rec.accepted and rec.reason == "no_improvement" and level2.id == "improver_v000"
    assert [p["gain"] for p in rec.metrics["probes"]] == [0.0, 0.0, 0.0]


def test_level2_rejects_unsafe_duplicate_and_missing_self_edits_without_evaluating(sandboxed_archive) -> None:
    arch = sandboxed_archive
    level2, old, calls = _level2_setup(arch, ("import os\n" + IMPROVER_SRC, "evil"))
    level2(3, old)
    old.propose_self_edit = lambda src, rng: (IMPROVER_SRC, "no-op")
    level2(6, old)
    old.propose_self_edit = lambda src, rng: None
    level2(9, old)
    assert [v.reason.split(":")[0] for v in arch.versions if v.kind == "improver"][1:] == ["unsafe", "duplicate", "no_edit"]
    assert calls == []  # none of them cost a single pipeline evaluation


def test_parent_selection_edits_are_invisible_to_the_utility_measure(sandboxed_archive) -> None:
    # KNOWN LIMITATION (see DESIGN_DECISIONS 8.4): probes start from a FIXED parent, so choose_parent never runs.
    # An improver differing only in PARENT_SELECTION / TOURNAMENT_K gets exactly the same utility and cannot win.
    level2, old, _ = _level2_setup(sandboxed_archive, (_improver_with(PARENT_SELECTION="best", TOURNAMENT_K=5), "parent sel."))
    level2(3, old)
    rec = sandboxed_archive.get("improver_v001")
    assert rec.metrics["utility"] == rec.metrics["utility_old"] and not rec.accepted


def test_rejected_level2_steps_do_not_disturb_level1(tmp_path, monkeypatch) -> None:
    runs = []
    for name, with_l2 in (("plain", False), ("with_l2", True)):
        monkeypatch.setattr(safety, "ROOT", tmp_path / name)
        monkeypatch.setattr(archive_mod, "ROOT", tmp_path / name)
        arch = Archive(tmp_path / name / "archive")
        level2, old, _ = _level2_setup(arch, None)  # always "no_edit"
        _load_script().run_level1(replace(Config(), generations=8, patience=100, improver_every=2), arch, improver,
                                  _fake_eval, random.Random(4), log=lambda s: None, level2=level2 if with_l2 else None)
        runs.append([(v.edit, v.reason) for v in arch.versions if v.kind == "pipeline"])
    assert runs[0] == runs[1]  # same pipeline trajectory: Level 2 uses its own random numbers


def test_on_event_streams_every_version_and_summary_works(sandboxed_archive) -> None:
    arch, events = sandboxed_archive, []
    level2, old, _ = _level2_setup(arch, (_improver_with({"add_feature": 1.0}), "weights"))
    script = _load_script()
    level2.on_event = events.append
    script.run_level1(replace(Config(), generations=4, patience=100, improver_every=2), arch, improver, _fake_eval,
                      random.Random(1), log=lambda s: None, level2=level2, on_event=events.append)
    assert [e["type"] for e in events].count("pipeline") == 4 and any(e["type"] == "improver" for e in events)
    s = script.summarize(arch)
    assert s["n_generations"] == 4 and s["improver_proposals"] >= 1 and s["final_improver_id"].startswith("improver_v")


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
