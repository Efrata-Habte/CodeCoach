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

<!-- Next entry: Step 5: generator.py (dataset + splits) -->
