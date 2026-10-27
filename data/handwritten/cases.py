"""FINAL TEST SET: hand-written buggy functions in a DIFFERENT style from codecoach/problems.py.

Different on purpose: problems that are not in problems.py, other names, loops over elements
(`for v in values`), `while` loops, early returns. No model, search step or script except
04_final_test.py may read this file, and 04 refuses to run without --final.
Each case: the buggy code, its TRUE label, and tests that the buggy code fails and a fix passes.
Test format: (args_tuple, expected_output).

ADD YOUR OWN: append 5-10 real mistakes you made, at the bottom, in the section marked MY CASES.
"""
import ast

LABELS = ["OFF_BY_ONE_RANGE", "WRONG_INDEX", "COMPARISON_BOUNDARY", "LOGIC_OPERATOR", "WRONG_INITIAL_VALUE"]


def case(label: str, code: str, tests: list) -> dict:
    """One final-test case; the function name is read from the code itself."""
    return {"name": ast.parse(code).body[0].name, "label": label, "code": code, "tests": tests}


CASES = [
    # ------------------------------------------------------------------ OFF_BY_ONE_RANGE
    case("OFF_BY_ONE_RANGE", '''def sum_first_n(values, n):
    total = 0
    for k in range(n - 1):
        total += values[k]
    return total
''', [(([1, 2, 3, 4], 2), 3), (([5, 5, 5], 3), 15), (([7], 1), 7), (([1, 2, 3], 0), 0), (([2, 4, 6, 8], 4), 20)]),
    case("OFF_BY_ONE_RANGE", '''def countdown(n):
    out = []
    for k in range(n, 1, -1):
        out.append(k)
    return out
''', [((3,), [3, 2, 1]), ((1,), [1]), ((0,), []), ((5,), [5, 4, 3, 2, 1])]),
    case("OFF_BY_ONE_RANGE", '''def squares_up_to(n):
    result = []
    for k in range(1, n):
        result.append(k * k)
    return result
''', [((1,), [1]), ((3,), [1, 4, 9]), ((0,), []), ((4,), [1, 4, 9, 16])]),
    case("OFF_BY_ONE_RANGE", '''def first_multiples(step, count):
    out = []
    for k in range(1, count):
        out.append(step * k)
    return out
''', [((3, 3), [3, 6, 9]), ((5, 1), [5]), ((2, 0), []), ((4, 2), [4, 8])]),
    case("OFF_BY_ONE_RANGE", '''def pair_sums(items):
    out = []
    for k in range(len(items) - 2):
        out.append(items[k] + items[k + 1])
    return out
''', [(([1, 2, 3],), [3, 5]), (([4],), []), (([],), []), (([1, 1],), [2]), (([5, 6, 7, 8],), [11, 13, 15])]),
    # ------------------------------------------------------------------ WRONG_INDEX
    case("WRONG_INDEX", '''def last_item(values):
    return values[len(values)]
''', [(([1, 2, 3],), 3), (([9],), 9), (([4, 5],), 5)]),
    case("WRONG_INDEX", '''def swap_ends(values):
    out = list(values)
    out[0] = values[len(values) - 2]
    out[len(values) - 1] = values[0]
    return out
''', [(([1, 2, 3],), [3, 2, 1]), (([1, 2],), [2, 1]), (([5, 6, 7, 8],), [8, 6, 7, 5])]),
    case("WRONG_INDEX", '''def gaps(values):
    out = []
    for k in range(len(values) - 1):
        out.append(values[k + 2] - values[k])
    return out
''', [(([1, 4, 9],), [3, 5]), (([2, 2],), [0]), (([5],), []), (([1, 2, 4, 8],), [1, 2, 4])]),
    case("WRONG_INDEX", '''def second_item(values):
    return values[2]
''', [(([1, 2, 3],), 2), (([9, 8],), 8), (([4, 5, 6, 7],), 5)]),
    case("WRONG_INDEX", '''def middle_item(values):
    return values[len(values) // 2 + 1]
''', [(([1, 2, 3],), 2), (([7],), 7), (([1, 2, 3, 4, 5],), 3)]),
    # ------------------------------------------------------------------ COMPARISON_BOUNDARY
    case("COMPARISON_BOUNDARY", '''def is_adult(age):
    return age > 18
''', [((18,), True), ((17,), False), ((30,), True), ((0,), False)]),
    case("COMPARISON_BOUNDARY", '''def count_small(values, limit):
    n = 0
    for v in values:
        if v <= limit:
            n += 1
    return n
''', [(([1, 5, 9], 5), 1), (([], 3), 0), (([2, 2], 2), 0), (([1, 2, 3], 4), 3)]),
    case("COMPARISON_BOUNDARY", '''def in_bounds(x, lo, hi):
    return lo < x and x <= hi
''', [((5, 1, 10), True), ((1, 1, 10), True), ((10, 1, 10), True), ((0, 1, 10), False), ((11, 1, 10), False)]),
    case("COMPARISON_BOUNDARY", '''def total_up_to(n):
    total = 0
    i = 1
    while i < n:
        total += i
        i += 1
    return total
''', [((0,), 0), ((1,), 1), ((3,), 6), ((4,), 10)]),
    case("COMPARISON_BOUNDARY", '''def never_decreases(values):
    i = 0
    while i < len(values) - 1:
        if values[i + 1] <= values[i]:
            return False
        i += 1
    return True
''', [(([],), True), (([1],), True), (([1, 1],), True), (([1, 2, 3],), True), (([2, 1],), False),
      (([1, 3, 2],), False), (([2, 2, 3],), True)]),
    # ------------------------------------------------------------------ LOGIC_OPERATOR
    case("LOGIC_OPERATOR", '''def is_teenager(age):
    return age >= 13 or age <= 19
''', [((13,), True), ((19,), True), ((12,), False), ((20,), False), ((16,), True)]),
    case("LOGIC_OPERATOR", '''def is_weekend(day):
    return day == 6 and day == 7
''', [((6,), True), ((7,), True), ((1,), False), ((5,), False)]),
    case("LOGIC_OPERATOR", '''def either_empty(a, b):
    return len(a) == 0 and len(b) == 0
''', [(([], [1]), True), (([1], []), True), (([], []), True), (([1], [2]), False)]),
    case("LOGIC_OPERATOR", '''def positive_even(n):
    return n > 0 or n % 2 == 0
''', [((4,), True), ((3,), False), ((-2,), False), ((0,), False)]),
    case("LOGIC_OPERATOR", '''def count_nonneg(values):
    count = 0
    for k in range(len(values)):
        if values[k] < 0:
            count += 1
    return count
''', [(([],), 0), (([1, -1, 2],), 2), (([-1, -2],), 0), (([0],), 1)]),
    # ------------------------------------------------------------------ WRONG_INITIAL_VALUE
    case("WRONG_INITIAL_VALUE", '''def product_of(values):
    result = 0
    for v in values:
        result *= v
    return result
''', [(([],), 1), (([2, 3],), 6), (([5],), 5), (([2, 2, 2],), 8)]),
    case("WRONG_INITIAL_VALUE", '''def smallest(values):
    best = 0
    for v in values:
        if v < best:
            best = v
    return best
''', [(([5, 3, 9],), 3), (([4],), 4), (([2, 8],), 2), (([-1, 5],), -1)]),
    case("WRONG_INITIAL_VALUE", '''def biggest(values):
    best = 0
    for v in values:
        if v > best:
            best = v
    return best
''', [(([-5, -2, -9],), -2), (([3, 1],), 3), (([-1],), -1)]),
    case("WRONG_INITIAL_VALUE", '''def sum_of_squares(values):
    total = 1
    i = 0
    while i < len(values):
        total += values[i] * values[i]
        i += 1
    return total
''', [(([],), 0), (([2],), 4), (([1, 2, 3],), 14)]),
    case("WRONG_INITIAL_VALUE", '''def last_negative_index(values):
    found = 0
    for k in range(len(values)):
        if values[k] < 0:
            found = k
    return found
''', [(([1, 2],), -1), (([],), -1), (([-1, 2],), 0), (([1, -2, 3, -4],), 3), (([5, -5],), 1)]),
    # ================================================================== MY CASES (add your own real mistakes below)
    # case("WRONG_INDEX", '''def my_function(xs):\n    ...\n''', [((args,), expected), ...]),
]
