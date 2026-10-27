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

Files: `codecoach/problems.py`, `tests/test_problems.py`. Result at this step: 20 problems, 169 tests.
(Step 5 later added 4 more comparison-heavy problems: now 24. See 5.11.)

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

## Step 3: Misconceptions (`codecoach/misconceptions.py`)

Files: `codecoach/misconceptions.py`, `tests/test_misconceptions.py` (164 lines + 4 tests).

### 3.1 Edit the AST, never the text

- **Decision**: parse with `ast`, change one node, convert back with `ast.unparse`.
- **Alternative**: `source.replace("<", "<=")`.
- **Why (intuition)**: text replacement does not know what code *is*. It would change a `<`
  inside a string or comment, turn `<=` into `<==`, or hit `range` in a variable name. The AST
  only contains real operators and calls, so every edit is a real, syntactically valid change.
  It is the difference between find-and-replace in a text editor and a refactoring tool.
- **Side effect to know**: `ast.unparse` rewrites formatting (quotes become `'`, comments
  disappear). So we compare programs with `normalize()` (parse then unparse) and never raw text.

### 3.2 An `Edit` = description + a function that applies it

- **Decision**: every possible change is an `Edit(description, apply)`. `mutate` and `repair`
  both do the same thing: list all edits, apply **each one separately to a fresh copy** of the
  tree, unparse.
- **Alternative**: apply all changes at once, or write one big function per class.
- **Why (intuition)**: think of a list of "things you could change here". Applying one at a
  time gives one bug per variant, and the description ("range stop -1 (line 3)") is a free
  human-readable log for the web app and the failure analysis. A fresh tree per edit matters
  because `apply` changes the tree in place: without that, edit 2 would stack on top of edit 1.

### 3.3 One edit = one bug (single-cause variants)

- **Decision**: each variant has exactly one injected bug, and each repair candidate changes
  exactly one place.
- **Why (intuition)**: the classifier's job is "which misconception caused this?". With two
  bugs in one function the answer is ambiguous, and the repair would need to fix both at once.
  Single-cause keeps the label well-defined. Real students often have several bugs, which is a
  stated limitation.

### 3.4 Repair is NOT the exact inverse, and that is the point

- **Decision**: repair tries a *superset* of the fixes (for `range`: stop +-1 and start +-1;
  for initial values: 6 standard values). It does not know which edit was injected.
- **Why (intuition)**: at diagnosis time we only have the buggy code and a predicted label, not
  the history. A real teacher would say "your loop bound looks wrong" and try the usual fixes.
  The tests decide which, if any, works. If repair were a perfect undo, the verifier would be
  cheating by knowing the answer.
- **The test that proves coverage**: `test_every_mutation_can_be_undone_by_its_own_repair`
  checks that for every bug we can inject, the original program is among the repair candidates.
  If this failed, the verifier would reject *correct* diagnoses and we would not know why.

### 3.5 Symmetric classes reuse one function for bug and fix

- **Decision**: `WRONG_INDEX`, `COMPARISON_BOUNDARY` and `LOGIC_OPERATOR` use the same edit list
  for `mutate` and `repair`. Flipping `<` to `<=` is its own undo; `and` -> `or` likewise.
- **Why (intuition)**: less code and no chance that the bug operator and the fix operator drift
  apart. `OFF_BY_ONE_RANGE` and `WRONG_INITIAL_VALUE` are asymmetric (many fixes per bug), so they
  have separate functions.

### 3.6 `_shift`: arithmetic that keeps code readable

- **Decision**: shifting an index by +1 simplifies when it can: `n - 1` + 1 gives `n`, and
  `i - 1` + 1 gives `i`.
- **Why (intuition)**: otherwise the bug `range(n)` -> `range(n - 1)` and a fix would produce
  `n - 1 + 1`, which is correct but looks nothing like a student's code and would never compare
  equal to the original. Realistic-looking code matters because the classifier reads the text.
  (Spotted detail: Python parses `-1` as unary-minus applied to `1`, not as the number -1, so
  `_int_value` handles that case explicitly.)

### 3.7 The `not` toggle is applied to every `if` and `while`

- **Decision**: `LOGIC_OPERATOR` includes wrapping/unwrapping `not` on conditions, as the spec asks.
- **Honest consequence**: nearly every function has an `if`, so this operator can break almost
  any function (`if not xs[i] > best`). It models "inverted condition" mistakes but is a blunt
  tool. Many of those bugs are very different in style from `and`/`or` confusion, so
  `LOGIC_OPERATOR` is a mixed class. Worth mentioning in the limitations.

### 3.8 What the demo showed (real output)

- Injecting into `find_max`: `range(1, len(xs))` -> `range(1, len(xs) - 1)`. The buggy code
  fails the tests (last element skipped).
- Of 4 repair candidates for `OFF_BY_ONE_RANGE`, **exactly one** passes (`stop +1`). The same bug
  with the *wrong* label (`COMPARISON_BOUNDARY`) has **no** passing repair. This is the core
  mechanism of the verifier in one example: a wrong diagnosis cannot be "fixed" by the wrong
  kind of repair.
- Mutants available per class (before the equivalent-mutant filter of Step 5):

  | Class | Mutants | Problems hosting it |
  |---|---|---|
  | OFF_BY_ONE_RANGE | 36 | 18 |
  | WRONG_INDEX | 74 | 19 |
  | COMPARISON_BOUNDARY | 16 | 9 |
  | LOGIC_OPERATOR | 27 | 16 |
  | WRONG_INITIAL_VALUE | 16 | 14 |

### 3.9 Open issue to handle in Step 5: class imbalance

- `WRONG_INDEX` (74) dwarfs `COMPARISON_BOUNDARY` and `WRONG_INITIAL_VALUE` (16 each). If we
  feed everything in, the model could score well just by favouring the big class, and
  **macro-F1** (which treats classes equally) would expose it.
