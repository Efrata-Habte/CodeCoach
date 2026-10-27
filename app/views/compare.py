"""Page 3 (the key page): pick a version and see exactly what changed compared with its PARENT."""
import plotly.graph_objects as go
import streamlit as st
from common import BLUE, ORANGE, SHORT, has_results, source_diff

from codecoach.misconceptions import LABELS


def confusion_figure(cm: list, title: str) -> go.Figure:
    names = [SHORT[c] for c in LABELS]
    fig = go.Figure(go.Heatmap(z=cm, x=names, y=names, text=cm, texttemplate="%{text}", colorscale="Blues", showscale=False))
    fig.update_layout(title=title, height=330, margin=dict(t=40, b=10), yaxis=dict(autorange="reversed"),
                      xaxis_title="predicted", yaxis_title="true")
    return fig


def render(a) -> None:
    st.header("Version vs previous version")
    if not has_results(a):
        return
    pipes = [v for v in a.versions if v.kind == "pipeline" and v.parent_id]
    if not pipes:
        st.info("Only the baseline exists so far: there is no parent to compare with.")
        return
    latest = next((v for v in reversed(pipes) if v.accepted), pipes[-1])
    choice = st.selectbox("Version", [v.id for v in pipes], index=[v.id for v in pipes].index(latest.id),
                          format_func=lambda i: f"{i}  ({'accepted' if a.get(i).accepted else 'rejected'}): {a.get(i).edit[:60]}")
    child, parent = a.get(choice), a.get(a.get(choice).parent_id)
    st.markdown(f"**{child.id}** <- parent **{parent.id}** | proposer: `{child.proposer}` | edit: `{child.edit}` | "
                f"decision: **{'ACCEPTED' if child.accepted else 'rejected: ' + child.reason}**")
    if not child.metrics:
        st.warning(f"{child.id} was never evaluated ({child.reason}); only its source diff is available.")
    else:
        pm, cm = parent.metrics, child.metrics
        cols = st.columns(5)
        for col, (label, key, fmt) in zip(cols, [("dev F1", "dev_macro_f1", "{:.3f}"), ("meta_dev F1", "meta_dev_macro_f1", "{:.3f}"),
                                                 ("params", "n_params", "{:,.0f}"), ("train time (s)", "train_time_s", "{:.1f}"),
                                                 ("verified pseudo-labels", "n_verified", "{:.0f}")]):
            col.metric(label, fmt.format(cm[key]), f"{cm[key] - pm[key]:+.3g}", delta_color="off" if key in ("n_params", "train_time_s") else "normal")
        fig = go.Figure([go.Bar(name=parent.id, x=[SHORT[c] for c in LABELS], y=[pm["per_class_f1"][c] for c in LABELS], marker_color=BLUE),
                         go.Bar(name=child.id, x=[SHORT[c] for c in LABELS], y=[cm["per_class_f1"][c] for c in LABELS], marker_color=ORANGE)])
        fig.update_layout(barmode="group", title="Per-class dev F1: parent vs child", height=340, margin=dict(t=40))
        st.plotly_chart(fig, width="stretch")
        c1, c2 = st.columns(2)
        c1.plotly_chart(confusion_figure(pm["confusion"], f"{parent.id} (parent): dev confusion"), width="stretch")
        c2.plotly_chart(confusion_figure(cm["confusion"], f"{child.id}: dev confusion"), width="stretch")
    st.subheader("What the system changed in its own source")
    st.code(source_diff(a.source(parent.id), a.source(child.id), f"{parent.id}/pipeline.py", f"{child.id}/pipeline.py"), language="diff")
    if st.checkbox("Walk the lineage (baseline -> ... -> this version)"):
        chain = a.lineage(child.id)
        st.table([{"step": v.id, "edit": v.edit, "dev F1": round(v.metrics["dev_macro_f1"], 3) if v.metrics else None,
                   "meta_dev F1": round(v.metrics["meta_dev_macro_f1"], 3) if v.metrics else None} for v in chain])
