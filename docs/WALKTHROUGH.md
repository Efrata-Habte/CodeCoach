# Read the repo in one day (about 8 hours)

Each block says what to open, what to run, and the questions an evaluator might ask (with short answers).
`docs/DESIGN_DECISIONS.md` has the long "why" for every step; `docs/CONCEPTS.md` maps slide terms to code.

## 1. (30 min) README + ARCHITECTURE
Open `README.md`, `docs/ARCHITECTURE.md`. Run `python run_all.py --quick` once in a terminal while you read.
- **Is this real recursive self-improvement?** No, and we say so: it is *bounded, sandboxed* recursive self-improvement. Only two whitelisted files
  change, through a fixed menu of AST edits with hard bounds, under a fixed evaluator, with rollback. Unrestricted RSI has not been demonstrated.

## 2. (1 h) Problems, misconceptions, verifier
Open `codecoach/problems.py`, `misconceptions.py`, `sandbox.py`, `verifier.py`. Run:
`python -c "from codecoach.problems import BY_NAME; from codecoach.misconceptions import mutate, repair; p=BY_NAME['find_max']; print(mutate(p.source,'OFF_BY_ONE_RANGE')[0])"`
- **Why AST edits and not string replace?** Text replacement would change a `<` inside a string or break `<=`; the AST only holds real operators.
- **Why does a wrong label get rejected?** Only the *predicted* class's repairs are tried; a wrong class usually has no repair that passes the tests (measured false-accept about 1%).
- **What if the tests are incomplete?** Then a wrong fix could pass; "tests define correctness" is a stated limitation. Boundary tests reduce it.

## 3. (1 h) Level 0: verified self-training
Open `codecoach/generator.py` (splits), `self_training.py`, `teacher.py`, `evolvable/pipeline.py`. Run `python scripts/01_generate_data.py`.
- **Why split by problem?** Variants of one function look alike; a random split would test the model on functions it has memorised.
- **Why a gate AND a verifier?** The verifier decides what enters training; the gate decides whether the result is kept. Two layers against self-confirmation.
- **Why is the rollback trivial?** The candidate is a separate copy; the old teacher is only replaced on acceptance.
- **What stops reward hacking in Level 0?** The gate lives in `config.py` (not editable); `effective_min_delta = max(config, pipeline)`, so a self-edit can only make the gate stricter.

## 4. (1.5 h) Level 1: the pipeline file, editor, evaluator, loop
Open `evolvable/pipeline.py`, `codecoach/code_editor.py`, `evaluator.py`, `archive.py`, `scripts/02_evolve.py` (`run_level1`).
Run `python scripts/02_evolve.py --quick` (after clearing `archive/`) and open `archive/index.json`.
- **Why can't the system edit the evaluator?** If it could, it would grade itself (reward hacking). The evaluator lives outside `evolvable/`, the whitelist only lets the system write under `archive/`, and SHA-256 hashes of all fixed files are compared before and after every evaluation.
- **Why compare a child with its parent, not with the best?** It measures what the edit did and keeps weaker lineages explorable; the cost is that small noisy wins can chain (so we confirm on meta_dev and extra seeds).
- **What happens when a child crashes or loops?** It is killed in the isolated child (timeout, memory cap), logged as `crash` / `timeout` / `memory`, and the loop continues.

## 5. (1 h) Level 2 and safety
Open `evolvable/improver.py`, the `Level2` class in `scripts/02_evolve.py`, `codecoach/safety.py`.
- **Why a separate meta_dev split?** The pipeline was selected on dev, so dev scores are optimistic. The improver must be judged on data no pipeline decision used.
- **How is a "better improver" measured?** Old and new improver each propose B edits from the same parent with the same seeds; an edit is worth its meta_dev gain only if it would have passed the dev gate; the new improver is kept only if its utility beats the old one by `min_delta` (STOP).
- **Did Level 2 help?** See the results in `REPORT_DRAFT.md`; the honest expectation is a null result because few edits pass the gate, so utilities often tie at 0.
- **Is the static check enough?** No, it is a first filter; containment comes from the isolated run and the hash check.

## 6. (1 h) Distillation
Open `codecoach/distillation.py`, `scripts/03_distill.py`, `evaluation.py`.
- **What does alpha = 1 do?** The loss becomes plain cross-entropy: no distillation. That is the hard-label baseline, through the same code path.
- **Why T squared?** The KL gradient scales like 1/T^2; multiplying by T^2 keeps it comparable to the CE term.
- **Why is the comparison fair?** All students use the same examples, architecture, epochs and learning rate; only the targets differ. (T, alpha) is chosen on dev; test is only reported.
- **Why can a student beat its teacher here?** It trains on all verified examples while the teacher's set is capped per class; at this scale the capacity gap is small.

## 7. (1 h) Web app + results
Run `python -m streamlit run app/streamlit_app.py`. Visit pages 3 (version vs previous), 5 (verifier ablation), 6 (live distillation), 7 (live learning), 8 (live run).
- **Is the live demo real?** Yes: the same code as the full run with a smaller budget; nothing is pre-computed except the 3-seed tables.
- **Why does "retrain now" sometimes roll back?** The gate is strict on purpose: one snippet rarely moves dev F1 by `min_delta`. A rollback is a legitimate outcome, shown with its reason.

## 8. (1 h) Slides
Use `docs/SLIDES_OUTLINE.md` and the figures in `results/figures/`. Practise the 2-minute live demo script there.

## Extra questions worth rehearsing
- **What did not work?** Two classes (`COMPARISON_BOUNDARY`, `WRONG_INITIAL_VALUE`) stay near F1 = 0 for the early teachers; self-training cannot bootstrap a class it never gets right. Distillation did not beat the hard-label student. Level 2 mostly ties.
- **Why is the confidence baseline weak?** The seed-only teacher is under-confident (max confidence 0.72), so a 0.9 threshold selects nothing; at 0.5 about half of the selected labels are wrong. We report both.
- **What would you do with more time?** More problems and richer bug types, real student code, more seeds, an LLM proposer for open-ended edits, an OS-level sandbox.
