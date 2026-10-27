"""Page 6: distillation: the rigorous precomputed 3-seed table, and a student you can train LIVE."""
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import BLUE, ORANGE, ROOT, best_version, has_results, read_json


@st.cache_resource(show_spinner="Loading the best teacher and its training examples...")
def _setup() -> dict:
    """Best teacher, the shared training examples (seed + verified), and dev features: built once per session."""
    from codecoach.archive import Archive, import_source
    from codecoach.distillation import shared_examples, teacher_logits
    from codecoach.generator import load_splits
    from codecoach.misconceptions import LABELS
    from codecoach.teacher import load_teacher
    a = Archive()
    best = best_version(a)
    pipe = import_source(a.source(best.id), "live_distill_pipe")
    teacher = load_teacher(pipe, a.root / best.id / "model.pt")
    d = ROOT / "data" / "generated"
    splits, verdicts = load_splits(d / "splits.json"), json.loads((d / "verdicts.json").read_text(encoding="utf-8"))
    codes, labels = shared_examples(teacher, splits, verdicts)
    return {"best": best.id, "teacher": teacher, "X": teacher.featurizer.transform(codes), "codes": codes,
            "y": np.array([LABELS.index(lab) for lab in labels]), "logits": teacher_logits(teacher, codes),
            "Xdev": teacher.featurizer.transform([s.code for s in splits.dev]), "dev_true": [s.label for s in splits.dev],
            "dev_codes": [s.code for s in splits.dev]}


def live_training() -> None:
    from config import Config
    from codecoach.distillation import predict_labels, train_student
    from codecoach.evaluation import classification_report, latency_ms, model_size_kb, n_params
    env, cfg = _setup(), Config()
    st.write(f"Training set: **{len(env['codes'])}** programs (labeled seed + pool items the verifier confirmed for the best teacher "
             f"{env['best']}). Same examples, same budget; only the **targets** differ.")
    c1, c2 = st.columns(2)
    T = c1.slider("Temperature T", 1.0, 6.0, 2.0, 0.5, help="softens the teacher's probabilities")
    alpha = c2.slider("alpha (weight of hard labels)", 0.0, 1.0, 0.3, 0.1, help="alpha = 1 means no distillation")
    if not st.button("Train the students now"):
        return
    chart, status = st.empty(), st.empty()
    curves: dict[str, list] = {"hard-label student (alpha=1)": [], "distilled student": []}

    def draw(_epoch: int, _loss: float) -> None:
        fig = go.Figure([go.Scatter(y=v, name=k, mode="lines", line=dict(color=c, width=2)) for (k, v), c in zip(curves.items(), (BLUE, ORANGE))])
        fig.update_layout(height=300, margin=dict(t=30), xaxis_title="epoch", yaxis_title="training loss", title="Live loss curves")
        chart.plotly_chart(fig, width="stretch")

    rows = {}
    for name, logits, a in (("hard-label student (alpha=1)", None, 1.0), ("distilled student", env["logits"], alpha)):
        status.write(f"Training {name} ...")
        model, _ = train_student(env["X"], env["y"], logits, T, a, cfg.student_hidden, cfg.student_epochs, cfg.student_lr, seed=0,
                                 on_epoch=lambda e, loss, k=name: (curves[k].append(loss), draw(e, loss) if e % 4 == 0 else None))
        draw(0, 0.0)
        rep = classification_report(env["dev_true"], predict_labels(model, env["Xdev"]))
        rows[name] = {"dev macro-F1": round(rep["macro_f1"], 3), "params": n_params(model), "size (KB)": round(model_size_kb(model), 1),
                      "latency (ms)": round(latency_ms(model, env["Xdev"][0], cfg.latency_runs), 4)}
    t = env["teacher"]
    rep = classification_report(env["dev_true"], t.predict(env["dev_codes"])[0])
    rows[f"teacher {env['best']}"] = {"dev macro-F1": round(rep["macro_f1"], 3), "params": t.n_params(), "size (KB)": round(model_size_kb(t.model), 1),
                                      "latency (ms)": round(latency_ms(t.model, env["Xdev"][0], cfg.latency_runs), 4)}
    status.success("Done. This is ONE live run on the dev set; the rigorous 3-seed test table is above.")
    st.table(pd.DataFrame(rows).T)


def render(a) -> None:
    st.header("Distillation: teacher -> tiny student")
    if not has_results(a):
        return
    st.latex(r"L = \alpha\,\mathrm{CE}(y,\,s) + (1-\alpha)\,T^{2}\,\mathrm{KL}\big(\mathrm{softmax}(t/T)\,\|\,\mathrm{softmax}(s/T)\big)")
    st.caption("alpha = 1 means no distillation. The student reads the same features as the best teacher but has one hidden layer of 16 units.")
    d = read_json("distillation.json")
    if not d:
        st.info("Precomputed table missing: run `python scripts/03_distill.py` (run_all does it).")
    else:
        s = d["summary"]
        st.subheader(f"Precomputed result: 3 seeds, best teacher = {d['best_version']}, synthetic test set")
        st.dataframe(pd.DataFrame({m: {"test macro-F1": f"{v['test_macro_f1']['mean']:.3f} +- {v['test_macro_f1']['std']:.3f}",
                                       "params": f"{v['params']['mean']:,.0f}", "size KB": f"{v['size_kb']['mean']:.0f}",
                                       "latency ms": f"{v['latency_ms']['mean']:.3f}"} for m, v in s.items()}).T, width="stretch")
        fig = go.Figure()
        for m, v in s.items():
            fig.add_trace(go.Scatter(x=[v["latency_ms"]["mean"]], y=[v["test_macro_f1"]["mean"]], mode="markers+text", text=[m.replace("_", " ")],
                                     textposition="top center", name=m, showlegend=False,
                                     error_x=dict(type="data", array=[v["latency_ms"]["std"]]), error_y=dict(type="data", array=[v["test_macro_f1"]["std"]]),
                                     marker=dict(size=14 + v["size_kb"]["mean"] ** 0.5, color=BLUE if m.startswith("teacher") else ORANGE)))
        fig.update_layout(xaxis_title="CPU latency per sample (ms)", yaxis_title="test macro-F1", height=420, margin=dict(t=20))
        st.plotly_chart(fig, width="stretch")
        st.caption("Bubble = model size (KB). Blue = teachers, orange = students. Error bars: std over 3 seeds. Read it honestly: "
                   "if distilled and hard-label students overlap within their error bars, distillation did not help at this scale.")
    st.subheader("Train a student live")
    live_training()
