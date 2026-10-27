"""Page 5: Level 0: accepted vs rejected pseudo-labels per round, verifier precision, and the verifier ablation."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import AQUA, GREY, ORANGE, best_version, has_results, read_json


def rounds_figure(rounds: list) -> go.Figure:
    """Stacked bars per round: verified vs rejected (split by reason)."""
    x = [f"round {r['round']}<br>{r['decision']}" for r in rounds]
    fig = go.Figure([go.Bar(name="verified (training data)", x=x, y=[r["n_verified"] for r in rounds], marker_color=AQUA)])
    for reason, shade in (("tests_still_fail", GREY), ("no_repair_applicable", "#bdbcb6"), ("timeout", ORANGE)):
        fig.add_trace(go.Bar(name=f"rejected: {reason}", x=x, y=[r["rejected"].get(reason, 0) for r in rounds], marker_color=shade))
    fig.update_layout(barmode="stack", height=360, margin=dict(t=30), yaxis_title="pool programs")
    return fig


def render(a) -> None:
    st.header("Self-training and the verifier (Level 0)")
    if not has_results(a):
        return
    pick = st.selectbox("Pipeline version", [v.id for v in a.accepted()], index=[v.id for v in a.accepted()].index(best_version(a).id))
    rounds = a.get(pick).metrics["rounds"]
    st.plotly_chart(rounds_figure(rounds), width="stretch")
    st.dataframe(pd.DataFrame([{"round": r["round"], "pool": r["pool_size"], "verified": r["n_verified"],
                                "precision of verified": r["precision"], "teacher raw accuracy": round(r["raw_accuracy"], 2),
                                "dev F1": r.get("dev_f1"), "decision": r["decision"], "reason": r["reason"]} for r in rounds]),
                 width="stretch", hide_index=True)
    st.caption("precision and raw accuracy use the HIDDEN true labels, only for this report; the loop never reads them. "
               "A big gap (low raw accuracy, high precision) is the verifier doing its job.")
    st.subheader("Does the verifier matter? (ablation)")
    ab = read_json("ablation_verifier.json")
    if not ab:
        st.info("Not run yet: `python scripts/02_evolve.py --verifier-ablation` (run_all does it).")
        return
    rows = []
    for mode, name in ab["modes"].items():
        vals = ab[mode]
        mean = lambda k: sum(v[k] for v in vals if v[k] is not None) / max(1, sum(v[k] is not None for v in vals))  # noqa: E731
        rows.append({"pseudo-labels from": name, "precision": round(mean("pseudo_label_precision"), 3),
                     "pseudo-labels used": round(mean("n_pseudo"), 1), "dev F1": round(mean("dev_f1"), 3),
                     "meta_dev F1": round(mean("meta_dev_f1"), 3)})
    st.table(pd.DataFrame(rows))
    st.caption(f"Mean over seeds {ab['seeds']} on the baseline and best pipelines.")