- Planned fix (in the generator, not here): cap or sample the same number of variants per
  problem and class (`variants_per_problem` in `config.py`), and report per-class F1. The
  imbalance is a property of the *code*, not something to hide: report the class counts per
  split, as the spec requires.

### 3.10 Tests written here and what they do NOT cover

- Checked: every class applies to at least 3 problems; mutants parse and differ from the
  original; every mutant is undoable by its own repair; no two classes produce identical buggy
  text (otherwise a label would be ambiguous). That last one passed, which was not guaranteed.
- **Not yet checked**: that mutants actually *fail the tests* and repairs *pass them*. That
  needs the sandbox (Step 4), because running mutated code in-process is unsafe. The demo above
  used a throwaway in-process runner on one trusted function only. The full test comes with the
  sandbox.

---

## Step 4: Sandbox and verifier (`codecoach/sandbox.py`, `codecoach/verifier.py`)

Files: `sandbox.py`, `verifier.py`, `tests/test_sandbox_verifier.py` (+ `test_timeout_s` in `config.py`).

### 4.1 Run candidate code in a child process, with a timeout

- **Decision**: each run is `python -I -c <runner>` as a subprocess. Code and tests go in as JSON on
  stdin and a JSON result comes out on stdout. `subprocess.run(timeout=...)` kills the child.
- **Alternative**: `exec()` in our own process, or a thread with a timeout.
- **Why (intuition)**: a bug like `while True` never returns. In our own process it would freeze the
  whole experiment, and Python cannot reliably kill a thread. A child process is disposable: we kill
  it, write down "timeout", and move on. A crash or `exit()` inside it also cannot hurt us.
- **Honest limit**: this is isolation and a time limit, **not a security jail**. It does not block
  file or network access. That is acceptable here because candidates come from our own AST edits;
  the self-edited source files get a separate static check in `safety.py` (Step 8). Also, Windows has
  no `resource` module, so there is no memory cap at this level.

### 4.2 Data in, result out: nothing is trusted from the child

- **Decision**: the child prints one JSON line; the parent parses it. If it is missing or garbled
  (child died), the result is `error`. `print()` calls inside the candidate are swallowed so they cannot
  corrupt the output.
- **Why (intuition)**: the child is the untrusted party. The parent should never assume it behaved.

### 4.3 What counts as "passing", exactly

- **Decision**: a test passes only if the function returns a value `==` to the expected one **and** the
  bool-ness matches. An exception counts as a fail. Inputs are deep-copied per test.
- **Why (intuition)**: in Python `1 == True`, so a function returning `1` would pass a test that expects
  `True`. That is a real, silent hole, so we close it (there is a test). Deep-copying stops a buggy function
  that modifies its list from corrupting the next test.

### 4.4 Four outcomes, not two: `ok`, `tests_failed`, `timeout`, `error`

- **Decision**: the sandbox keeps the *reason* for failing.
- **Why (intuition)**: later we have to report **why** pseudo-labels were rejected (stacked bars per round,
  failure analysis). Throwing the reason away now would make that impossible. A timeout (infinite loop) and
  a wrong answer are different kinds of failure.

### 4.5 Cache by hash of (source, function name, tests)

- **Decision**: results are stored in an in-memory dict keyed by SHA-256. Cached call: 0.00005 s; real call:
  about 0.035 s.
- **Why (intuition)**: the same code with the same tests always gives the same answer, so running it twice is
  waste. Self-training will verify thousands of candidates, and many repeat across rounds and generations.
- **Known gap**: the cache lives only for one process. The evaluator (Step 7) runs each pipeline version in
  its own subprocess, so those runs will not share it. If runtime becomes a problem we will add an on-disk
  cache. Not done yet, because we should measure before optimising.

### 4.6 Run the repair candidates in parallel

- **Decision**: `run_tests_many` uses a thread pool (up to 8 workers). Each thread just waits for a child
  process, so the GIL is no problem.
- **Why (intuition)**: to *reject* a diagnosis we must try every repair of that class (up to a few dozen).
  In parallel the wall-clock time is about one test run instead of many. Accepting stops being cheaper
  only in the rare case where the first repair works.

### 4.7 The verifier's inputs are deliberately poor

- **Decision**: `verify(buggy_source, predicted_label, problem)`. It never receives the model's confidence
  or the true label.
- **Why (intuition)**: independence. If the verifier looked at confidence, "the model is sure" would leak
  into "the model is right", which is exactly the self-confirmation failure we are fighting. The signature
  makes cheating impossible by construction, not by promise. Only the **predicted** class's repairs are
  tried, so a wrong label usually finds no working fix.

### 4.8 Rejection reasons are logged

- `no_repair_applicable` (e.g. predicted `COMPARISON_BOUNDARY` but the code has no comparison),
  `tests_still_fail`, `timeout` (every candidate timed out). Reported per round in Level 0.

### 4.9 Measured results (real numbers, from this run)

Full guarantee test: every one of the 154 real bugs (mutants that fail the tests) is accepted when verified
with its own label. Then, for each of those bugs, I verified it against each of the 4 **wrong** labels:

| True class | Mutants | Equivalent (pass tests) | Wrong label wrongly accepted |
|---|---|---|---|
| OFF_BY_ONE_RANGE | 36 | 1 | 3 / 140 (2%) |
| WRONG_INDEX | 74 | 7 | 3 / 268 (1%) |
| COMPARISON_BOUNDARY | 16 | 6 | 0 / 40 |
| LOGIC_OPERATOR | 27 | 0 | 1 / 108 (1%) |
| WRONG_INITIAL_VALUE | 16 | 1 | 0 / 60 |
| **Overall** | 169 | 15 | **1.1%** |

Rejections of wrong labels: 461 `tests_still_fail`, 148 `no_repair_applicable`.

What this tells us:
- **The verifier is strict, not perfect**: about 1% false accepts on this synthetic data. It is a measured
  property to report, not a guarantee. "Verifier precision" in the Level 0 logs will measure it the same way,
  from the hidden true-label column.
