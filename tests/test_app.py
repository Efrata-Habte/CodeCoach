"""The web app: every page renders without an exception, and the live-learning logic behaves (no browser needed)."""
import sys

import pytest
from streamlit.testing.v1 import AppTest

from codecoach.utils import ROOT

sys.path.insert(0, str(ROOT / "app"))  # for `import live_logic`

HAS_RESULTS = (ROOT / "archive" / "index.json").exists() and (ROOT / "data" / "generated" / "verdicts.json").exists()
needs_results = pytest.mark.skipif(not HAS_RESULTS, reason="run `python run_all.py --quick` first")
APP = str(ROOT / "app" / "streamlit_app.py")
PAGES = ["1. Overview", "2. Evolution timeline", "3. Version vs previous version", "4. Improver evolution (recursive step)",
         "5. Self-training & verifier", "6. Distillation (live)", "7. Try it (live learning)", "8. Live run", "9. Safety & limitations"]


@needs_results
@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_error(page) -> None:
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, [e.value for e in at.exception]


def _overview_page() -> None:
    from common import get_archive
    from views import overview
    overview.render(get_archive())


def test_app_shows_friendly_message_when_nothing_has_been_run(tmp_path, monkeypatch) -> None:
    import common
    monkeypatch.setattr(common, "ROOT", tmp_path)  # an empty project: no archive/ at all
    at = AppTest.from_function(_overview_page, default_timeout=30)
    at.run()
    assert not at.exception and any("run_all.py --quick" in i.value for i in at.info)


# ---- the live features, clicked like a user would ---------------------------------------------------------------------
def _click(at: AppTest, label: str) -> AppTest:
    return next(b for b in at.button if b.label == label).click().run()


def _open(page: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=180).run()
    return at.sidebar.radio[0].set_value(page).run()


@needs_results
def test_live_distillation_trains_two_students_and_reports_a_table() -> None:
    at = _click(_open("6. Distillation (live)"), "Train the students now")
    assert not at.exception, [e.value for e in at.exception]
    assert any("Done" in s.value for s in at.success)
    assert any("hard-label student" in str(t.value) for t in at.table)


@needs_results
def test_live_run_streams_self_training_rounds() -> None:
    at = _click(_open("8. Live run"), "Run self-training")
    assert not at.exception, [e.value for e in at.exception]
    assert any("verified pseudo-labels kept" in s.value for s in at.success)


@needs_results
def test_try_it_learning_flow_start_verify_retrain() -> None:
    at = _click(_open("7. Try it (live learning)"), "Start a weak learner (seed examples only)")
    at = _click(at, "Verify my label and add to the buffer")  # default example = find_max, label = the learner's guess
    assert not at.exception, [e.value for e in at.exception]
    assert at.success or at.error  # the verifier answered either way (verified or rejected)
    if any(b.label == "Retrain now (the dev gate decides)" for b in at.button):
        at = _click(at, "Retrain now (the dev gate decides)")
        assert not at.exception and (at.success or at.warning)  # gate decided: accepted or rolled back


# ---- live-learning logic (Streamlit-free) --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def live():
    import live_logic as ll
    from config import get_config
    from codecoach.archive import Archive, import_source
    from codecoach.verifier import verdict_key
    a = Archive()
    best = max(a.accepted(), key=lambda v: v.metrics["dev_macro_f1"])
    pipe = import_source(a.source(best.id), "test_app_pipe")
    splits, verdicts = ll.load_data()
    cfg = get_config(quick=True)
    return ll, pipe, splits, verdicts, cfg, verdict_key


@needs_results
def test_check_fix_verifies_a_right_label_and_rejects_a_wrong_one(live) -> None:
    ll = live[0]
    code = "def find_max(xs):\n    best = xs[0]\n    for i in range(1, len(xs) - 1):\n        if xs[i] > best:\n            best = xs[i]\n    return best\n"
    normalized, problem = ll.snippet_problem(code, "find_max")
    assert not ll.tests_pass(normalized, problem)
    assert ll.check_fix(normalized, "OFF_BY_ONE_RANGE", problem)["verified"] is True
    assert ll.check_fix(normalized, "LOGIC_OPERATOR", problem)["verified"] is False
    assert ll.check_fix(normalized, "OFF_BY_ONE_RANGE", None)["verified"] is None  # no tests: only an unverified suggestion


@needs_results
def test_live_learner_retrains_through_the_gate_and_rolls_back_when_rejected(live) -> None:
    ll, pipe, splits, verdicts, cfg, verdict_key = live
    learner = ll.new_live_learner(pipe, splits, cfg)
    assert learner["buffer"] == [] and 0.0 <= learner["dev"]["macro_f1"] <= 1.0
    # verified pool snippets (true label confirmed by the verifier), never dev/test data
    verified = [(p.code, p.hidden_label) for p in splits.pool if verdicts[verdict_key(p.code, p.hidden_label)] == "verified"]
    learner["buffer"] += verified[:40]
    old_teacher = learner["teacher"]
    out = ll.retrain_with_buffer(learner, pipe, splits, cfg)
    assert out["n_buffer"] == 40 and learner["history"] == [out]
    if out["accepted"]:
        assert learner["teacher"] is not old_teacher and learner["dev"]["macro_f1"] == out["dev_after"]
    else:  # rollback: the old teacher object is untouched
        assert learner["teacher"] is old_teacher and out["reason"] in ("no_improvement", "class_dropped")
