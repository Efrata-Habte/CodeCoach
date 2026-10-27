"""Page 1: what the system is, and the headline numbers (v000 vs the best evolved version)."""
import streamlit as st
from common import best_version, has_results, n_features, read_json

FLOW = """digraph G { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef3fb", fontname="Helvetica"];
  seed [label="30 labeled\\nbuggy programs"]; pool [label="unlabeled pool"]; teacher [label="Level 0\\nteacher diagnoses"];
  ver [label="independent verifier\\n(fix + hidden tests)", fillcolor="#e5f5e9"]; gate [label="dev gate\\naccept / rollback"];
  pipe [label="Level 1\\nedits pipeline.py", fillcolor="#fdeee7"]; imp [label="Level 2\\nedits improver.py", fillcolor="#fdeee7"];
  dist [label="distillation\\ntiny student", fillcolor="#f3eefb"];
  seed -> teacher; pool -> teacher; teacher -> ver -> gate -> teacher [label="verified only"];
  pipe -> teacher [label="new code"]; imp -> pipe [label="how to edit"]; imp -> imp [label="edits itself"]; gate -> dist [label="best teacher"]; }"""


def render(a) -> None:
    st.title("CodeCoach-RSI")
    st.write("A classifier that reads a buggy Python function and says **which misconception** caused the bug, and a system that "
             "improves it three ways, under a fixed external evaluator.")
    c = st.columns(3)
    c[0].markdown("**Level 0: verified self-training.** The model labels unlabeled bugs; only labels the *verifier* confirms "
                  "(a matching fix makes hidden tests pass) become training data. Changes **weights**. Gate + rollback.")
    c[1].markdown("**Level 1: self-modifying source.** An improver rewrites the pipeline's own source file; a fixed evaluator "
                  "scores each version; better ones enter an archive. Changes **code**.")
    c[2].markdown("**Level 2: the improver improves itself.** It edits its own file; kept only if it improves pipelines more "
                  "than before, on a separate split (`meta_dev`). Changes **the improver**.")
    st.graphviz_chart(FLOW)
    if not has_results(a):
        return
    base, best = a.get("v000"), best_version(a)
    dist = (read_json("distillation.json") or {}).get("summary")
    st.subheader(f"Baseline v000 vs best evolved version {best.id}")
    m = st.columns(5)
    m[0].metric("dev macro-F1", f"{best.metrics['dev_macro_f1']:.3f}", f"{best.metrics['dev_macro_f1'] - base.metrics['dev_macro_f1']:+.3f}")
    m[1].metric("meta_dev macro-F1", f"{best.metrics['meta_dev_macro_f1']:.3f}",
                f"{best.metrics['meta_dev_macro_f1'] - base.metrics['meta_dev_macro_f1']:+.3f}")
    if dist:
        t0, tb = dist["teacher_v000"]["test_macro_f1"]["mean"], dist["teacher_best"]["test_macro_f1"]["mean"]
        m[2].metric("synthetic test F1 (3 seeds)", f"{tb:.3f}", f"{tb - t0:+.3f}")
    else:
        m[2].metric("synthetic test F1", "n/a", help="run scripts/03_distill.py")
    m[3].metric("structural features", n_features(a.source(best.id)), n_features(a.source(best.id)) - n_features(a.source("v000")))
    m[4].metric("parameters", f"{best.metrics['n_params']:,}", f"{best.metrics['n_params'] - base.metrics['n_params']:+,}", delta_color="off")
    st.caption("dev was used to SELECT the best version, so its gain is optimistic. meta_dev and the 3-seed synthetic test are "
               "never selected on: trust those more. Small gains are within noise at this data size.")
