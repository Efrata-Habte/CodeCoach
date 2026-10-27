"""Style variants: the SAME correct function written in different (equivalent) ways.

Why: 20 functions with single-place bugs give only ~150 buggy programs, too few for stable
gates. Students write the same logic in many styles, so we rewrite each reference solution
before injecting bugs. Rewrites never change behaviour (a test checks every variant passes
the problem's tests) and variants stay in their problem's split, so there is no leakage.

  1. expand augmented assignment:  total += x      ->  total = total + x
  2. mirror ordering comparisons:  a > b           ->  b < a
  3. split an `and` condition:     if A and B: ..  ->  if A: (if B: ..)
Every subset of the 3 rewrites is tried (up to 8 variants); duplicates are dropped.
"""
import ast
import itertools

_MIRROR = {ast.Lt: ast.Gt, ast.LtE: ast.GtE, ast.Gt: ast.Lt, ast.GtE: ast.LtE}


class _ExpandAugAssign(ast.NodeTransformer):
    """`x += e` -> `x = x + e` (same for -=, *=, ...)."""

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        if not isinstance(node.target, ast.Name):
            return node
        name = node.target.id
        return ast.Assign([ast.Name(name, ast.Store())],
                          ast.BinOp(ast.Name(name, ast.Load()), node.op, node.value))


class _MirrorCompare(ast.NodeTransformer):
    """`a < b` -> `b > a` for single ordering comparisons (== is left alone: unusual style)."""

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if len(node.ops) == 1 and type(node.ops[0]) in _MIRROR:
            return ast.Compare(node.comparators[0], [_MIRROR[type(node.ops[0])]()], [node.left])
        return node


class _SplitAnd(ast.NodeTransformer):
    """`if A and B: body` (no else) -> nested ifs. Short-circuit order is preserved."""

    def visit_If(self, node: ast.If) -> ast.AST:
        self.generic_visit(node)
        test = node.test
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And) and not node.orelse:
            body = node.body
            for cond in reversed(test.values):  # innermost condition wraps the body first
                body = [ast.If(cond, body, [])]
            return body[0]
        return node


REWRITES = [_ExpandAugAssign, _MirrorCompare, _SplitAnd]


def style_variants(source: str) -> list[str]:
    """The original (first) plus every distinct rewrite combination, as normalized text."""
    seen: set[str] = set()
    out: list[str] = []
    for flags in itertools.product([False, True], repeat=len(REWRITES)):
        tree = ast.parse(source)
        for use, rewrite in zip(flags, REWRITES):
            if use:
                tree = rewrite().visit(tree)
        text = ast.unparse(ast.fix_missing_locations(tree))  # new statements need line numbers to unparse
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out