- **Why a wrong label can be accepted**: the verifier proves "*some* class-X fix makes the tests pass",
  not "the student's mistake was class X". Example: `OFF_BY_ONE_RANGE -> WRONG_INITIAL_VALUE` (2 cases): a
  loop that skips element 0 can also be repaired by starting the accumulator at `xs[0]`. Both programs are
  correct as far as the tests can tell. So a "wrong" accept is sometimes a legitimate alternative fix. For
  teaching, a *useful* diagnosis, but the label differs from what we injected.
- **Equivalent mutants are common for one class**: 6 of 16 `COMPARISON_BOUNDARY` mutants (37%) pass all tests
  (e.g. `<` vs `<=` in `find_max` does not change the result, because ties do not matter). They are not bugs,
  so the generator must drop them (Step 5). After dropping: 10 `COMPARISON_BOUNDARY`, 15 `WRONG_INITIAL_VALUE`,
  35 `OFF_BY_ONE_RANGE`, 67 `WRONG_INDEX`, 27 `LOGIC_OPERATOR`. The class imbalance from Step 3.9 gets
  worse before it gets better, and the small classes are small.
- **Confirms a Step 2/3 design choice**: boundary tests are what make most mutants detectable (only 15 of
  169 escape).

### 4.10 Tests and runtime

15 tests in 13.5 s. They cover: references pass, infinite loop times out, exception = fail, syntax error =
error, cache hit, bool/int strictness, "label with nothing to repair is rejected", and the
mutate -> fail -> repair -> pass loop over every problem and class. Step 3's open question is answered: mutants
really fail the tests and repairs really fix them.

---

## Step 5: Dataset and splits (`codecoach/generator.py`, `scripts/01_generate_data.py`)

Files: `generator.py`, `styles.py`, `01_generate_data.py`, `tests/test_generator.py`, `tests/test_styles.py`,
plus `split_sizes` / `min_seed_per_class` / `min_class_per_split` in `config.py`. Output: `data/generated/splits.json` (git-ignored).

### 5.1 Split by problem, not by sample

- **Decision**: whole *functions* go to train, dev, meta_dev or test (10 / 4 / 3 / 3 problems).
- **Alternative**: shuffle all buggy variants and cut 70/15/15.
- **Why (intuition)**: ten variants of `find_max` look nearly the same. A random cut puts some in train and
  some in test, so the model gets "tested" on a function it has memorised. Its score would measure memory, not
  understanding of the misconception. Splitting by problem means test functions are strangers.

### 5.2 Why there are four splits (one purpose each)

| Split | Used for | Why it must be separate |
|---|---|---|
| seed | the only labeled training data | simulates "few labels" |
| pool | unlabeled code the teacher diagnoses | the true label is kept as `hidden_label`, only for measuring verifier precision afterwards |
| dev | Level 0 gates and Level 1 fitness | needed to choose between versions |
| meta_dev | **only** accepts/rejects improver edits (Level 2) | if the improver were judged on dev, it would learn to please dev (the data the pipeline was already tuned on) |
| test | final tables | touched last, never used to choose anything |

Selection pressure "uses up" a split: whatever you choose on, you overfit to. So every decision level
gets its own data.

### 5.3 The pool's label is hidden by the *type*, not by a promise

- **Decision**: pool items are `PoolSample(code, problem, hidden_label)`. Labeled data are
  `Sample(code, problem, label, edit)`. A test checks the pool has no `.label` attribute.
- **Why (intuition)**: self-training must never peek at true labels. If both used the same class with a
  `label` field, one careless line `s.label` would leak the answer and nobody would notice. With a
  different type and an ugly name (`hidden_label`), a leak has to be written on purpose and stands out in review.
  The pool also drops `edit`, which would reveal the label too.

### 5.4 Equivalent-mutant filter

- **Decision**: after injecting, run every candidate through the sandbox; keep only those that **fail**
  the tests. (15 of 169 were dropped, 37% of one class: see Step 4.)
- **Why (intuition)**: an "equivalent mutant" behaves like the correct program, so labelling it
  `COMPARISON_BOUNDARY` teaches the model a false thing, and no repair can "fix" it (tests already pass).

### 5.5 Name normalization (`f`, `v1`, `v2`...)

- **Decision**: function becomes `f`, parameters and locals become `v1, v2...` in order of appearance;
  builtins (`len`, `range`) stay.
