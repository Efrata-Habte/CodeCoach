"""The final-test script must refuse to run by accident. (These tests never run the real evaluation.)"""
import importlib.util
import subprocess
import sys

from codecoach.utils import ROOT

SCRIPT = ROOT / "scripts" / "04_final_test.py"


def test_refuses_without_final_flag_and_writes_nothing() -> None:
    existed = (ROOT / "results" / "FINAL_TEST_DONE").exists()
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode != 0 and "REFUSED" in (r.stderr + r.stdout) and "--final" in (r.stderr + r.stdout)
    assert (ROOT / "results" / "FINAL_TEST_DONE").exists() == existed  # the refusal changed nothing


def test_evaluate_models_reports_metrics_for_any_predictor() -> None:
    spec = importlib.util.spec_from_file_location("final_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = [{"name": "last", "label": "WRONG_INDEX", "code": "def last(xs):\n    return xs[len(xs)]\n", "tests": [(([1, 2],), 2)]},
             {"name": "first", "label": "WRONG_INDEX", "code": "def first(xs):\n    return xs[1]\n", "tests": [(([5, 6],), 5)]}]
    out = module.evaluate_models({"perfect": lambda codes: ["WRONG_INDEX"] * len(codes),
                                  "wrong": lambda codes: ["LOGIC_OPERATOR"] * len(codes)}, cases)
    assert out["perfect"]["accuracy"] == 1.0 and out["perfect"]["verified_fix_rate"] == 1.0
    assert out["wrong"]["accuracy"] == 0.0 and out["wrong"]["verified_fix_rate"] == 0.0  # wrong class -> no fix found
