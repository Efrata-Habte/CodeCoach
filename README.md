# CodeCoach-RSI

A classifier that reads a buggy Python function and predicts **which misconception** caused the bug (off-by-one loops, wrong
indices, `<` vs `<=`, `and` vs `or`, wrong initial values), plus a system that improves it in three layers and compresses the result.
Research project for *Emerging AI Paradigms: Recursive Self-Learning & Knowledge Distillation* (iCog Labs).

> **Safety statement.** This is **bounded, sandboxed recursive self-improvement**. The slides note that unrestricted recursive
> self-improvement has not been demonstrated; our system only edits whitelisted files (`evolvable/pipeline.py`, `evolvable/improver.py`),
> through a fixed menu of AST edits with hard bounds, under a fixed external evaluator, with rollback.

## The three layers + distillation

| Layer | What changes | How it is kept honest |
|---|---|---|
| **Level 0: verified self-training** | the model's **weights** | the teacher diagnoses unlabeled bugs; a diagnosis is accepted only if a repair of that class makes the **hidden unit tests** pass; a copy is trained and replaces the teacher only if it passes the dev gate, else rollback |
| **Level 1: self-modifying source** | the pipeline's **own source file** | an improver edits `evolvable/pipeline.py`; a fixed evaluator (isolated process, timeout, memory cap, tamper hashes) scores each version; better ones enter an archive |
| **Level 2: the improver improves itself** | the **improver's source** | it edits `evolvable/improver.py`; kept only if its edits are worth more, on a separate split (`meta_dev`) |
| **Distillation** | model size | best teacher -> tiny student (input-16-5), compared with a hard-label student, 3 seeds |

## Run it

```bash
python -m pip install numpy scikit-learn torch matplotlib pandas streamlit plotly pytest   # once (use python -m pip)
python run_all.py --quick          # about 3 minutes: everything, small budgets (also the live-demo data)
python run_all.py                  # default full run: about 20 minutes on a laptop CPU (measured: 20.4 min)
python -m streamlit run app/streamlit_app.py     # the web app (http://localhost:8501)
python -m pytest tests -q          # tests (1-2 minutes)
```

`python run_all.py --clean --evo-seeds 3` wipes generated data/archive/results first and repeats the evolution with 3 seeds. Only one
`run_all.py` may run at a time (a lock file enforces it): two runs would overwrite each other's data.
Everything runs on CPU with no internet. The hand-written final test is separate and **never part of a normal run** (see below).

## Results (real numbers from `python run_all.py --clean --evo-seeds 3`, seed 0 unless stated)

**Does evolution help?** Best evolved pipeline (v009) vs the baseline (v000):

| | v000 | v009 | change |
|---|---|---|---|
| dev macro-F1 (used to SELECT) | 0.394 | 0.567 | +0.173 (optimistic) |
| meta_dev macro-F1 (never selected on) | 0.536 | 0.585 | +0.049 |
| synthetic test macro-F1, 3 training seeds | 0.435 +- 0.012 | 0.513 +- 0.073 | +0.078 (2 of 3 seeds better) |

**The same experiment with 3 evolution seeds** (honest view of reproducibility):

| Evolution seed | dev v000 -> best | meta_dev v000 -> best | accepted edits |
|---|---|---|---|
| 0 | 0.394 -> 0.567 (+0.173) | 0.536 -> 0.585 (+0.049) | 6 |
| 1 | 0.382 -> 0.423 (+0.041) | 0.518 -> 0.448 (**-0.070**) | 1 |
| 2 | 0.423 -> 0.430 (+0.007) | 0.529 -> 0.538 (+0.009) | 1 |
| mean | +0.074 | **-0.004** | |

Evolution reliably raises the score it selects on (dev) but **does not reliably improve held-out `meta_dev`**: the dev gate partly selects noise.

**Does the improver improve itself (Level 2)?** No: 0 of 7 proposals were accepted over the 3 seeds (6 were judged; 1 had no applicable edit).
In all 6 judged checks the old and the new improver scored **exactly the same utility** (five at 0.000, one at +0.034), because small changes to
an operator weight rarely change which edits get drawn. So "Level 1 only" and "Level 1 + 2" are identical runs. A null result, reported as is.