- **Why (intuition)**: otherwise the classifier can latch onto names (`total` often means "initial value
  bug") that real students would not share. We want it to read structure. It also makes unrelated
  problems look more alike, which is closer to testing "do you understand the bug type".
- **Order detail**: mutate **after** normalizing, so the stored code is exactly what the model sees and
  exactly what the verifier repairs (the verifier calls `f`, via `normalized_problem`).

### 5.6 Retry the split until every split has all 5 classes

- **Decision**: shuffle problems until train/dev/meta_dev/test each contain every class (seeded, so the
  result is deterministic).
- **Why (intuition)**: a split lacking a class makes that class's F1 undefined (0/0) and macro-F1
  meaningless there. This is a reproducible search over *which functions go where* using only class
  presence, never model scores.

### 5.7 Seed is stratified with a minimum

- **Decision**: ~15% of each class, but at least `min_seed_per_class = 2`.
- **Why (intuition)**: random 15% of a 10-sample class could be 1 or 0 and drop a class from the seed.

### 5.8 PROBLEM FOUND: the dataset is small, and the small classes are tiny

Real output of `python scripts/01_generate_data.py` (154 samples in total):

| split | OFF_BY_ONE | WRONG_INDEX | COMPARISON | LOGIC | WRONG_INIT | total |
|---|---|---|---|---|---|---|
| seed | 3 | 6 | 2 | 2 | 2 | 15 |
| pool (hidden) | 15 | 36 | 2 | 13 | 6 | 72 |
| dev | 6 | 9 | 2 | 5 | 2 | 24 |
| meta_dev | 5 | 10 | 2 | 3 | 3 | 23 |
| test | 6 | 6 | 2 | 4 | 2 | 20 |

Why this matters:
- `COMPARISON_BOUNDARY` has **2 samples** in dev, meta_dev and test and **2 in the pool**. One wrong prediction
  moves its F1 by about 0.3 and macro-F1 by about 0.06. Our gate thresholds are `min_delta = 0.005` and
  `max_class_drop = 0.10`, so the gates would mostly react to **noise**, and the improver would be
  rewarded for luck.
- The pool has 72 items, but the spec's `POOL_PER_ROUND = 300` assumes far more.
- The seed has 15 labeled examples for 5 classes. The teacher starts very weak (intended), but 2 per class
  may be too few to learn anything.
- The cause: only 20 functions with single-place bugs give about 154 distinct buggy programs. The
  imbalance from Step 3.9 is inherited (some classes only fit a few functions).

This was a *decision for the user*, not something to hide or silently fix. The user chose style-variant
augmentation (5.9). That was not enough on its own (5.10), so we also used the spec's room for up to 24
problems (5.11). Final numbers are in 5.12.

### 5.9 Style-variant augmentation (`codecoach/styles.py`)

- **Decision**: before injecting bugs, rewrite each reference solution in equivalent styles, using three
  behaviour-preserving AST rewrites and every combination of them (up to 8 variants):
  1. `x += e` becomes `x = x + e`
  2. `a > b` becomes `b < a` (ordering comparisons only)
  3. `if A and B: ...` becomes nested `if A: if B: ...`
- **Why (intuition)**: students write the same logic in different shapes, and the classifier should learn the
  *bug*, not one specific template. It also multiplies the data without inventing new logic.
- **Why it cannot leak**: every style variant belongs to its problem, and splits are by problem, so no style
  variant of a test function ever appears in train.
- **Safety net**: a test runs every style variant of every problem through the sandbox; all must still pass the
  problem's tests (a rewrite that changed behaviour would silently create wrong "correct" code).
- **Bug found while building it**: Python 3.13's `ast.unparse` needs line numbers on statement nodes; the
  `Assign` created by rewrite 1 had none and crashed. Fixed with `ast.fix_missing_locations`.
- **Ambiguity guard**: if two styles produce identical buggy text under different labels, the sample is
  dropped (a label for it would be arbitrary).

### 5.10 Augmentation alone was not enough: the host-function problem

- After augmentation: 319 samples, but `COMPARISON_BOUNDARY` still had only 2 samples in `dev` while
  `meta_dev` had 14. I then asked for at least 5 samples per class in every split, and **no partition
  existed**.
- **Root cause**: `COMPARISON_BOUNDARY` can only be injected into functions that contain a comparison
  where ties matter. Only **6 of the 20** problems did (`binary_search`, `count_in_range`, `all_positive`,
  `is_sorted`, `merge_two_sorted`, `count_greater`), and two of them held most of the samples. Six
  functions cannot feed four splits. Rewriting styles multiplies *variants of those 6 functions*, not the
  number of different functions.
- **Lesson to remember**: more data from the same functions is not more diversity. Diversity comes from
  different host functions. I diagnosed this by listing which problems host which class before changing
  anything, rather than lowering the threshold to make the error go away.

### 5.11 Four new problems (the spec allows 18-24)

- **Decision**: added `count_negative`, `all_below`, `first_index_above`, `is_strictly_increasing`
  (now 24 problems, 7-10 tests each; `split_sizes` is now `(12, 4, 4, 4)`).
- **Why these**: ties must change the answer, otherwise `<` vs `<=` is an equivalent mutant and is
  filtered out (like `find_max`). For example `all_below([5], 5)` must be False, so `>=` to `>` is caught.
- This stays inside the spec's 18-24 range. It does make the Step 2 numbers outdated (20 problems, 169
  tests); the code is the source of truth.

### 5.12 Split search: valid first, then best

- **Decision**: try 3000 seeded shuffles of the problems. A partition is *valid* if every split has at
  least `min_class_per_split = 5` samples of every class. Among valid ones, choose the one whose **training**
  set has the most samples of its scarcest class.
- **Why (intuition)**: "first valid" gave a train set with 6 `COMPARISON_BOUNDARY` samples and a test set
  with 24, which is backwards: the model learns from the least. The choice uses **only class counts**, never
  model scores, so it cannot leak test information. It is a deliberate, documented, seeded decision
  about which *functions* go where.
- **Honest limit**: this chooses the partition once, by us. A different partition would give different
  scores. Reporting a few partitions would be more convincing; that is listed in the limitations.

Final dataset (real output, 381 samples, 24 problems):

| split | OFF_BY_ONE | WRONG_INDEX | COMPARISON | LOGIC | WRONG_INIT | total |
|---|---|---|---|---|---|---|
| seed | 7 | 12 | 3 | 5 | 3 | 30 |
| pool (hidden) | 41 | 70 | 17 | 27 | 17 | 172 |
| dev | 8 | 16 | 12 | 19 | 12 | 67 |
| meta_dev | 18 | 20 | 6 | 11 | 7 | 62 |
| test | 18 | 12 | 6 | 8 | 6 | 50 |

Compared with the first attempt (154 samples, as few as 2 per class per split): the pool grew from 72 to
172, and every evaluation split now has at least 6 per class. Still small, still noisy: with 6 samples one
mistake moves that class's F1 by roughly 0.1. The `min_delta` gate and repeated evaluation must account for
this; it is also a stated limitation. The seed has only 3 samples for two classes: the teacher starts weak
on purpose.

### 5.13 Tests (9) and what they prove

Splits share no problems; samples belong to their split's problems; every split has every class; pool hides
its label and is disjoint from seed; every dev/test sample really fails its tests; names are normalized;
the build is reproducible (same seed gives the identical dataset) and survives a save/load round-trip;
every style variant still passes the problem's tests; style rewrites really add variety.

---

## Step 6: Level 0, verified self-training (`codecoach/self_training.py` and friends)

