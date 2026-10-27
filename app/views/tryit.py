"""Page 7: Try it. Paste a buggy function, compare the models, check the diagnosis with the verifier, and watch a weak
learner LEARN from verified snippets in real time (retrain + dev gate + rollback)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import AQUA, BLUE, GREEN, ORANGE, RED, SHORT, best_version, has_results, is_single_function

import live_logic as ll
from codecoach.misconceptions import LABELS
from codecoach.problems import BY_NAME

EXAMPLES = {
    "find_max: loop stops one early": ("find_max", "def find_max(xs):\n    best = xs[0]\n    for i in range(1, len(xs) - 1):\n        if xs[i] > best:\n            best = xs[i]\n    return best\n"),
    "is_sorted: >= instead of >": ("is_sorted", "def is_sorted(xs):\n    for i in range(len(xs) - 1):\n        if xs[i] >= xs[i + 1]:\n            return False\n    return True\n"),
    "sum_list: starts at 1": ("sum_list", "def sum_list(xs):\n    total = 1\n    for i in range(len(xs)):\n        total += xs[i]\n    return total\n"),
    "count_in_range: or instead of and": ("count_in_range", "def count_in_range(xs, lo, hi):\n    count = 0\n    for i in range(len(xs)):\n        if xs[i] >= lo or xs[i] <= hi:\n            count += 1\n    return count\n"),
    "reverse_list: wrong index": ("reverse_list", "def reverse_list(xs):\n    result = []\n    for i in range(len(xs) - 1, -1, -1):\n        result.append(xs[i - 1])\n    return result\n"),
    "median (from the slides; no tests)": ("(none)", "def median(xs):\n    ys = sorted(xs)\n    n = len(ys)\n    if n % 2 == 1:\n        return ys[n // 2 + 1]\n    return (ys[n // 2 - 1] + ys[n // 2]) / 2\n"),
}


@st.cache_resource(show_spinner="Loading models (first time only)...")
def _env(best_id: str) -> dict:
    from config import Config
    from codecoach.archive import Archive, import_source
    a = Archive()
    splits, verdicts = ll.load_data()
    return {"handles": ll.load_handles(a, best_id), "pipe": import_source(a.source(best_id), "tryit_pipe"),
            "splits": splits, "cfg": Config()}


def prob_chart(name: str, diag: dict, truth: str | None) -> go.Figure:
    colors = [GREEN if lab == diag["label"] else BLUE for lab in LABELS]
    fig = go.Figure(go.Bar(x=[SHORT[c] for c in LABELS], y=[diag["probs"][c] for c in LABELS], marker_color=colors))
    fig.update_layout(title=f"{name}: {SHORT[diag['label']]}", height=260, margin=dict(t=40, b=10), yaxis=dict(range=[0, 1]), showlegend=False)
    return fig


def live_learning(env: dict, normalized: str, problem, current: dict) -> None:
    st.subheader("Learn from this snippet, live")
    st.caption("A weak learner starts with ONLY the 30 labeled seed examples. Tell it the true class: the verifier checks your label "
               "against the hidden tests; verified snippets enter a buffer; a candidate is retrained and must pass the same dev gate "
               "as in Level 0, otherwise it is rolled back. (The gate is strict: one snippet rarely moves dev F1, so try several.)")
    if "learner" not in st.session_state:
        if st.button("Start a weak learner (seed examples only)"):
            with st.spinner("training..."):
                st.session_state.learner = ll.new_live_learner(env["pipe"], env["splits"], env["cfg"])
            st.rerun()
        return
    learner = st.session_state.learner
    before = ll.diagnose(learner["teacher"], normalized)
    c1, c2, c3 = st.columns(3)
    c1.metric("learner dev macro-F1", f"{learner['dev']['macro_f1']:.3f}")
    c2.metric("verified snippets in buffer", len(learner["buffer"]))
    c3.metric("learner says", SHORT[before["label"]])
    label = st.selectbox("True class of this snippet", LABELS, index=LABELS.index(before["label"]), format_func=lambda x: SHORT[x])
    if st.button("Verify my label and add to the buffer"):
        if problem is None:
            st.warning("Pick a problem (hidden tests) above: without tests nothing can be verified.")
        else:
            res = ll.check_fix(normalized, label, problem)
            if res["verified"]:
                learner["buffer"].append((normalized, label))
                st.success(f"Verified: a {SHORT[label]} repair makes all tests pass. Added to the buffer.")
            else:
                st.error(f"Rejected by the verifier ({res['note']}): not used for training.")
    if learner["buffer"] and st.button("Retrain now (the dev gate decides)"):
        with st.spinner("retraining a candidate..."):
            out = ll.retrain_with_buffer(learner, env["pipe"], env["splits"], env["cfg"])
        after = ll.diagnose(learner["teacher"], normalized)
        verdict = "ACCEPTED: the candidate replaced the learner" if out["accepted"] else f"ROLLED BACK ({out['reason']}): the learner is unchanged"
        (st.success if out["accepted"] else st.warning)(f"{verdict}. dev F1 {out['dev_before']:.3f} -> {out['dev_after']:.3f}")
        st.write(f"Prediction for this snippet: **{SHORT[before['label']]}** -> **{SHORT[after['label']]}**")
    if learner["history"]:
        st.dataframe(pd.DataFrame(learner["history"]), width="stretch", hide_index=True)
    if st.button("Reset learner"):
        del st.session_state["learner"]
        st.rerun()


def render(a) -> None:
    st.header("Try it")
    if not has_results(a):
        return
    best = best_version(a)
    name = st.selectbox("Example", list(EXAMPLES))
    default_problem, default_code = EXAMPLES[name]
    code = st.text_area("Buggy Python function (one function, any names)", default_code, height=230, key=f"code_{name}")
    names = ["(none)"] + sorted(BY_NAME)
    problem_name = st.selectbox("Hidden tests of problem", names, index=names.index(default_problem))
    if not is_single_function(code):
        st.warning("Paste exactly one function definition.")
        return
    env = _env(best.id)
    normalized, problem = ll.snippet_problem(code, None if problem_name == "(none)" else problem_name)
    if problem is not None:
        st.write("The pasted code **passes** the hidden tests." if ll.tests_pass(normalized, problem) else "The pasted code **fails** the hidden tests (it has a bug).")
    diags = {n: ll.diagnose(h, normalized) for n, h in env["handles"].items()}
    cols = st.columns(len(diags))
    for col, (n, d) in zip(cols, diags.items()):
        col.plotly_chart(prob_chart(n, d, None), width="stretch")
    pick = st.selectbox("Check the diagnosis of", list(diags), index=1)
    res = ll.check_fix(normalized, diags[pick]["label"], problem)
    if res["verified"]:
        st.success(f"Verified: a {SHORT[diags[pick]['label']]} repair makes every test pass ({res['note']}).")
    elif res["verified"] is False:
        st.error(f"Not verified ({res['note']}): no {SHORT[diags[pick]['label']]} repair passes the tests, so this diagnosis would be rejected.")
    else:
        st.info(res["note"])
    if res["fixed"]:
        st.code(res["fixed"], language="python")
    live_learning(env, normalized, problem, diags)
