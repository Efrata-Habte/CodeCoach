# Hand-written final test set

`cases.py` holds 25 buggy functions (5 per misconception class) written by hand in a **different style** from
`codecoach/problems.py`: new problems, new names, `while` loops, loops over elements. Each has its TRUE label and tests that the
buggy code fails and a fix passes (`tests/test_handwritten.py` checks this with the sandbox and verifier; no model involved).

## Rules (this is what makes it a final test)

1. **Nothing may select, tune or train on these cases.** Only `scripts/04_final_test.py` reads them.
2. `04_final_test.py` refuses to run without `--final`, runs the evaluation **once**, and writes `results/FINAL_TEST_DONE`.
   Running it again needs `--again` and prints a loud warning: after you have looked at the result and changed anything,
   the set is no longer a fair final test.

## Add your own mistakes BEFORE running it (recommended: 5-10)

Real mistakes you made are the most convincing evidence, because nobody tuned anything to them. At the bottom of
`cases.py`, in the "MY CASES" section, append:

```python
case("WRONG_INDEX", '''def my_function(xs):
    return xs[len(xs)]
''', [(([1, 2, 3],), 3), (([5],), 5)]),
```

- The label must be one of: `OFF_BY_ONE_RANGE`, `WRONG_INDEX`, `COMPARISON_BOUNDARY`, `LOGIC_OPERATOR`, `WRONG_INITIAL_VALUE`.
- The tests must be `(args_tuple, expected)` and the buggy code must FAIL at least one of them.
- Then run `python -m pytest tests/test_handwritten.py`: it confirms that your case is a real bug and that a repair of your label
  makes the tests pass. If your real mistake does not fit one of the 5 classes, leave it out (or note it as a limitation).