Files: `self_training.py` (110 lines), `teacher.py`, `evaluation.py`, `feature_blocks.py`, `evolvable/pipeline.py`
(**v0**), `verifier.py` (+ verdict table), `tests/test_self_training.py`; `max_rounds` in `config.py`.
`teacher.py` is a helper module not named in the spec: it holds the shared mechanics so that
`self_training.py` stays short and readable.

### 6.1 What Level 0 does, in one picture

```
seed (30 labeled) --> train teacher v0
repeat up to N rounds:
    teacher diagnoses unlabeled pool programs
    verifier keeps only diagnoses where a matching repair passes the hidden tests
    train a COPY on seed + verified examples (curated)
    GATE on dev: better by min_delta and no class collapsed?  yes -> promote the copy
                                                               no  -> rollback (keep old teacher)
    stop after 2 rejected rounds in a row
```
It changes only the *weights*. The code that defines the pipeline does not change here; that is Level 1.

### 6.2 The gate, and why it has two conditions

- **Decision**: accept a candidate only if `dev macro-F1 >= best + min_delta` **and** no class F1 fell by more
  than `max_class_drop` (0.10).
- **Why (intuition)**: self-training has a known failure: the model reinforces its own mistakes (confirmation
  bias). The gate is the circuit breaker. The class-drop rule exists because an *average* can rise while one
  class is sacrificed, which for a tutor means some students get systematically wrong feedback.
- **Evaluator might ask**: *"What stops error amplification?"* Two layers: the verifier decides what enters
  training, and the dev gate decides whether the result is kept at all.

### 6.3 Rollback is just "do not replace the old object"

- **Decision**: the candidate is trained as a separate model; `teacher` is reassigned only on acceptance.
- **Why (intuition)**: rollback needs no undo logic because the old teacher was never touched. The simplest
  safe design is one where failure leaves everything as it was. There is a test for it
  (`test_impossible_gate_means_rollback_and_early_stop`: nothing promoted, final dev equals initial dev).

### 6.4 Retrain from scratch each round, on seed + all verified so far

- **Decision**: every candidate is a fresh network (not the previous teacher fine-tuned).
- **Alternative**: keep training the same network round after round.
- **Why (intuition)**: continuing to train a model on data it produced compounds its errors. A fresh network
  on the verified set is a clean test: "does this dataset teach something better?" It also makes rounds
  independent and reproducible (seed + round number).

### 6.5 The pipeline may only make the gate STRICTER

- **Decision**: `effective_min_delta = max(config.min_delta, pipe.MIN_DELTA)`.
- **Why (intuition)**: `MIN_DELTA` lives in the editable file so Level 1 can tune it. If an edit could set it to
  `-1`, every round would be accepted and the gate would protect nothing. This is **reward hacking by editing
  the rules**. Letting the file raise the bar but never lower it keeps the search space useful and the guarantee
  intact. Same idea: `max_class_drop` and `max_rounds` come only from `config.py`, which the system cannot edit.

### 6.6 Hidden labels are used for logging only, and a test proves it

- **Decision**: the loop reads `.code` of pool items. `hidden_label` is read in exactly one place, to compute
  `precision` and `raw_accuracy` for the log.
- **Proof, not promise**: `test_loop_never_reads_hidden_labels` replaces every hidden label with `"SCRAMBLED"`
  and checks that all decisions and final scores are identical; only the two logged statistics may differ.

### 6.7 Precomputed verdict table (speed without changing results)

- **Decision**: script 01 asks the verifier every (program, label) question once (172 x 5) and saves
  `data/generated/verdicts.json` (50 s, one time). The loop looks answers up, and falls back to a live
  `verify()` call on a miss.
- **Why (intuition)**: the verifier does not depend on any model, so its answers are fixed facts. Later, Level 1
  evaluates dozens of pipeline versions, each in its own process, and the in-memory sandbox cache is not
  shared across processes. Without the table each evaluation would redo thousands of sandbox runs.
  With it, a whole Level 0 run takes about 7.5 s.
- **Side benefit (real numbers)**: on the 172 pool programs the verifier accepts the **true label 172/172** and a
  **wrong label 4/688 (0.6%)**.
- **Important for Step 7**: the evaluator must only *read* `data/generated/`. Tamper detection hashes `data/`
  before and after every evaluation; a write there would look like an attack.

### 6.8 `pipeline.py` v0: a deliberately plain baseline

- Char 2-4-gram TF-IDF + 3 structural features (`count_comparisons`, `count_range_calls`,
  `count_subscripts`) -> MLP 256-128, dropout 0.2, Adam 1e-3, 30 epochs. `PER_CLASS_CAP = 30`.
- These were set once, before any result, and **not tuned**. The point of Level 1 is to see whether the system
  can beat a baseline we did not polish. Tuning v0 until it looked good would make any later gain smaller and
  harder to defend.
- Features go through `sign(x) * log1p(|x|)` so counts live on the same scale as TF-IDF values (0 to 1).
- Whitelisted building blocks (`feature_blocks.py`) are a fixed menu of 8 functions. An edit can only combine
  tools we wrote and tested.

### 6.9 REAL RESULT (seed 0, default settings, one run)

| Round | Pool left | Verified | Rejected | Precision of verified | Teacher's raw accuracy | Dev F1 | Decision |
|---|---|---|---|---|---|---|---|
| (v0, seed only) | | | | | | 0.211 | |
| 1 | 172 | 61 | 111 | 1.00 | 0.35 | 0.303 | accepted |
| 2 | 111 | 14 | 97 | 1.00 | 0.13 | 0.322 | accepted |
| 3 | 97 | 21 | 76 | 1.00 | 0.22 | 0.394 | accepted |
| 4 | 76 | 11 | 65 | 1.00 | 0.14 | 0.337 | **rejected (no_improvement)** |

Final dev macro-F1 **0.211 -> 0.394** (reproducible: a second run gave identical numbers).

