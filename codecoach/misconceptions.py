"""The 5 misconception classes: how to INJECT each bug (mutate) and how to UNDO it (repair).

| Label                | Mutation (inject bug)                          | Repair (matching fix)                  |
|----------------------|------------------------------------------------|----------------------------------------|
| OFF_BY_ONE_RANGE     | range(n)->range(n-1), range(0,n)->range(1,n)   | +-1 on range start/stop                |
| WRONG_INDEX          | xs[i] -> xs[i+1] / xs[i-1]                     | +-1 on subscripts                      |
| COMPARISON_BOUNDARY  | < <-> <=,  > <-> >=                            | flip strictness of each comparison     |
| LOGIC_OPERATOR       | and <-> or, toggle `not` on a condition        | swap each and/or, toggle `not`         |
| WRONG_INITIAL_VALUE  | accumulator init changed (0<->1, xs[0]/-inf->0)| try standard init values               |

All edits are done on the AST (`ast`), never by string replace, so we only ever change real
code (not a "range" inside a string). Each edit touches ONE place -> a single-cause bug.
"""
import ast
from dataclasses import dataclass
from typing import Callable

LABELS = ["OFF_BY_ONE_RANGE", "WRONG_INDEX", "COMPARISON_BOUNDARY", "LOGIC_OPERATOR",
          "WRONG_INITIAL_VALUE"]


@dataclass
class Edit:
    """One possible change: a description for humans + a function that performs it in place."""
    description: str
    apply: Callable[[], None]


def normalize(source: str) -> str:
    """Canonical formatting (ast round-trip) so two equal programs compare equal as text."""
    return ast.unparse(ast.parse(source))


def _int_value(node: ast.AST) -> int | None:
    """Value of an int literal (handles `-1`, which Python parses as unary minus + 1)."""
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _int_value(node.operand)
        return -inner if inner is not None else None
    return None


def _shift(node: ast.expr, delta: int) -> ast.expr:
    """Return `node + delta`, simplified: 5 -> 6, `n - 1` + 1 -> `n`, `i` + 1 -> `i + 1`."""
    value = _int_value(node)
    if value is not None:
        return ast.Constant(value + delta)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        const = _int_value(node.right)
        if const is not None:
            net = (const if isinstance(node.op, ast.Add) else -const) + delta
            if net == 0:
                return node.left
            return ast.BinOp(node.left, ast.Add() if net > 0 else ast.Sub(), ast.Constant(abs(net)))
    return ast.BinOp(node, ast.Add() if delta > 0 else ast.Sub(), ast.Constant(abs(delta)))


def _set(obj: object, attr: str, value: object, description: str) -> Edit:
    """Edit that assigns obj.attr = value (closure created in a function so each Edit keeps its own)."""
    return Edit(description, lambda: setattr(obj, attr, value))


# ---------------------------------------------------------------- OFF_BY_ONE_RANGE
def _range_calls(tree: ast.AST) -> list[ast.Call]:
    """Every `range(...)` call with 1-3 arguments."""
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "range" and 1 <= len(n.args) <= 3]


def _shift_arg(call: ast.Call, idx: int, delta: int, name: str) -> Edit:
    """Edit: shift range argument `idx` by delta (and simplify range(0, n) -> range(n))."""
    def apply() -> None:
        call.args[idx] = _shift(call.args[idx], delta)
        if len(call.args) == 2 and _int_value(call.args[0]) == 0:
            call.args = [call.args[1]]
    return Edit(f"range {name} {delta:+d} (line {call.lineno})", apply)


def _range_mutations(tree: ast.AST) -> list[Edit]:
    """Inject: shrink the stop by one, or start one too late."""
    edits = []
    for call in _range_calls(tree):
        if len(call.args) == 1:  # range(n) -> range(1, n)
            edits.append(Edit(f"range start +1 (line {call.lineno})",
                              lambda c=call: setattr(c, "args", [ast.Constant(1), c.args[0]])))
            edits.append(_shift_arg(call, 0, -1, "stop"))
        else:
            edits.append(_shift_arg(call, 1, -1, "stop"))
            edits.append(_shift_arg(call, 0, +1, "start"))
    return edits


def _range_repairs(tree: ast.AST) -> list[Edit]:
    """Repair candidates: +-1 on every range start and stop."""
    edits = []
    for call in _range_calls(tree):
        slots = [("stop", 0)] if len(call.args) == 1 else [("start", 0), ("stop", 1)]
        edits += [_shift_arg(call, i, d, name) for name, i in slots for d in (-1, +1)]
    return edits


# ---------------------------------------------------------------- WRONG_INDEX
def _index_edits(tree: ast.AST) -> list[Edit]:
    """+-1 on every subscript index (same operator injects the bug and repairs it)."""
    subs = [n for n in ast.walk(tree) if isinstance(n, ast.Subscript)
            and not isinstance(n.slice, (ast.Slice, ast.Tuple))]
    return [_set(s, "slice", _shift(s.slice, d), f"index {d:+d} (line {s.lineno})")
            for s in subs for d in (+1, -1)]


