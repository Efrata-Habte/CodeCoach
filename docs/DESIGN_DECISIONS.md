# Design Decisions Log

A running log of *why* the project is built the way it is. One section per build step,
appended as we go. Each decision uses the same format:

- **Decision**: what we did
- **Alternative**: what we could have done instead
- **Why (intuition)**: the reasoning in plain language
- **Evaluator might ask**: a likely question, with a short answer

---

## Step 1: Foundation (folders, config, utils)

Files: `config.py`, `codecoach/utils.py`, `requirements.txt`, `.gitignore`, folder skeleton.

### 1.1 Keep the "fixed" code and the "editable" code in different folders

- **Decision**: three separate zones.
  - `codecoach/`, `config.py`, `data/`, `tests/` are the **fixed zone**. The system never edits them.
  - `evolvable/` is the **only editable zone**. It holds the two files the system rewrites.
  - `archive/` is where the system **writes** new versions. It is output, not code.
- **Alternative**: one flat package where any file could be edited.
- **Why (intuition)**: think of a student, an exam and a grader. If the student can edit the
  grader, the student can give themselves 100%. Self-improving systems fail this way in
  practice. This is called *reward hacking*: the system finds that cheating the measurement
  is easier than improving. We make cheating structurally impossible by physically
  separating what is being improved (`evolvable/`) from what measures it (`codecoach/`).
  The folder layout is the first guard-rail. Later steps (`safety.py`) enforce it.
- **Evaluator might ask**: *"What stops the system from changing its own evaluator?"* The
  evaluator lives outside `evolvable/`. The whitelist only allows edits inside `evolvable/`,
  and file hashes are checked before and after every run.

### 1.2 One `Config` dataclass for every setting

- **Decision**: all seeds, budgets and thresholds live in `config.py`, in one dataclass.
- **Alternative**: constants scattered through each script, or command-line flags only.
- **Why (intuition)**: two reasons.
  1. **Honest experiments.** If a gate threshold (e.g. `min_delta = 0.005`) were buried in
     five places, it would be easy to nudge one "just to get a nicer result" without
     noticing. One file means one place to audit, and the report can say "all settings are
     in config.py".
  2. **Explainability.** You will be asked "why 0.005?" or "why 3 seeds?". One file is one
     place to point at.
- **Evaluator might ask**: *"Did you tune thresholds until results looked good?"* No. They
  are set once here, and any change is visible in git history.

### 1.3 `frozen=True`: and what it does NOT protect

- **Decision**: the dataclass is frozen, so `cfg.seed = 5` raises an error.
- **Alternative**: a normal mutable dataclass or a plain dict.
- **Why (intuition)**: it stops *accidents*. Without it, one function could quietly change a
  threshold mid-run and every later step would silently use the changed value. To "change" a
  setting you must build a new config (`dataclasses.replace`), which is explicit and visible.
- **Honest limit**: `frozen` is **not a security boundary**. Code running in the same Python
  process could still bypass it. The real protection against a malicious or buggy edit is
  built later: the AST static check (forbids `open`, `exec`, `os`...), running candidates in
  a separate subprocess, and SHA-256 tamper detection. Do not claim `frozen` makes the
  system safe. It is a seatbelt, not a vault.

### 1.4 What each setting group is for (the plain-language meaning)

| Group | Settings | Intuition |
|---|---|---|
| Gate (Level 0) | `min_delta`, `max_class_drop`, `max_bad_rounds` | A new model must be *clearly* better (`min_delta`) and must not wreck any one class (`max_class_drop`), or we roll back. `min_delta` exists because F1 on a small dev set is noisy, so a +0.0001 "gain" is just luck. Stopping after 2 bad rounds in a row avoids wasting budget. |
| Evolution (Level 1/2) | `generations`, `improver_every`, `improver_budget`, `patience` | The search budget. The budget is capped so the loop always terminates, which is itself a safety property. |
| Safety limits | `eval_timeout_s`, `eval_memory_mb` | A candidate pipeline is *code we did not write*. It might loop forever or eat all RAM, so it gets a time and memory cap. |
| Ablation switches | `ablate_level2`, `ablate_verifier` | These let the same code run the "without X" experiment. A claim like "the verifier helps" is only credible if you also ran the system **without** it. |
| Distillation | `temperature`, `alpha`, `*_grid`, `student_hidden` | `alpha=1` means pure hard labels (no distillation), so it doubles as the baseline. |
| LLM | `use_llm`, `max_llm_calls` | Off by default. The project must work with no API key and no internet. |

### 1.5 `--quick` mode changes budgets, never logic

- **Decision**: `get_config(quick=True)` only shrinks numbers (fewer variants, 6 generations
  instead of 20). It does not switch code paths.