**Does the verifier matter?** Yes, decisively (baseline + best pipeline x 3 seeds = 6 runs per row):

| Pseudo-labels chosen by | precision of labels used | labels used | final meta_dev F1 |
|---|---|---|---|
| independent verifier | **1.00** | 95 | **0.553** |
| model confidence >= 0.5 | 0.51 | 84 | 0.250 |
| model confidence >= 0.9 | n/a (selects nothing: the weak teacher's max confidence is 0.72) | 0 | 0.201 |

**Distillation** (synthetic test, mean +- std over 3 seeds; best teacher = v009):

| model | test macro-F1 | params | size | CPU latency |
|---|---|---|---|---|
| teacher v000 | 0.435 +- 0.012 | 235,013 | 921 KB | 0.039 ms |
| teacher best | 0.513 +- 0.073 | 235,269 | 922 KB | 0.039 ms |
| student, hard labels | 0.518 +- 0.064 | 12,693 | 52 KB | 0.017 ms |
| student, distilled from v000 | 0.492 +- 0.087 | 12,693 | 52 KB | 0.018 ms |
| student, distilled from best | 0.532 +- 0.054 | 12,693 | 52 KB | 0.018 ms |

The students are about **18x smaller and 2x faster at equal F1**. The three students are **not significantly different** (their error bars
overlap): distillation showed no measurable benefit over hard labels at this data size. Full table: `results/results_table.md`; figures in `results/figures/`.

## Honest limitations

Bounded edit space (constrained program search, not open-ended). Tests define correctness. Small synthetic data (24 functions, 5 classes,
single-place bugs): about 6-20 samples per class per split, so differences below ~0.05 F1 are noise and `COMPARISON_BOUNDARY` stays at F1 = 0 on
meta_dev and test for every model. Dev-set overfitting from many generations. Latency is one CPU, one thread. The Linux/macOS memory cap is untested.
Details: `docs/REPORT_DRAFT.md` and the web app's "Safety & limitations" page.

## The hand-written final test (run once, by you)

`data/handwritten/cases.py` has 25 hand-written buggy functions in a different style. Add 5-10 of your own real mistakes first (instructions in
`data/handwritten/README.md`), validate with `python -m pytest tests/test_handwritten.py`, then run `python scripts/04_final_test.py --final` **once**.
It refuses without `--final` and writes `results/FINAL_TEST_DONE`. **It has not been run.**

## Repository map

```
run_all.py  config.py              one command; ALL settings (seeds, budgets, gate thresholds)
codecoach/                         FIXED library, never edited by the system (problems, mutations, sandbox, verifier,
                                   generator, self_training, evaluator, code_editor, safety, archive, distillation, ...)
evolvable/pipeline.py, improver.py THE ONLY FILES THE SYSTEM MAY EDIT
scripts/01..05_*.py                data, evolve (Level 1 + 2 + ablations), distill, final test, figures
app/                               Streamlit web app (9 pages incl. live learning and live distillation)
data/handwritten/                  final test set (never used for any selection)
archive/  results/                 created by a run: every version, metrics, tables, figures
docs/                              ARCHITECTURE, WALKTHROUGH (one-day reading plan), CONCEPTS, DESIGN_DECISIONS (the long "why"),
                                   REPORT_DRAFT, SLIDES_OUTLINE
tests/                             pytest suite
```

Optional: `pip install anthropic`, set `ANTHROPIC_API_KEY`, and run `python scripts/02_evolve.py --llm` (or `use_llm=True` in `config.py`) to let Claude
(`claude-opus-5-5`) propose every second pipeline edit (`codecoach/llm_proposer.py`, capped by `max_llm_calls`). Its files pass the same safety check,
isolated evaluator and gate as every other edit, and each version records its proposer. Off by default; the project works fully without it. The live
API path was tested only against a fake client (no key was available), so treat it as unverified until you try it once.
