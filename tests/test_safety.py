"""Guard-rail tests: static check, tamper detection, write whitelist, isolated execution."""
import pytest

from codecoach.safety import (TamperError, assert_unchanged, assert_write_allowed, check, protected_hashes,
                              run_isolated)
from codecoach.utils import ROOT

BASELINE = (ROOT / "evolvable" / "pipeline.py").read_text(encoding="utf-8")


def _with(extra: str, where: str = "top") -> str:
    """Baseline pipeline with one extra line, to see whether the check notices it."""
    if where == "top":
        return BASELINE.replace("import random\n", f"import random\n{extra}\n", 1)
    return BASELINE + f"\ndef sneaky():\n    {extra}\n"


def test_baseline_pipeline_passes() -> None:
    report = check(BASELINE)
    assert report.ok, report.reasons


@pytest.mark.parametrize("line,expected", [
    ("import os", "forbidden_import: import os"),
    ("import subprocess", "forbidden_import: import subprocess"),
    ("from os import path", "forbidden_import: from os import path"),
    ("import sklearn", "forbidden_import: import sklearn"),
])
def test_forbidden_imports_are_rejected(line, expected) -> None:
    assert expected in check(_with(line)).reasons


@pytest.mark.parametrize("line,name", [
    ("open('x.txt')", "open"), ("exec('1')", "exec"), ("eval('1')", "eval"),
    ("__import__('os')", "__import__"), ("getattr(0, 'x')", "getattr"),
    ("torch.load('model.pt')", "load"), ("print(splits)", "splits"), ("print(verdicts)", "verdicts"),
])
def test_forbidden_names_are_rejected(line, name) -> None:
    reasons = check(_with(line, where="func")).reasons
    assert any(name in r for r in reasons), reasons


def test_dunder_escape_is_rejected() -> None:
    reasons = check(_with("x = ().__class__.__bases__", where="func")).reasons
    assert any("dunder_access" in r for r in reasons)


def test_code_running_at_import_time_is_rejected() -> None:
    assert any("top_level_code" in r for r in check(BASELINE + "\nfor i in range(3):\n    pass\n").reasons)


def test_missing_interface_and_bad_syntax_are_rejected() -> None:
    assert any("missing_function: curate" in r for r in check(BASELINE.replace("def curate", "def other")).reasons)
    assert any("missing_constant: LR" in r for r in check(BASELINE.replace("LR =", "LEARN =")).reasons)
    assert check("def broken(:").reasons == ["syntax_error"]
    assert check("x = 1\n" * 10_000).reasons == ["too_long"]


def test_improver_kind_has_its_own_rules() -> None:
    assert not check(BASELINE, kind="improver").ok  # pipeline file is not a valid improver


# ---- tamper detection ---------------------------------------------------------------------------
def _tiny_project(tmp_path):
    for d in ("codecoach", "data", "tests", "scripts", "evolvable"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "f.py").write_text("x = 1\n")
    (tmp_path / "config.py").write_text("y = 1\n")
    return tmp_path


def test_unchanged_project_passes_tamper_check(tmp_path) -> None:
    root = _tiny_project(tmp_path)
    assert_unchanged(protected_hashes(root), root)


@pytest.mark.parametrize("victim", ["codecoach/f.py", "data/f.py", "tests/f.py", "config.py", "evolvable/f.py"])
def test_changing_a_protected_file_is_detected(tmp_path, victim) -> None:
    root = _tiny_project(tmp_path)
    before = protected_hashes(root)
    (root / victim).write_text("CHEAT = True\n")
    with pytest.raises(TamperError, match="protected files changed"):
        assert_unchanged(before, root)


def test_new_or_deleted_protected_file_is_detected(tmp_path) -> None:
    root = _tiny_project(tmp_path)
    before = protected_hashes(root)
    (root / "codecoach" / "evil.py").write_text("x = 1\n")
    with pytest.raises(TamperError):
        assert_unchanged(before, root)
    (root / "codecoach" / "evil.py").unlink()
    (root / "tests" / "f.py").unlink()
    with pytest.raises(TamperError):
        assert_unchanged(before, root)


def test_real_project_hashes_are_stable() -> None:
    assert_unchanged(protected_hashes())  # nothing in this test run modifies protected files


# ---- write whitelist ----------------------------------------------------------------------------
def test_only_archive_is_writable() -> None:
    assert_write_allowed(ROOT / "archive" / "v001" / "pipeline.py")
    for bad in ("codecoach/verifier.py", "config.py", "evolvable/pipeline.py", "data/generated/splits.json"):
        with pytest.raises(PermissionError):
            assert_write_allowed(ROOT / bad)
    with pytest.raises(PermissionError):
        assert_write_allowed(ROOT / "archive" / ".." / "config.py")  # path tricks do not escape


# ---- isolated execution -----------------------------------------------------------------------------
def test_isolated_run_returns_output() -> None:
    r = run_isolated(["-c", "print(40 + 2)"], timeout_s=20, memory_mb=1024)
    assert r.ok and r.stdout.strip() == "42"


def test_isolated_run_times_out_on_infinite_loop() -> None:
    r = run_isolated(["-c", "while True: pass"], timeout_s=1.5, memory_mb=1024)
    assert not r.ok and r.reason == "timeout"


def test_isolated_run_stops_runaway_memory() -> None:
    r = run_isolated(["-c", "x = bytearray(1500 * 1024 * 1024); print('allocated')"], timeout_s=30, memory_mb=300)
    assert not r.ok and "allocated" not in r.stdout