| Class | Start | Final |
|---|---|---|
| OFF_BY_ONE_RANGE | 0.22 | 0.57 |
| WRONG_INDEX | 0.42 | 0.52 |
| COMPARISON_BOUNDARY | **0.00** | **0.00** |
| LOGIC_OPERATOR | 0.42 | 0.88 |
| WRONG_INITIAL_VALUE | **0.00** | **0.00** |

What this shows:
- **The verifier is doing the work.** The teacher was wrong 65-87% of the time on the pool, yet everything the
  verifier let through was correct (96 of 96). Naive self-training would have trained on mostly wrong labels.
- **The gate worked as designed**: round 4 got worse on dev and was rolled back.
- **A blind spot (important)**: two classes stay at **0.00**. Self-training can only learn from diagnoses the
  teacher *makes*, and a teacher that never predicts `COMPARISON_BOUNDARY` correctly never produces verified
  examples of it. The seed has just 3 examples of each of those two classes. This is the "rich get richer"
  weakness of self-training and a natural target for Level 1 (e.g. better structural features, or a curation
  that rebalances). We do not fix it by hand.
- Verified counts shrink each round (61, 14, 21, 11): easy cases are absorbed first, and the remaining
  pool is harder.

### 6.10 Caveats that must go in the report

- **One seed, one run.** No error bars yet.
- **Dev is used twice**: it drives the Level 0 gate *and* it is the number we report here. That makes
  0.394 optimistic. The honest numbers are meta_dev and test, which nothing has been selected on.
- **Small F1 steps are noise-sized** (6 to 19 samples per class): a +0.02 move between rounds is not evidence.
- The pool is 172 programs; `POOL_PER_ROUND = 300` therefore means "the whole pool".
- A bug in my own printout (labels cut to 8 characters merged two classes) briefly hid the zero-F1 finding;
  caught by re-running with full names. Worth remembering: check how results are *displayed*, too.

### 6.11 Tests (9 new, 33 total, 40 s)

Gate accepts clear gains, rejects "no improvement" and "tiny gain", rejects a class collapse even when the
average rises; the pipeline cannot loosen the gate; confidence-only ablation works; curation dedups and caps;
feature blocks count what they say (and survive unparseable code); rollback + early stop; hidden labels never
influence decisions.

---

## Step 7a: The editing toolbox and the guard-rails (`code_editor.py`, `safety.py`)

Files: `code_editor.py` (152 lines), `safety.py` (145 lines), `tests/test_code_editor.py`, `tests/test_safety.py`.
Step 7 was split in two: 7a (this) builds the tools; 7b builds archive + evaluator + evolve loop.

### 7a.1 Constrained program search instead of free-form code generation

- **Decision**: the default proposer edits `evolvable/pipeline.py` with 5 fixed operators (`tweak_constant`,
  `add_feature`, `remove_feature`, `change_layer`, `swap_curation`). Each parses the file, changes the tree,
  and unparses it.
- **Alternative**: let an LLM write the whole file (the optional proposer in Step 13).
- **Why (intuition)**: think of a chef who may only choose from a fixed menu of ingredients and adjust
  amounts, versus one who may improvise anything. Most menu combinations are valid dishes, so nearly every
  child *runs* and the search spends its budget learning, not crashing. It needs no API key, is
  reproducible, and every edit has a readable name. It is a small-scale version of what the Darwin Godel
  Machine does with an LLM. The honest cost: it can only find improvements that live inside the menu.
- **Evaluator might ask**: *"Is this really self-modifying code?"* Yes: the program's own source file is
  rewritten and the rewritten program is what runs. It is bounded self-modification, not open-ended.

### 7a.2 Bounds on every number

- **Decision**: each tunable has a hard range (`LR` in [1e-4, 1e-2], `EPOCHS` in [5, 100], `MIN_DELTA` in
  [0, 0.05], ...). Ints stay ints. Edits that would leave the range are clamped; no-ops return `None`.
- **Why (intuition)**: without bounds one lucky multiplication gives `EPOCHS = 10**9` and the evaluator spends
  the whole budget. A test applies 200 aggressive edits in a row and checks every value stays in range.
- `NGRAM_RANGE` is kept ordered (`low <= high`); an edit that would break it is dropped.

### 7a.3 A fixed menu of feature blocks

- `add_feature` can only call blocks that exist in `feature_blocks.py` (8 of them); `remove_feature` never
  removes the last one. So a "new feature" can never smuggle in file access, labels or test data: it is a
  call to code we wrote and tested.

### 7a.4 Edits drop comments (known cost)

- `ast.unparse` removes comments and blank lines. Version v000 in the archive will therefore be stored in
  normalized form (comment-free), so that diffs between versions show only the real edit. The original
  commented `evolvable/pipeline.py` stays untouched in the repo. Demo diff: one changed line for one
  `add_feature`.

### 7a.5 One toolbox for both levels

- The same module exposes `IMPROVER_OPERATORS` (`tweak_constant` on the improver's own knobs with
  `IMPROVER_BOUNDS`, and `swap_parent_selection`). Level 2 will reuse the machinery, so "the improver edits
  itself" needs no second implementation. `OPERATOR_WEIGHTS` is a dict, and its values are tunable too.

### 7a.6 `safety.py`: four independent guard-rails

| Guard | What it stops | Where it bites |
|---|---|---|
| Write whitelist (`assert_write_allowed`) | overwriting library/config/baseline | any write by the system must be under `archive/` (path tricks like `archive/../config.py` are resolved and refused) |
| Static check (`check`) | forbidden imports and names, dunder escapes, code that runs at import, wrong interface | before a candidate is ever run |
| Tamper detection (`protected_hashes`, `assert_unchanged`) | a candidate (or bug) changing the evaluator, data or tests | before/after every evaluation |
| Isolated run (`run_isolated`) | infinite loops, runaway memory, crashes | the child is killed and the reason logged |