# ---------------------------------------------------------------- COMPARISON_BOUNDARY
_FLIP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt}


def _flip(compare: ast.Compare, k: int) -> Edit:
    """Edit: flip strictness of the k-th operator of a comparison (< <-> <=)."""
    def apply() -> None:
        compare.ops[k] = _FLIP[type(compare.ops[k])]()
    return Edit(f"flip {type(compare.ops[k]).__name__} (line {compare.lineno})", apply)


def _comparison_edits(tree: ast.AST) -> list[Edit]:
    """Every strict/non-strict comparison can be flipped (symmetric: bug and fix)."""
    return [_flip(n, k) for n in ast.walk(tree) if isinstance(n, ast.Compare)
            for k, op in enumerate(n.ops) if type(op) in _FLIP]


# ---------------------------------------------------------------- LOGIC_OPERATOR
def _logic_edits(tree: ast.AST) -> list[Edit]:
    """Swap and/or, or toggle `not` on an if/while condition (symmetric: bug and fix)."""
    edits = []
    for n in ast.walk(tree):
        if isinstance(n, ast.BoolOp):
            new_op = ast.Or() if isinstance(n.op, ast.And) else ast.And()
            edits.append(_set(n, "op", new_op, f"swap and/or (line {n.lineno})"))
        elif isinstance(n, (ast.If, ast.While)):
            t = n.test
            has_not = isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not)
            new_test = t.operand if has_not else ast.UnaryOp(ast.Not(), t)
            edits.append(_set(n, "test", new_test, f"toggle not (line {n.lineno})"))
    return edits


# ---------------------------------------------------------------- WRONG_INITIAL_VALUE
def _is_init_value(v: ast.expr) -> bool:
    """Looks like an accumulator start: 0, 1, -1, 0.0, xs[0], float('-inf')."""
    if _int_value(v) is not None or (isinstance(v, ast.Constant) and type(v.value) is float):
        return True
    if isinstance(v, ast.Subscript) and _int_value(v.slice) == 0:
        return True
    return isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "float"


def _init_sites(tree: ast.AST) -> list[ast.Assign]:
    """Top-level `name = <init value>` statements of the function (before/outside loops)."""
    return [s for s in tree.body[0].body if isinstance(s, ast.Assign) and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name) and _is_init_value(s.value)]


def _expr(text: str) -> ast.expr:
    """Parse a one-line expression into an AST node."""
    return ast.parse(text, mode="eval").body


def _init_mutations(tree: ast.AST) -> list[Edit]:
    """Inject: 0 -> 1; 1, -1, xs[0], -inf -> 0."""
    return [_set(s, "value", _expr("1" if _int_value(s.value) == 0 else "0"),
                 f"init changed (line {s.lineno})") for s in _init_sites(tree)]


def _init_repairs(tree: ast.AST) -> list[Edit]:
    """Repair: try each STANDARD starting value at each init site (one site at a time)."""
    first_param = tree.body[0].args.args[0].arg
    standard = ["0", "1", "-1", f"{first_param}[0]", "float('-inf')", "float('inf')"]
    return [_set(s, "value", _expr(t), f"init := {t} (line {s.lineno})")
            for s in _init_sites(tree) for t in standard
            if ast.dump(_expr(t)) != ast.dump(s.value)]


# mutate-function, repair-function per label. Symmetric classes reuse one function for both.
OPERATORS: dict[str, tuple[Callable, Callable]] = {
    "OFF_BY_ONE_RANGE": (_range_mutations, _range_repairs),
    "WRONG_INDEX": (_index_edits, _index_edits),
    "COMPARISON_BOUNDARY": (_comparison_edits, _comparison_edits),
    "LOGIC_OPERATOR": (_logic_edits, _logic_edits),
    "WRONG_INITIAL_VALUE": (_init_mutations, _init_repairs),
}


def _apply_edits(source: str, edits_fn: Callable) -> list[tuple[str, str]]:
    """Apply each edit separately to a FRESH copy of the AST -> list of (new_source, description)."""
    seen = {normalize(source)}  # drop no-ops and duplicates
    results = []
    for k in range(len(edits_fn(ast.parse(source)))):
        tree = ast.parse(source)  # fresh tree: edits mutate it in place
        edit = edits_fn(tree)[k]
        edit.apply()
        new = ast.unparse(tree)
        if new not in seen:
            seen.add(new)
            results.append((new, edit.description))
    return results


def mutate(source: str, label: str) -> list[tuple[str, str]]:
    """All single-place bugs of class `label` that can be injected into `source`."""
    return _apply_edits(source, OPERATORS[label][0])


def repair(source: str, label: str) -> list[tuple[str, str]]:
    """All single-place fixes of class `label`: the verifier tries these against the tests."""
    return _apply_edits(source, OPERATORS[label][1])
