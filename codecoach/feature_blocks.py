"""Whitelisted feature building blocks. evolvable/pipeline.py may CALL these but not define new ones.

Each block reads a code string and returns one number describing its structure. Why a fixed menu:
the self-editing system can only combine tools we wrote and tested, so a "new feature" can never
smuggle in file access, labels or test data. (Constrained program search, like DGM at small scale.)
"""
import ast
from typing import Callable


def _nodes(code: str) -> list[ast.AST]:
    """All AST nodes of `code` (empty list if it does not parse)."""
    try:
        return list(ast.walk(ast.parse(code)))
    except SyntaxError:
        return []


def count_comparisons(code: str) -> float:
    """Number of comparison operators (<, <=, ==, ...): hints at COMPARISON_BOUNDARY."""
    return float(sum(len(n.ops) for n in _nodes(code) if isinstance(n, ast.Compare)))


def count_range_calls(code: str) -> float:
    """Number of range(...) calls: hints at OFF_BY_ONE_RANGE."""
    return float(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "range"
                     for n in _nodes(code)))


def count_subscripts(code: str) -> float:
    """Number of xs[...] accesses: hints at WRONG_INDEX."""
    return float(sum(isinstance(n, ast.Subscript) for n in _nodes(code)))


def count_boolops(code: str) -> float:
    """Number of `and`/`or` expressions: hints at LOGIC_OPERATOR."""
    return float(sum(isinstance(n, ast.BoolOp) for n in _nodes(code)))


def count_const_assigns(code: str) -> float:
    """Assignments of a plain number (`total = 0`): hints at WRONG_INITIAL_VALUE."""
    def is_number(v: ast.AST) -> bool:
        inner = v.operand if isinstance(v, ast.UnaryOp) else v
        return isinstance(inner, ast.Constant) and isinstance(inner.value, (int, float))
    return float(sum(isinstance(n, ast.Assign) and is_number(n.value) for n in _nodes(code)))


def has_while(code: str) -> float:
    """1.0 if the code contains a while loop."""
    return float(any(isinstance(n, ast.While) for n in _nodes(code)))


def count_plus_minus_one(code: str) -> float:
    """Number of `x + 1` / `x - 1` expressions: the classic off-by-one fingerprint."""
    def is_one(v: ast.AST) -> bool:
        return isinstance(v, ast.Constant) and v.value == 1
    return float(sum(isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub))
                     and (is_one(n.left) or is_one(n.right)) for n in _nodes(code)))


def max_loop_depth(code: str) -> float:
    """Deepest nesting of for/while loops."""
    def depth(node: ast.AST) -> int:
        inner = max((depth(c) for c in ast.iter_child_nodes(node)), default=0)
        return inner + isinstance(node, (ast.For, ast.While))
    try:
        return float(depth(ast.parse(code)))
    except SyntaxError:
        return 0.0


BLOCKS: dict[str, Callable[[str], float]] = {
    f.__name__: f for f in (count_comparisons, count_range_calls, count_subscripts, count_boolops,
                            count_const_assigns, has_while, count_plus_minus_one, max_loop_depth)
}