**Why layers (intuition)**: any single wall can have a hole. The static check can miss a trick; so a timeout
and memory cap still contain it; and if something still modified the evaluator, the hash check notices.
Each layer assumes the one before it failed.

### 7a.7 What the static check rejects (and why each rule exists)

- Imports outside a per-file allow-list (pipeline: numpy, torch, torch.nn, random, math, the feature blocks;
  improver: random, math, the editor).
- Names for file/network/process/dynamic-code access (`open`, `exec`, `eval`, `__import__`, `os`, `sys`,
  `subprocess`, `getattr`, `pickle`, ...), plus helpers hidden inside allowed libraries
  (`torch.load`, `numpy.load`, `memmap`, `fromfile`, ...).
- Our protected data: `splits`, `hidden_label`, `verdicts`, `verify`, `tests`, `PROBLEMS`: "no reference to
  splits/labels/tests".
- Any dunder attribute or name (blocks `().__class__.__bases__...` escapes).
- Any statement at top level except imports, assignments, defs and a docstring: nothing may run on import.
- Missing required functions/constants (`extra_features`, `build_teacher`, `curate`, `LR`, ...): a file
  that breaks the interface is rejected *before* running, which saves evaluation time.
- Source longer than 20,000 characters.

### 7a.8 Honest limits of the guard-rails

- **The static check is a filter, not a proof.** A determined adversary could look for gaps (that is why
  there are three other layers). Our threat model is a *buggy or over-eager search procedure*, not a
  malicious human.
- Forbidding names also forbids innocent variables called `load`, `save`, `tests`, ... A mild cost,
  accepted for simplicity.
- Candidate code runs on the same machine as the user's files. A real deployment would add an OS-level
  sandbox (container, no network).

### 7a.9 The memory cap needed OS-specific code, and I checked it for real

- **Decision**: Linux/macOS use `RLIMIT_AS`; Windows (this machine) uses a **Job Object** with a per-process
  memory limit, via `ctypes`.
- **Check (not just a green test)**: allocating 1500 MB under a 300 MB cap died with `MemoryError`
  (`ok=False reason=crashed`), while a 100 MB control under the same cap succeeded. That rules out "the
  test passed because the machine happened to fail".
- The Linux/macOS branch is written but **not tested here** (no such machine). The documentation should say so.

### 7a.10 Tests (41 new; 74 total in 42 s)

Every operator: parseable, different, passes the safety check and actually **imports and runs**
(`build_teacher`, `extra_features`) over 25 random seeds; bounds hold after 200 edits; layer count stays 1-4;
add/remove feature behave; deterministic per seed; improver operators work on an improver-like file.
Safety: baseline passes; each forbidden import/name/dunder/top-level-code/missing-interface/syntax/size case
is rejected for the right reason; tamper detection fires for a changed, added or deleted file in every
protected area; writes are limited to `archive/`; isolated runs return output, time out, and stop runaway memory.

---

## Step 7b: Archive, evaluator and the Level 1 loop (`archive.py`, `evaluator.py`, `02_evolve.py`, `improver.py` v0)

Files: `archive.py` (90 lines), `evaluator.py` (79), `scripts/02_evolve.py` (92), `evolvable/improver.py` (41),
`tests/test_archive_evolve.py` (12 tests). Suite: 86 tests, 54 s.

### 7b.1 The archive is a tree of versions, not a single "current" file

- **Decision**: every candidate gets an id (`v000`, `v001`, ...), a parent, the edit that produced it, its metrics,
  an accepted flag and a reason. Rejected versions are **kept** (source + metrics), flagged.
- **Alternative**: keep only the current best and overwrite it (hill climbing).
- **Why (intuition)**: Darwin-Godel-Machine thinking: a mediocre version today might be the stepping stone to a
  great one tomorrow, so any accepted version can be a parent. Keeping rejected versions is what makes the failure
  analysis possible later ("which kinds of edits never helped?"). Weights (`model.pt`) are stored only for accepted
  versions; rejected ones are too many and too useless to keep.
- Writes go through `assert_write_allowed`; the index is written to a temp file and renamed so a crash can never
  leave a half-written `index.json`.

### 7b.2 The evaluator treats the system's own code as untrusted

- **Decision**: a candidate is written to `archive/_tmp/`, imported and run inside an **isolated child** (timeout, memory
  cap), and every protected file is hashed before and after. A change raises `TamperError`, which the loop does **not**
  catch: the whole run aborts.
- **Why (intuition)**: the thing being evaluated wrote its own code. The evaluator is the one place that must not trust
  it. A crash or hang costs one generation; tampering ends the experiment, because after tampering no number can be trusted.
- The child reports one `@@RESULT@@` JSON line; the candidate's `print()` output is diverted to stderr so it cannot forge
  or corrupt the result.
- It returns **dev** F1 (decides pipeline acceptance) and **meta_dev** F1 (only for judging improvers in Level 2). **`test`
  is never touched here.**

### 7b.3 Bug found by running it: `python -I` hides your packages

- The sandbox from Step 4 uses `python -I`. For the evaluator the child died instantly: `No module named 'torch'`. `-I`
  also disables *user* site-packages, where torch lives; Step 4 never noticed because it needed only the standard library.
- **Fix**: `run_isolated` now uses `-E -P` (ignore `PYTHON*` env vars; keep the current directory off the import path).
  That keeps the protection we wanted (no planted `json.py`) without hiding installed packages.
- **Lesson**: a safety flag can silently remove something the code depends on. Always run the real thing once.
- **Verification that isolation changes nothing**: the isolated baseline gave dev 0.394 (0.211 initially), the same as the
  in-process run in Step 6, in 5.5 s.

### 7b.4 Failure is a normal outcome with a name

- Rejection reasons recorded per version: `unsafe: ...` (never run), `duplicate` (same code as an earlier version, not
  re-evaluated), `crash`, `timeout`, `memory`, `no_improvement`. All three runtime failures were tested **for real** (a
  `1/0`, a `[0] * 10**11`, a `while True`) and each is contained and correctly named.
