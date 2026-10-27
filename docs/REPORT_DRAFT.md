# CodeCoach-RSI: bounded, sandboxed recursive self-improvement for diagnosing programming misconceptions

All numbers are from one real run of `python run_all.py --clean --evo-seeds 3` (20.4 min, CPU, this machine). Nothing was tuned after seeing results.

## 1. Problem
Beginners repeat the same mistakes. Given a buggy Python function, predict **which of 5 misconceptions** caused it (off-by-one range, wrong index,
comparison boundary, logic operator, wrong initial value). Research question: *can a system improve its own classifier, then its own improver, under a
fixed independent evaluator, and can the result be compressed?* We say **bounded, sandboxed** recursive self-improvement: unrestricted RSI has not been demonstrated.

## 2. Method
- **Task layer (fixed).** 24 beginner functions with hidden unit tests including boundary cases; AST-based bug injection and matching repair operators; buggy
  variants (plus semantics-preserving style rewrites), equivalent mutants dropped. **Independent verifier:** a diagnosis is accepted only if a repair of the
  predicted class makes all hidden tests pass (it never sees confidence or the true label).
- **Level 0, verified self-training (weights).** Teacher on 30 labeled seeds; each round it diagnoses unlabeled programs, the verifier filters, a copy is trained
  on seed + verified examples and accepted only if dev macro-F1 improves by 0.005 with no class dropping more than 0.10; otherwise rollback.
- **Level 1 (source code).** An improver edits `evolvable/pipeline.py` with AST operators (tweak a bounded constant, add/remove a feature block, change a layer,
  swap the curation strategy). Each child passes a static safety check, runs in an isolated process (timeout, memory cap, SHA-256 tamper check) and is accepted if
  dev F1 beats its parent by 0.005. Every version, accepted or rejected, is archived (Darwin-Godel-Machine style).
- **Level 2 (the improver edits itself).** Old and new improver each propose 3 edits from the same parent with the same seeds; an edit is worth its **meta_dev**
  gain only if it would pass the Level 1 gate; the new improver is kept only if its utility exceeds the old one (STOP-style).
- **Distillation.** Student input-16-5; loss `alpha*CE + (1-alpha)*T^2*KL`; hard-label vs distilled-from-v000 vs distilled-from-best; same examples and budget; (T, alpha) chosen on dev.

## 3. Setup
Splits **by problem**: train 12 problems (30 labeled seed + 172 unlabeled pool), dev 4 (67 samples), meta_dev 4 (62), synthetic test 4 (50); plus a separate hand-written
final test (not yet run). 3 seeds for evolution and distillation. Latency: median of 200 single-sample forward passes, 1 thread. Everything seeded and regenerated from code.

## 4. Results
**Evolution (seed 0):** v000 -> v009 after 19 generations (6 accepted, 11 rejected for no improvement, 2 duplicates, 0 unsafe/crash/timeout/memory):
dev 0.394 -> 0.567, meta_dev 0.536 -> 0.585, synthetic test (3 training seeds) 0.435 +- 0.012 -> 0.513 +- 0.073 (better in 2 of 3 seeds).
**Across 3 evolution seeds** dev gains were +0.173 / +0.041 / +0.007 but meta_dev changes were +0.049 / **-0.070** / +0.009 (mean -0.004): evolution reliably improves the
score it selects on, not reliably the held-out score.
**Level 2:** 0 of 7 proposals accepted over 3 seeds (6 judged, 1 had no applicable edit). In every judged check old and new utility were exactly equal (five at 0.000, one at +0.034),
so "Level 1 only" equals "Level 1 + 2" (null result).
**Verifier ablation** (6 runs per row): verifier precision 1.00 and meta_dev F1 0.553; confidence >= 0.5 precision 0.51 and 0.250; confidence >= 0.9 selects nothing (0.201).
**Distillation** (test, 3 seeds): teacher best 0.513 +- 0.073; students 0.518 +- 0.064 (hard), 0.492 +- 0.087 (from v000), 0.532 +- 0.054 (from best): not significantly different;
students are 12.7K params / 52 KB / 0.017 ms vs 235K / 921 KB / 0.039 ms.

## 5. Failure analysis
- **Dev and meta_dev disagree.** Versions the dev gate *rejected* include some with higher meta_dev than the selected best (0.585): v005 0.699, v016 0.712, v011 0.671; v004 gained
  +0.040 on dev but lost 0.128 on meta_dev. With 6-20 samples per class one prediction moves a class F1 by about 0.1, so the gate partly selects noise.
- **A fragile jump.** In the best version's round 4 only 4 new pseudo-labels moved dev F1 from 0.439 to 0.567 (`COMPARISON_BOUNDARY` 0 -> 0.59 on dev), yet it stays 0.00 on
  meta_dev and test for every model: it was learned for the dev functions, not as a general pattern.
- **Edit types.** Most accepted edits in the main run were feature additions or removals (`count_const_assigns`, `count_plus_minus_one`, `has_while`) and one training-length change; the best teacher's
  `WRONG_INITIAL_VALUE` test F1 rose from 0.00 to 0.39 (we did not isolate which edit caused it). Architecture edits were volatile (dev from 0.077 to 0.48); the one curation swap did not help.
  0 unsafe, crashing, timing-out or memory-hungry children in 40+ attempts across the 3 seeds: the constrained edit space keeps almost every child runnable.
- **Level 2 has almost no signal.** About 1 in 3 pipeline edits passed the dev gate in the main run (6 of 19) and 1 of 11 and 1 of 14 in the other seeds; in every judged Level 2 check the old and new
  improver produced exactly equal utility, because small changes to an operator weight rarely change which edits are drawn from the same random stream.
- **Where the verifier fails.** Wrong label accepted for 0.6% of (program, label) pairs on the pool (4/688), typically a *different valid fix* (e.g. a loop skipping element 0 repaired by
  an initial value). It proves "some class-X fix works", not "the student's mistake was class X". Equivalent mutants (37% of comparison mutants) had to be filtered out.
- **Self-training blind spot.** A class the teacher never gets right never yields verified examples; the confidence baseline fails for the same weak-teacher reason (max confidence 0.72).

## 6. Limitations
Bounded edit space (constrained program search, a small-scale cousin of DGM); tests define correctness and are ours; small synthetic data and templates (24 functions, single-place bugs);
dev-set overfitting from many generations; noise floor about 0.05 F1; one machine, one thread, no cross-machine bit-reproducibility; the static check is a filter, not a proof (containment
is the isolated process + hashes); the Linux/macOS memory cap is untested; the hand-written final test has not been run; distillation conclusions rest on 3 seeds and 50 test programs.
