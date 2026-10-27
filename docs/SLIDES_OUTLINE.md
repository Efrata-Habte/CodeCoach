# Slides outline (20 minutes: 3 problem/design, 5 method, 5 results and demo, 2 limits, plus questions)

| # | Slide | Time | Say | Figure / app page |
|---|---|---|---|---|
| 1 | **Problem: misconceptions, not bugs** | 1:30 | Beginners repeat the same mistakes; we predict *which misconception* (5 classes). One sentence: bounded, sandboxed recursive self-improvement; unrestricted RSI is not demonstrated. | a buggy `find_max` snippet |
| 2 | **Design: three levels + distillation** | 1:30 | Level 0 weights, Level 1 source code, Level 2 the improver itself, then a tiny student. Everything judged by a fixed evaluator. | app page 1 (flow diagram) |
| 3 | **The independent verifier** | 2:00 | "A model agreeing with itself is not proof; executable tests are." Fix + hidden tests; never sees confidence or the label. Measured false-accept 0.6%. | `self_training_rounds.png` (low raw accuracy, 100% precision) |
| 4 | **Level 0: verified self-training with gate and rollback** | 1:30 | Teacher labels, verifier filters, a copy trains, dev gate accepts or rolls back. | app page 5 |
| 5 | **Level 1: the system edits its own source** | 2:00 | AST edit operators, static check, isolated evaluator, archive of every version; show a real 2-line diff. | `evolution_timeline.png`; app page 3 |
| 6 | **Level 2: the improver edits itself** | 1:30 | STOP-style utility on a separate split (`meta_dev`). Result: 0 of 7 proposals accepted; in every judged check old and new utility were equal: a null result. | `improver_utility.png` |
| 7 | **Results: what worked and what did not** | 3:00 | Dev +0.173 but meta_dev +0.049; across 3 seeds meta_dev mean -0.004. Verifier ablation: meta_dev 0.553 vs 0.250. Failure analysis: dev gate selects noise. | `verifier_ablation.png`, `version_vs_parent_best.png` |
| 8 | **Distillation** | 2:00 | Loss with T and T^2, alpha = 1 is the baseline. Students 18x smaller, 2x faster at equal F1; distillation not significantly better than hard labels. | `student_comparison.png` |
| 9 | **Live demo** | 2:00 | See script below. | app pages 3, 6, 7 |
| 10 | **Limits and what is next** | 2:00 | Bounded edit space, small synthetic data, noise floor, tests define correctness, final hand-written test (state its result if you ran it). | app page 9 |

## 2-minute live demo script (web app, already running with results loaded)
1. **(0:00) Page 3 "Version vs previous version".** Pick an accepted version (v006 or v009): "Here is exactly what the system changed in its own source" (the diff), the F1 deltas
   against its parent, and the per-class bars. Mention the parent's meta_dev next to the dev gain.
2. **(0:40) Page 7 "Try it".** Example `find_max: loop stops one early`. Show the models' probability bars, then "Check the diagnosis": the verifier confirms a repair passes the tests.
   Click **Start a weak learner**, pick the true class, **Verify my label**, add 2-3 snippets, **Retrain now**: show before/after F1 and the gate's verdict (a rollback is a
   valid, honest result: explain that one example rarely moves dev F1).
3. **(1:30) Page 6 "Distillation".** Click **Train the students now**: watch the two loss curves, then compare F1 / size / latency; then point to the precomputed 3-seed table.
4. If time is short or something is slow, show page 8 (Level 0 rounds streaming) or the saved figures instead.

Backup: `python run_all.py --quick --clean` (about 3 min) regenerates everything; start the app with `python -m streamlit run app/streamlit_app.py`.

## Questions to rehearse (answers in `docs/WALKTHROUGH.md`)
Why can't the system edit the evaluator? Why a separate meta_dev? Is this real recursive self-improvement? What stops reward hacking? What does alpha = 1 do? Why split by problem?
Why did Level 2 not help? Why does the dev gain not carry over to meta_dev?