- Duplicates are skipped because evaluation is the expensive step; they still use up a generation, so the budget stays
  honest and the loop always terminates.
- **Test-writing lesson**: one of my tests silently evaluated the *unmodified* baseline, because `ast.unparse` writes
  `layers, width = ([], input_dim)` (with parentheses) and my `.replace` matched nothing. It "failed" in a confusing way
  (the evaluator said OK). Every replace-based test now asserts that the text really changed.

### 7b.5 The gate compares a child with its PARENT

- **Decision**: accept if `dev_f1(child) >= dev_f1(parent) + min_delta` (0.005), where the parent is whichever accepted
  version the improver picked, not the global best.
- **Why (intuition)**: it measures what the edit did. Comparing to the global best would reject useful edits of weaker
  lineages that the archive wants to keep exploring. Cost: a chain of small noisy "wins" can drift upward (see 7b.7).

### 7b.6 `improver.py` v0 (written now, edited by itself in Step 8)

- Holds `OPERATOR_WEIGHTS`, `EDITS_PER_CHILD`, `PARENT_SELECTION`, `TOURNAMENT_K`, `STEP_SCALE` and three functions:
  `choose_parent`, `propose_child` (used now) and `propose_self_edit` (used by Level 2 next step).
- Tournament selection (best of K random accepted versions) = pressure toward good parents with some exploration.
- It receives the archive as plain dicts (`id`, `dev_f1`, `order`), not objects: the improver file gets only what it needs.
- It passes the same static check (`kind="improver"`). It runs in the main process, which is acceptable only because every
  Level 2 edit is a constrained change to constants/strings (Step 7a), never new logic.

### 7b.7 REAL RESULT: first `--quick` run (6 generations, seed 0)

| Version | Parent | Edit | Dev F1 | Meta-dev F1 | Decision |
|---|---|---|---|---|---|
| v000 | | baseline | 0.394 | 0.536 | baseline |
| v001 | v000 | `change_layer [256,128] -> [128]` | 0.077 | | rejected: no_improvement |
| v002 | v000 | `swap_curation dedup_cap -> balance` | 0.376 | | rejected: no_improvement |
| v003 | v000 | same edit as v002 | | | rejected: duplicate |
| v004 | v000 | `add_feature count_const_assigns` | 0.434 | **0.408** | accepted |
| v005 | v004 | `EPOCHS 30 -> 43` | 0.438 | | rejected: no_improvement |
| v006 | v004 | `EPOCHS 30 -> 39` | 0.465 | 0.550 | accepted |

Diff of the system's rewrite of its own source, v000 to v006: `EPOCHS = 30` becomes `39`, and a fourth feature
`fb.count_const_assigns(code)` is appended to `extra_features`.

**How to read it honestly (do not oversell):**
- The pipeline's dev F1 rose **0.394 -> 0.465 (+0.071)**, but meta_dev rose only **0.536 -> 0.550 (+0.014)**. The dev gain
  is mostly selection on dev (and noise); meta_dev, which nothing chose on, shows almost nothing.
- **v004 gained +0.040 on dev but lost 0.128 on meta_dev** (0.536 -> 0.408). An accepted version that is *worse* on held-out
  data is the textbook symptom of selecting on a small, noisy dev set. This is exactly why meta_dev exists, and the reason
  gains must be confirmed on data the search never used (test, more seeds).
- `WRONG_INITIAL_VALUE` stays at F1 = 0 on both splits even though `count_const_assigns` was added with it in mind;
  `COMPARISON_BOUNDARY` is 0 on meta_dev. The blind spot from Step 6 is not fixed by this run.
- v001 (one hidden layer) scores 0.077 on dev: with so little data, small architecture changes can swing results wildly. That
  is the noise level the gate has to live with.
- Six generations, one seed, one run: this proves the **machinery works**, not that self-editing helps. The full run (20
  generations), the ablation and extra seeds come later.

### 7b.8 Known limitations of this step

- One seed per evaluation: parent and child are compared on a single training run, so some accepted edits are just seed luck.
  Plan: re-evaluate the baseline and the best version on extra seeds and report the mean (not used for selection).
- Comments are dropped by `ast.unparse` (v000 in the archive is the comment-free form).
- Linux/macOS memory cap still untested (see 7a.9).
- The Level 1 loop runs sequentially (about 6 s per evaluation); parallel evaluation would be faster but harder to follow.

---

## Demo requirement added after Step 7 (decided with the user)

The presentation must show learning **happening**, not only saved results. Chosen: **both** live-learning modes, and
**live distillation**.

| Live feature | What the audience sees | What it needs from the library |
|---|---|---|
| Learn from my snippet (Try-it page) | paste a bug -> prediction -> verifier check -> retrain in seconds -> before/after prediction + gate decision | a function that adds one verified example and retrains/gates; fast (a Level 0 training takes about 1 s) |
| Live run (Run button) | rounds stream in: accepted vs rejected pseudo-labels, dev F1, rollbacks | `self_train` must report each round through a callback instead of only returning at the end |
| Live distillation | tiny student trained from the teacher in seconds, live loss curve, then F1 / size / latency vs hard-label student | distillation training with a progress callback, fast enough for a laptop on stage |

Decisions already visible, to be settled when the app is built (Step 11):
- **One example rarely moves dev F1 by `min_delta`.** A strict gate will almost always roll back a single-snippet update.
  Options: collect a few verified snippets in a session buffer and retrain when it reaches k, or show the before/after
  prediction on the SAME snippet next to the (honest) gate verdict. Do not weaken the real gate to make the demo look good.
- The full 3-seed distillation table stays precomputed. The live student is a demonstration, a single run; it must say so on screen.
- Live runs use quick mode so they finish in 1-3 minutes.

Plan impact: Step 8 (Level 2) unchanged; Steps 8-10 add progress callbacks; Step 11 gets a "Live" page.

---

<!-- Next entry: Step 8: Level 2, the improver improves itself -->

