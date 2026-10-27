"""Page 8: Live run: watch Level 0 self-training, or Level 1 self-editing, happen round by round."""
import importlib.util
import shutil

import pandas as pd
import streamlit as st
from common import ROOT, best_version, has_results

from views.selftrain import rounds_figure


def _load_evolve_script():
    spec = importlib.util.spec_from_file_location("evolve_script", ROOT / "scripts" / "02_evolve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def level0(a) -> None:
    from config import get_config
    from codecoach.archive import import_source
    import live_logic as ll
    from codecoach.self_training import self_train
    st.write("Level 0 on the chosen pipeline: the teacher diagnoses the pool, the verifier filters, a candidate is trained, the dev gate "
             "accepts or rolls back. Each round appears the moment it finishes.")
    which = st.radio("Pipeline", ["v000", best_version(a).id], horizontal=True)
    seed = st.number_input("seed", 0, 99, 0)
    if not st.button("Run self-training"):
        return
    splits, verdicts = ll.load_data()
    pipe = import_source(a.source(which), f"live_{which}")
    chart, table, status = st.empty(), st.empty(), st.empty()
    rounds: list[dict] = []

    def on_round(r: dict) -> None:
        rounds.append(r)
        chart.plotly_chart(rounds_figure(rounds), width="stretch")
        table.dataframe(pd.DataFrame([{"round": x["round"], "verified": x["n_verified"], "precision": x["precision"], "dev F1": x.get("dev_f1"),
                                       "decision": x["decision"], "reason": x["reason"]} for x in rounds]), width="stretch", hide_index=True)

    status.info("running...")
    res = self_train(pipe, splits, get_config(quick=True), int(seed), verdicts, on_round=on_round)
    status.success(f"Done in {res.train_time_s:.1f}s: dev macro-F1 {res.initial_dev['macro_f1']:.3f} (seed only) -> {res.final_dev['macro_f1']:.3f}. "
                   f"{res.n_verified} verified pseudo-labels kept.")


def level1(a) -> None:
    import random
    from dataclasses import replace
    from codecoach.archive import Archive, Version, import_source
    from codecoach.code_editor import normalize_source
    from codecoach.evaluator import evaluate_pipeline
    from config import get_config
    st.write("Level 1: the improver rewrites the pipeline's own source; each child is scored by the fixed evaluator in an isolated process "
             "(about 6 s each). Written to `archive/live/`, never to the main archive.")
    gens = st.slider("generations", 2, 6, 3)
    if not st.button("Run self-editing live"):
        return
    script = _load_evolve_script()
    cfg = replace(get_config(quick=True), generations=gens)
    live_dir = ROOT / "archive" / "live"
    shutil.rmtree(live_dir, ignore_errors=True)  # our own scratch folder from an earlier live run
    arch = Archive(live_dir)
    imp_src = normalize_source((ROOT / "evolvable" / "improver.py").read_text(encoding="utf-8"))
    arch.add(Version("improver_v000", "improver", None, "baseline", "baseline", True, "baseline", 0), imp_src)
    base = normalize_source((ROOT / "evolvable" / "pipeline.py").read_text(encoding="utf-8"))
    with st.spinner("evaluating the baseline..."):
        out = evaluate_pipeline(base, cfg)
    if not out.ok:
        st.error(f"baseline failed: {out.reason} {out.detail}")
        return
    script.record(arch, out, base, None, "baseline", 0, True, "baseline", "baseline")
    table, status = st.empty(), st.empty()
    rows = [{"version": "v000", "edit": "baseline", "dev F1": round(out.metrics["dev_macro_f1"], 3), "decision": "baseline"}]

    def on_event(e: dict) -> None:
        v = e["version"]
        rows.append({"version": v["id"], "edit": v["edit"], "dev F1": None if not v["metrics"] else round(v["metrics"]["dev_macro_f1"], 3),
                     "decision": "ACCEPTED" if v["accepted"] else f"rejected: {v['reason']}"})
        table.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    table.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    status.info("evolving...")
    script.run_level1(cfg, arch, import_source(imp_src, "live_improver"), lambda s: evaluate_pipeline(s, cfg), random.Random(cfg.seed),
                      log=lambda s: None, on_event=on_event)
    status.success("Done. The versions are in `archive/live/` (diffs and metrics included); the main archive was not touched.")


def render(a) -> None:
    st.header("Live run")
    if not has_results(a):
        return
    t0, t1 = st.tabs(["Level 0: watch self-training", "Level 1: watch the system edit its own code"])
    with t0:
        level0(a)
    with t1:
        level1(a)
