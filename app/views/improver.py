"""Page 4: Level 2, the improver editing ITSELF: utility old vs new, diffs, and the ablation."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import BLUE, ORANGE, has_results, read_json, source_diff


def render(a) -> None:
    st.header("Improver evolution (the recursive step)")
    if not has_results(a):
        return
    st.write("Every K generations the improver proposes an edited copy of **its own source**. Old and new improver each try B "
             "edits from the same parent with the same seeds. The new one is kept only if its edits are worth more on `meta_dev` "
             "(an edit counts only if it would have passed the Level 1 dev gate).")
    imps = [v for v in a.versions if v.kind == "improver"]
    if len(imps) <= 1:
        st.info("No improver proposals yet (Level 2 off, or too few generations).")
    else:
        st.dataframe(pd.DataFrame([{"id": v.id, "parent": v.parent_id, "gen": v.generation, "edit": v.edit, "accepted": v.accepted,
                                    "reason": v.reason, "utility old": None if not v.metrics else round(v.metrics["utility_old"], 4),
                                    "utility new": None if not v.metrics else round(v.metrics["utility"], 4)} for v in imps]),
                     width="stretch", hide_index=True)
        judged = [v for v in imps if v.metrics]
        if judged:
            fig = go.Figure([go.Bar(name="old improver", x=[f"gen {v.generation}" for v in judged], y=[v.metrics["utility_old"] for v in judged], marker_color=BLUE),
                             go.Bar(name="proposed improver", x=[f"gen {v.generation}" for v in judged], y=[v.metrics["utility"] for v in judged], marker_color=ORANGE)])
            fig.update_layout(barmode="group", title="Utility = mean meta_dev gain of the edits kept (B probes, same parent, same seeds)",
                              height=330, margin=dict(t=40))
            st.plotly_chart(fig, width="stretch")
        pick = st.selectbox("Show details and diff for", [v.id for v in imps[1:]])
        v = a.get(pick)
        if v.metrics:
            st.write("Probes of the proposed improver vs the old one:")
            st.dataframe(pd.DataFrame([{"improver": "new", **p} for p in v.metrics["probes"]] +
                                      [{"improver": "old", **p} for p in v.metrics["probes_old"]]), width="stretch", hide_index=True)
        st.code(source_diff(a.source(v.parent_id), a.source(v.id), f"{v.parent_id}/improver.py", f"{v.id}/improver.py"), language="diff")
    st.subheader("Ablation: does editing the improver help?")
    l1, full = read_json("evolution_summary_level1_only.json"), read_json("evolution_summary.json")
    if l1 and full:
        st.table(pd.DataFrame({"Level 1 only": l1, "Level 1 + Level 2": full}).loc[
            ["baseline_dev_f1", "best_dev_f1", "baseline_meta_dev_f1", "best_meta_dev_f1", "n_accepted", "improver_accepted"]])
        st.caption("Same seed and budget. If Level 2 never accepts a new improver, both runs are identical: a null result, reported as is.")
    else:
        st.info("Ablation not run yet: `python scripts/02_evolve.py --quick --no-level2 --tag level1_only` (run_all does it).")
