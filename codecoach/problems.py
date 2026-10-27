"""Reference solutions + hidden unit tests for 24 beginner functions.

This file is DATA (so it is longer than the other modules). Everything downstream depends on it:
  - the generator injects bugs into these solutions,
  - the verifier decides a fix is "correct" only if THESE tests pass.

Design rules for the tests (why bugs get caught):
  * every function has boundary tests: empty / single element / last element / equal values;
  * so an off-by-one, `<` vs `<=`, or wrong initial value changes the output on some test.
Test format: (args_tuple, expected_output). A test that raises an exception counts as a FAIL.
"""
import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    """One beginner function: its correct source and the tests that define 'correct'."""
    name: str
    source: str
    func_name: str
    tests: list  # list of (args_tuple, expected)


def _make(source: str, tests: list) -> Problem:
    """Build a Problem; the function name is read from the source itself (no typos possible)."""
    func_name = ast.parse(source).body[0].name
    return Problem(func_name, source, func_name, tests)


PROBLEMS: list[Problem] = [
    _make('''def sum_list(xs):
    total = 0
    for i in range(len(xs)):
        total += xs[i]
    return total
''', [(([],), 0), (([5],), 5), (([1, 2, 3],), 6), (([-1, 1],), 0), (([1, 2, 10],), 13),
      (([10, -3, 4, 2],), 13), (([7, 7, 7],), 21)]),

    _make('''def find_max(xs):
    best = xs[0]
    for i in range(1, len(xs)):
        if xs[i] > best:
            best = xs[i]
    return best
''', [(([5],), 5), (([1, 2, 3],), 3), (([3, 2, 1],), 3), (([-5, -2, -9],), -2), (([2, 2],), 2),
      (([1, 9, 4],), 9), (([4, 1, 7, 7, 3],), 7)]),

    _make('''def find_min(xs):
    best = xs[0]
    for i in range(1, len(xs)):
        if xs[i] < best:
            best = xs[i]
    return best
''', [(([5],), 5), (([1, 2, 3],), 1), (([3, 2, 1],), 1), (([5, 2, 9],), 2), (([2, 2],), 2),
      (([4, 0, 9],), 0), (([8, 6, 7, 6],), 6), (([-1, -2],), -2)]),

    _make('''def count_vowels(s):
    count = 0
    for i in range(len(s)):
        c = s[i]
        if c == "a" or c == "e" or c == "i" or c == "o" or c == "u":
            count += 1
    return count
''', [(("",), 0), (("a",), 1), (("xyz",), 0), (("hello",), 2), (("aeiou",), 5), (("rhythm",), 0),
      (("banana",), 3), (("xyza",), 1), (("queue",), 4)]),

    _make('''def linear_search(xs, target):
    for i in range(len(xs)):
        if xs[i] == target:
            return i
    return -1
''', [(([], 5), -1), (([5], 5), 0), (([1, 2, 3], 3), 2), (([1, 2, 3], 1), 0), (([1, 2, 3], 9), -1),
      (([4, 4], 4), 0), (([7, 8, 9, 8], 8), 1), (([2], 3), -1)]),

    _make('''def binary_search(xs, target):
    low = 0
    high = len(xs) - 1
    while low <= high:
        mid = (low + high) // 2
        if xs[mid] == target:
            return mid
        elif xs[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
''', [(([], 3), -1), (([3], 3), 0), (([3], 4), -1), (([1, 2, 3, 4, 5], 1), 0),
      (([1, 2, 3, 4, 5], 5), 4), (([1, 2, 3, 4, 5], 3), 2), (([1, 3, 5, 7], 7), 3),
      (([1, 3, 5, 7], 4), -1), (([1, 3, 5, 7], 0), -1), (([2, 4], 4), 1)]),

    _make('''def reverse_list(xs):
    result = []
    for i in range(len(xs) - 1, -1, -1):
        result.append(xs[i])
    return result
''', [(([],), []), (([1],), [1]), (([1, 2],), [2, 1]), (([1, 2, 3],), [3, 2, 1]),
      (([5, 5, 1],), [1, 5, 5]), (([1, 2, 3, 4],), [4, 3, 2, 1]), (([0, -1],), [-1, 0])]),

    _make('''def is_palindrome(s):
    for i in range(len(s) // 2):
        if s[i] != s[len(s) - 1 - i]:
            return False
    return True
''', [(("",), True), (("a",), True), (("aa",), True), (("ab",), False), (("aba",), True),
      (("abca",), False), (("abba",), True), (("abcd",), False), (("racecar",), True),
      (("abcdba",), False)]),

    _make('''def factorial(n):
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result
''', [((0,), 1), ((1,), 1), ((2,), 2), ((3,), 6), ((4,), 24), ((5,), 120), ((6,), 720)]),

    _make('''def count_in_range(xs, lo, hi):
    count = 0
    for i in range(len(xs)):
        if xs[i] >= lo and xs[i] <= hi:
            count += 1
    return count
''', [(([], 1, 5), 0), (([3], 1, 5), 1), (([1, 5], 1, 5), 2), (([0, 6], 1, 5), 0),
      (([1, 2, 3, 4, 5], 2, 4), 3), (([2, 2, 2], 2, 2), 3), (([5, 1, 9], 1, 5), 2),
      (([7], 7, 7), 1), (([1, 9], 2, 8), 0)]),

    _make('''def second_largest(xs):
    first = float("-inf")
    second = float("-inf")
    for i in range(len(xs)):
        if xs[i] > first:
            second = first
            first = xs[i]
        elif xs[i] > second:
            second = xs[i]
    return second
''', [(([1, 2],), 1), (([2, 1],), 1), (([1, 2, 3],), 2), (([3, 2, 1],), 2), (([5, 5, 3],), 5),
      (([-4, -2, -9],), -4), (([1, 9, 5, 7],), 7), (([4, 4],), 4), (([2, 8, 8],), 8)]),

    _make('''def running_total(xs):
    result = []
    total = 0
    for i in range(len(xs)):
        total += xs[i]
        result.append(total)
    return result
''', [(([],), []), (([4],), [4]), (([1, 2, 3],), [1, 3, 6]), (([1, -1, 1],), [1, 0, 1]),
      (([0, 0],), [0, 0]), (([5, 5, 5, 5],), [5, 10, 15, 20]), (([-2, -3],), [-2, -5])]),

    _make('''def all_positive(xs):
    for i in range(len(xs)):
        if xs[i] <= 0:
            return False
    return True
''', [(([],), True), (([1],), True), (([0],), False), (([-1],), False), (([1, 2, 3],), True),
      (([1, 0, 3],), False), (([1, 2, -3],), False), (([3, 2, 0],), False)]),

    _make('''def average(xs):
    if len(xs) == 0:
        return 0
    total = 0
    for i in range(len(xs)):
        total += xs[i]
    return total / len(xs)
''', [(([],), 0), (([4],), 4), (([1, 3],), 2), (([1, 2, 3],), 2), (([0, 0],), 0),
      (([2, 4, 6, 8],), 5), (([-2, 2],), 0), (([10, 0, 0, 0],), 2.5), (([1, 2],), 1.5)]),

    _make('''def is_sorted(xs):
    for i in range(len(xs) - 1):
        if xs[i] > xs[i + 1]:
            return False
    return True
''', [(([],), True), (([1],), True), (([1, 2],), True), (([2, 1],), False), (([1, 1],), True),
      (([1, 2, 3],), True), (([1, 3, 2],), False), (([3, 1, 2],), False),
      (([1, 2, 2, 3],), True), (([1, 2, 3, 1],), False)]),

    _make('''def merge_two_sorted(a, b):
    i = 0
    j = 0
    result = []
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            result.append(a[i])
            i += 1
        else:
            result.append(b[j])
            j += 1
    while i < len(a):
        result.append(a[i])
        i += 1
    while j < len(b):
        result.append(b[j])
        j += 1
    return result
''', [(([], []), []), (([1], []), [1]), (([], [2]), [2]), (([1, 3], [2, 4]), [1, 2, 3, 4]),
      (([1, 2], [3, 4]), [1, 2, 3, 4]), (([3, 4], [1, 2]), [1, 2, 3, 4]),
      (([1, 1], [1]), [1, 1, 1]), (([1, 5, 9], [2]), [1, 2, 5, 9]),
      (([2], [1, 5, 9]), [1, 2, 5, 9])]),

    _make('''def count_greater(xs, t):
    count = 0
    for i in range(len(xs)):
        if xs[i] > t:
            count += 1
    return count
''', [(([], 3), 0), (([5], 3), 1), (([3], 3), 0), (([1, 2, 3], 2), 1), (([4, 4, 4], 4), 0),
      (([5, 6, 7], 4), 3), (([1, 9, 3, 9], 5), 2), (([-1, -5], -3), 1), (([1, 2], 5), 0)]),

    _make('''def last_index_of(xs, target):
    index = -1
    for i in range(len(xs)):
        if xs[i] == target:
            index = i
    return index
''', [(([], 1), -1), (([1], 1), 0), (([1, 2, 1], 1), 2), (([1, 2, 3], 4), -1), (([5, 5], 5), 1),
      (([1, 2, 3], 1), 0), (([1, 2, 3], 3), 2), (([4, 5, 4, 6], 4), 2)]),

    _make('''def contains_both(xs, a, b):
    found_a = False
    found_b = False
    for i in range(len(xs)):
        if xs[i] == a:
            found_a = True
        if xs[i] == b:
            found_b = True
    return found_a and found_b
''', [(([], 1, 2), False), (([1], 1, 2), False), (([2], 1, 2), False), (([1, 2], 1, 2), True),
      (([2, 1], 1, 2), True), (([1, 1], 1, 1), True), (([3, 4], 1, 2), False),
      (([1, 5, 6], 1, 6), True), (([1, 5, 6], 6, 7), False)]),

    _make('''def count_adjacent_equal(xs):
    count = 0
    for i in range(1, len(xs)):
        if xs[i] == xs[i - 1]:
            count += 1
    return count
''', [(([],), 0), (([1],), 0), (([1, 1],), 1), (([1, 2],), 0), (([1, 1, 1],), 2),
      (([1, 2, 2, 3, 3],), 2), (([2, 1, 1],), 1), (([5, 5, 6],), 1), (([1, 2, 1],), 0)]),

    # --- added in Step 5: comparison-heavy functions where ties matter (< vs <= changes the answer),
    # --- because COMPARISON_BOUNDARY had too few host functions to fill every split.
    _make('''def count_negative(xs):
    count = 0
    for i in range(len(xs)):
        if xs[i] < 0:
            count += 1
    return count
''', [(([],), 0), (([-1],), 1), (([0],), 0), (([1, -2, 3, -4],), 2), (([0, 0, -1],), 1),
      (([-1, -1],), 2), (([5],), 0), (([0, -1],), 1), (([1, 2, -3],), 1)]),

    _make('''def all_below(xs, limit):
    for i in range(len(xs)):
        if xs[i] >= limit:
            return False
    return True
''', [(([], 5), True), (([1], 5), True), (([5], 5), False), (([1, 2, 3], 4), True),
      (([1, 2, 4], 4), False), (([4, 1], 4), False), (([6], 5), False), (([1, 9, 2], 5), False),
      (([-3, -1], 0), True)]),

    _make('''def first_index_above(xs, t):
    for i in range(len(xs)):
        if xs[i] > t:
            return i
    return -1
''', [(([], 3), -1), (([5], 3), 0), (([3], 3), -1), (([1, 2, 3, 4], 2), 2), (([1, 5, 9], 5), 2),
      (([9, 1], 5), 0), (([1, 2], 5), -1), (([1, 2, 3], 0), 0), (([2, 2, 7], 2), 2)]),

    _make('''def is_strictly_increasing(xs):
    for i in range(len(xs) - 1):
        if xs[i] >= xs[i + 1]:
            return False
    return True
''', [(([],), True), (([1],), True), (([1, 2],), True), (([2, 1],), False), (([1, 1],), False),
      (([1, 2, 3],), True), (([1, 2, 2],), False), (([1, 3, 2],), False), (([3, 2, 1],), False)]),
]

BY_NAME: dict[str, Problem] = {p.name: p for p in PROBLEMS}