- **Alternative**: a separate "demo mode" with simplified or mocked logic.
- **Why (intuition)**: if quick mode ran different code, a passing quick test would tell you
  nothing about the real run. Same logic and smaller numbers means a quick pass is a
  meaningful smoke test, and the live demo shows the real system, not a fake.
- **Evaluator might ask**: *"Is your demo real or pre-computed?"* It runs the same code as
  the full run, with a smaller budget.

### 1.6 `set_seed` seeds three libraries and pins torch to one thread

- **Decision**: one helper seeds `random`, `numpy` and `torch`, and calls
  `torch.set_num_threads(1)`.
- **Alternative**: seed only what you think you use.
- **Why (intuition)**: randomness hides in many places (shuffling data, weight
  initialisation, dropout, sampling). If even one source is unseeded, "re-running gives the
  same numbers" is false. Reproducibility is a grading requirement, so we seed everything,
  in one function nobody can forget to call fully.
  The single thread is for **latency measurement** later. With multiple threads, timing
  varies with whatever else the laptop is doing, which makes the "CPU latency over 3 seeds"
  table noisy. Single-threaded timing is slower in absolute terms but repeatable, and
  repeatable is what a comparison needs.
- **Honest limit**: this gives reproducibility on *one machine*. Bit-identical results across
  different CPUs or torch versions are not guaranteed. This goes in the limitations section.

### 1.7 SHA-256 helpers live in `utils.py` now, before they are used

- **Decision**: `sha256_text` / `sha256_file` are written in Step 1 although nothing uses them yet.
- **Why (intuition)**: two later features need hashing, and both depend on it being exact:
  - the **sandbox cache** (same code + same tests = same result, so skip re-running);
  - **tamper detection** (hash every protected file before and after a run; any difference
    means something modified the evaluator, so abort).
  Writing it once avoids two slightly different implementations.

### 1.8 `ROOT` is computed from the file's location, not the working directory

- **Decision**: `ROOT = Path(__file__).resolve().parent.parent`.
- **Alternative**: relative paths like `"data/generated"`.
- **Why (intuition)**: relative paths mean "relative to wherever I launched Python". The same
  code would work from the project folder and break from `scripts/` or from Streamlit.
  Anchoring to the file's own location makes every path correct no matter where you run from.
  This matters because candidate pipelines run in subprocesses, possibly with a different
  working directory.

### 1.9 `.gitignore` excludes generated data and the archive

- **Decision**: `data/generated/` and `archive/` are not committed.
- **Why (intuition)**: the rubric says data must be **regenerated from code**. If generated
  data is in git, nobody can tell whether it matches the generator. Excluding it forces the
  claim "delete it and `run_all.py` rebuilds it identically" to be true.
  `results/` is also ignored except for a `.gitkeep` placeholder; revisit this when we have
  final numbers worth committing.

### 1.10 Environment note

- `pip.exe` is blocked by an Application Control policy on this machine; use
  `python -m pip install ...` instead.
- Python 3.13.5. Installed: numpy, scikit-learn, torch, matplotlib, pandas, plotly, pytest.
  **Missing: streamlit** (needed from the web-app step).

---

## Step 2: The problem set (`codecoach/problems.py`)

Files: `codecoach/problems.py`, `tests/test_problems.py`. Result: 20 problems, 169 tests.

### 2.1 Tests define "correct", not a human and not the model

- **Decision**: a function is correct if and only if it passes the problem's hidden unit tests.
- **Alternative**: compare to the reference code's text, or ask an LLM/the model to judge.
- **Why (intuition)**: many different programs are correct (`i += 1` vs `i = i + 1`), so text
  comparison would wrongly reject good fixes. A model judging itself is circular. Running code
  on inputs and comparing outputs is objective, and the model cannot argue with it.
  This is the **independent verifier** the rubric demands.
- **Evaluator might ask**: *"What if the tests are incomplete?"* Then a wrong fix could pass.
  This is a stated limitation ("tests define correctness"). The mitigation is the boundary
  tests below.

### 2.2 Every problem has boundary tests, because boundaries are where beginner bugs live

- **Decision**: each problem has 7-10 tests including empty, single element, last element,
  equal values and negative values.
- **Why (intuition)**: take `find_max` with a bug `range(1, len(xs))` -> `range(1, len(xs)-1)`.
  On `[3, 2, 1]` the bug is invisible (the max is first). On `[1, 2, 3]` it is exposed, because
  the last element is skipped. So we deliberately include inputs where each bug *changes the
  answer*. Without them, the bug would still pass the tests: an "equivalent mutant", which
  would be mislabeled as a real bug. The generator (Step 5) throws those away, but good tests
  mean fewer are thrown away.
