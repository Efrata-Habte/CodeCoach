"""Page 2: the evolution timeline: every pipeline version tried, accepted or rejected."""
from collections import Counter

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import GREEN, GREY, ORANGE, BLUE, has_results


def timeline_figure(pipes: list, show_meta: bool) -> go.Figure:
    """Dev F1 per generation: accepted = filled green, rejected = hollow grey, plus best-so-far."""
    ev = [v for v in pipes if v.metrics]
    fig = go.Figure()
    hover = lambda vs: [f"{v.id} <- {v.parent_id}<br>{v.edit}<br>{v.reason}" for v in vs]  # noqa: E731
    acc, rej = [v for v in ev if v.accepted], [v for v in ev if not v.accepted]
    fig.add_trace(go.Scatter(x=[v.generation for v in acc], y=[v.metrics["dev_macro_f1"] for v in acc], mode="markers",
                             name="accepted", marker=dict(color=GREEN, size=12), text=hover(acc), hoverinfo="text+y"))
    fig.add_trace(go.Scatter(x=[v.generation for v in rej], y=[v.metrics["dev_macro_f1"] for v in rej], mode="markers",
                             name="rejected", marker=dict(color="rgba(0,0,0,0)", size=12, line=dict(color=GREY, width=2)),
                             text=hover(rej), hoverinfo="text+y"))
    best, run = [], 0.0
    for v in ev:
        run = max(run, v.metrics["dev_macro_f1"]) if v.accepted else run
        best.append(run)
    fig.add_trace(go.Scatter(x=[v.generation for v in ev], y=best, mode="lines", name="best dev F1 so far",
                             line=dict(color=BLUE, width=2, shape="hv")))
    if show_meta:
        fig.add_trace(go.Scatter(x=[v.generation for v in acc], y=[v.metrics["meta_dev_macro_f1"] for v in acc], mode="lines+markers",
                                 name="accepted versions on meta_dev", line=dict(color=ORANGE, width=2)))
    fig.update_layout(xaxis_title="generation", yaxis_title="macro-F1", height=420, margin=dict(t=30))
    return fig


def render(a) -> None:
    st.header("Evolution timeline")
    if not has_results(a):
        return
    pipes = [v for v in a.versions if v.kind == "pipeline"]
    st.plotly_chart(timeline_figure(pipes, st.checkbox("also show meta_dev (never selected on)", value=True)), width="stretch")
    st.subheader("Why versions were rejected")
    reasons = Counter(v.reason.split(":")[0] for v in pipes[1:] if not v.accepted)
    c1, c2 = st.columns([1, 2])
    if reasons:
        c1.bar_chart(pd.Series(reasons, name="count"))
    else:
        c1.write("Nothing rejected yet.")
    c2.caption("unsafe = failed the static check (never run) | crash / timeout / memory = contained by the sandbox | "
               "no_improvement = did not beat its parent by min_delta | duplicate = same code as an earlier version")
    st.subheader("All versions")
    st.dataframe(pd.DataFrame([{"id": v.id, "parent": v.parent_id, "gen": v.generation, "edit": v.edit,
                                "dev F1": None if not v.metrics else round(v.metrics["dev_macro_f1"], 3),
                                "meta_dev F1": None if not v.metrics else round(v.metrics["meta_dev_macro_f1"], 3),
                                "accepted": v.accepted, "reason": v.reason} for v in pipes]), width="stretch", hide_index=True)