- A few concrete "bug traps" in the data: `[-5, -2, -9]` catches a wrong initial value of 0
  for max; `[1, 1]` catches `>` vs `>=` in `is_sorted`; `[0, 6]` catches `and` -> `or` in
  `count_in_range`; `[4, 4, 4]` with `t=4` catches `>` vs `>=` in `count_greater`.

### 2.3 Why these functions? Each class of bug needs a place to live

- **Decision**: the 20 functions were chosen so that all 5 misconception classes have several
  places to be injected.
  - `range(...)` loops: almost all -> `OFF_BY_ONE_RANGE`
  - `xs[i]` / `xs[i+1]` / `xs[i-1]`: `is_sorted`, `count_adjacent_equal`, `reverse_list`...
    -> `WRONG_INDEX`
  - `<`, `<=`, `>`, `>=`: `find_max`, `count_greater`, `all_positive`, `binary_search`
    -> `COMPARISON_BOUNDARY`
  - `and` / `or`: `count_in_range`, `contains_both`, `merge_two_sorted`, `count_vowels`
    -> `LOGIC_OPERATOR`
  - accumulators `0`, `1`, `xs[0]`, `-inf`, `-1`: `sum_list`, `factorial`, `find_max`,
    `second_largest`, `last_index_of` -> `WRONG_INITIAL_VALUE`
- **Why (intuition)**: if a class had few host functions, its training data would be tiny and
  repetitive and the classifier would memorise functions instead of learning the pattern.
- We include `while` loops (`binary_search`, `merge_two_sorted`) and a string input
  (`count_vowels`, `is_palindrome`) so the set is not all the same shape.

### 2.4 Tests are plain data: `(args_tuple, expected)`, not code

- **Decision**: `(([1, 2, 3],), 6)` instead of `assert sum_list([1,2,3]) == 6`.
- **Alternative**: write tests as Python functions or `assert` statements.
- **Why (intuition)**: data can be sent into the sandbox subprocess, counted, and printed in a
  report. Test *code* could be tampered with, or hide a bug of its own. Data cannot run
  anything. It also makes "a test that raises an exception counts as a FAIL" a single uniform
  rule.

### 2.5 The function name is read from the source, not typed twice

- **Decision**: `_make()` parses the source with `ast` and takes the name from the `def`.
- **Why (intuition)**: duplicating a name in two places invites a typo that silently breaks one
  problem. Deriving it removes a whole class of bug. `Problem` still stores `name` and
  `func_name`, as the spec requires.

### 2.6 `Problem` is a frozen dataclass; the list is a module constant

- **Decision**: `@dataclass(frozen=True)`, and `PROBLEMS` / `BY_NAME` defined once.
- **Why (intuition)**: same idea as Step 1: the answer key must not be changed by accident
  during a run. (Same honest caveat: this is a seatbelt, not a vault. The hash check on
  `codecoach/` files is the real guard.)

### 2.7 Validating the answer key: what the test found

- **Decision**: `tests/test_problems.py` runs every reference solution against its own tests
  in-process.
- **Why (intuition)**: if a reference solution fails its own test, *every* downstream number
  is garbage, and you would not know why. A 0.02 s test removes that doubt up front.
  In-process `exec` is acceptable here because it is our own trusted code. Anything the model
  or the improver produces will only ever run in the sandbox (Step 4).
- **What happened**: all 20 reference solutions passed. My generic "every problem has a
  boundary test" check failed for `second_largest`, which is correct: it needs at least 2
  elements, so a 1-element input is invalid. We fixed the *test* with an explicit,
  commented exemption (`NEEDS_TWO_ELEMENTS`). The rule stays strict for everyone else. This is
  the right kind of fix: keep the rule, name the exception.
- **Note on file length**: the spec asks for files under about 200 lines. `problems.py` is
  longer because it is data (20 solutions + 169 tests), not logic. The module docstring says so.

### 2.8 Known weaknesses of this design (for the limitations section)

- Tests were written by us, so they reflect our idea of "boundary". A real bug outside our
  tests would pass undetected.
- Only 20 small functions: the classifier may learn *these* functions' templates rather than
  general misconception patterns. That is why splits are **by problem** (Step 5): the model is
  evaluated on functions it never saw.
- `average` tests compare floats with `==`; this is safe only because the values are exactly
  representable (e.g. 2.5). Do not add tests like `0.1 + 0.2`.
- `second_largest` counts duplicates (`[5,5,3]` -> 5). That is a definition choice, not the
  only valid one; it is documented by its tests.

---

<!-- Next entry: Step 3: misconceptions.py -->
