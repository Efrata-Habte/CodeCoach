"""Rule-based AST editing: the toolbox the (default) proposer uses to rewrite source files.

Every operator parses the source, changes the tree in a small controlled way, and unparses it.
It returns (new_source, human_readable_description) or None when it cannot apply or would change
nothing. The edit space is deliberately CONSTRAINED (bounded numbers, a fixed menu of feature
blocks, a fixed menu of curation strategies) so most children run: this is constrained program
search, a small-scale cousin of what the Darwin Godel Machine does with an LLM.
Note: ast.unparse drops comments, so archived versions are comment-free (diffs stay clean).
"""
import ast
import random
from typing import Callable

from codecoach.feature_blocks import BLOCKS

Result = tuple[str, str] | None

# Hard bounds for every tunable number: a self-edit can never set LR = 1000 or EPOCHS = 10**9.
PIPELINE_BOUNDS = {"LR": (1e-4, 1e-2), "EPOCHS": (5, 100), "DROPOUT": (0.0, 0.6),
                   "MAX_FEATURES": (256, 8192), "SELF_TRAIN_ROUNDS": (1, 8), "POOL_PER_ROUND": (50, 600),
                   "MIN_DELTA": (0.0, 0.05), "PER_CLASS_CAP": (5, 100), "NGRAM_RANGE": (1, 6)}
IMPROVER_BOUNDS = {"EDITS_PER_CHILD": (1, 3), "TOURNAMENT_K": (2, 6), "STEP_SCALE": (0.05, 0.8),
                   "OPERATOR_WEIGHTS": (0.05, 3.0)}
CURATION_CHOICES = ("none", "dedup_cap", "balance")
PARENT_CHOICES = ("tournament", "best", "recent")
LAYER_SIZES = (16, 32, 64, 128, 256, 512)


def normalize_source(source: str) -> str:
    """Canonical text of a source file (what ast.unparse would produce)."""
    return ast.unparse(ast.parse(source))


def _finish(tree: ast.AST, before: str, description: str) -> Result:
    """Unparse an edited tree; None if the edit changed nothing."""
    new = ast.unparse(ast.fix_missing_locations(tree))
    return None if new == normalize_source(before) else (new, description)


def _assign(tree: ast.Module, name: str) -> ast.Assign | None:
    """The module-level statement `name = ...`, if present."""
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and \
                isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == name:
            return stmt
    return None


def _is_number(node: ast.AST) -> bool:
    """A plain int/float literal (bool excluded)."""
    return isinstance(node, ast.Constant) and type(node.value) in (int, float)


def _slots(tree: ast.Module, bounds: dict) -> list[tuple[str, ast.Constant, tuple]]:
    """Every tunable number: (display name, its Constant node, allowed (lo, hi))."""
    slots = []
    for name, rng_ in bounds.items():
        stmt = _assign(tree, name)
        if stmt is None:
            continue
        v = stmt.value
        if _is_number(v):
            slots.append((name, v, rng_))
        elif isinstance(v, ast.Tuple):  # e.g. NGRAM_RANGE = (2, 4)
            slots += [(f"{name}[{i}]", e, rng_) for i, e in enumerate(v.elts) if _is_number(e)]
        elif isinstance(v, ast.Dict):   # e.g. OPERATOR_WEIGHTS = {...}
            slots += [(f"{name}[{k.value}]", e, rng_) for k, e in zip(v.keys, v.values) if _is_number(e)]
    return slots


def tweak_constant(source: str, rng: random.Random, step_scale: float, bounds: dict | None = None) -> Result:
    """Multiply one tunable number by (1 +- step_scale); ints stay ints; result stays inside its bounds."""
    tree = ast.parse(source)
    slots = _slots(tree, PIPELINE_BOUNDS if bounds is None else bounds)
    if not slots:
        return None
    label, node, (lo, hi) = rng.choice(slots)
    old = node.value
    factor = 1 + rng.choice((-1, 1)) * step_scale * rng.uniform(0.5, 1.5)
    if isinstance(old, int):
        new = int(round(old * factor)) or old
        new = new if new != old else old + (1 if factor > 1 else -1)
        new = int(min(max(new, lo), hi))
    else:
        new = min(max(float(f"{old * factor:.3g}"), lo), hi)
    if new == old:
        return None
    node.value = new
    ngram = _assign(tree, "NGRAM_RANGE")
    if ngram is not None and isinstance(ngram.value, ast.Tuple):
        a, b = (e.value for e in ngram.value.elts)
        if a > b:  # n-gram range must stay ordered
            return None
    return _finish(tree, source, f"tweak_constant: {label} {old} -> {new}")


def tweak_improver_constant(source: str, rng: random.Random, step_scale: float) -> Result:
    """tweak_constant, but for the improver file's own knobs (Level 2)."""
    return tweak_constant(source, rng, step_scale, IMPROVER_BOUNDS)


def _feature_list(tree: ast.Module) -> ast.List | None:
    """The list literal returned by extra_features()."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "extra_features":
            for stmt in node.body:
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.List):
                    return stmt.value
    return None


def _block_name(call: ast.expr) -> str | None:
    """`fb.count_x(code)` -> "count_x"."""
    return call.func.attr if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) else None


def add_feature(source: str, rng: random.Random, step_scale: float) -> Result:
    """Append a whitelisted feature block that is not used yet."""
    tree = ast.parse(source)
    lst = _feature_list(tree)
    if lst is None:
        return None
    options = sorted(set(BLOCKS) - {_block_name(e) for e in lst.elts})
    if not options:
        return None
    name = rng.choice(options)
    lst.elts.append(ast.parse(f"fb.{name}(code)", mode="eval").body)
    return _finish(tree, source, f"add_feature: {name}")


def remove_feature(source: str, rng: random.Random, step_scale: float) -> Result:
    """Drop one feature block (keeps at least one)."""
    tree = ast.parse(source)
    lst = _feature_list(tree)
    if lst is None or len(lst.elts) <= 1:
        return None
    gone = lst.elts.pop(rng.randrange(len(lst.elts)))
    return _finish(tree, source, f"remove_feature: {_block_name(gone)}")


def change_layer(source: str, rng: random.Random, step_scale: float) -> Result:
    """Add, remove or resize one hidden layer (1-4 layers, sizes from a fixed menu)."""
    tree = ast.parse(source)
    stmt = _assign(tree, "HIDDEN_SIZES")
    if stmt is None or not isinstance(stmt.value, ast.List) or not all(_is_number(e) for e in stmt.value.elts):
        return None
    sizes = [e.value for e in stmt.value.elts]
    before = list(sizes)
    op = rng.choice((["add"] if len(sizes) < 4 else []) + (["remove"] if len(sizes) > 1 else []) + ["resize"])
    if op == "add":
        sizes.insert(rng.randint(0, len(sizes)), rng.choice(LAYER_SIZES))
    elif op == "remove":
        sizes.pop(rng.randrange(len(sizes)))
    else:
        i = rng.randrange(len(sizes))
        sizes[i] = rng.choice([s for s in LAYER_SIZES if s != sizes[i]])
    stmt.value = ast.List([ast.Constant(s) for s in sizes], ast.Load())
    return _finish(tree, source, f"change_layer: {before} -> {sizes}")


def _swap_choice(source: str, rng: random.Random, name: str, choices: tuple, op: str) -> Result:
    """Switch the string constant `name` to a different allowed value."""
    tree = ast.parse(source)
    stmt = _assign(tree, name)
    if stmt is None or not isinstance(stmt.value, ast.Constant):
        return None
    old = stmt.value.value
    new = rng.choice([c for c in choices if c != old])
    stmt.value = ast.Constant(new)
    return _finish(tree, source, f"{op}: {old} -> {new}")


def swap_curation(source: str, rng: random.Random, step_scale: float) -> Result:
    """Switch between the whitelisted curation strategies."""
    return _swap_choice(source, rng, "CURATION", CURATION_CHOICES, "swap_curation")


def swap_parent_selection(source: str, rng: random.Random, step_scale: float) -> Result:
    """Switch the improver's parent-selection rule (Level 2)."""
    return _swap_choice(source, rng, "PARENT_SELECTION", PARENT_CHOICES, "swap_parent_selection")


Operator = Callable[[str, random.Random, float], Result]
PIPELINE_OPERATORS: dict[str, Operator] = {
    "tweak_constant": tweak_constant, "add_feature": add_feature, "remove_feature": remove_feature,
    "change_layer": change_layer, "swap_curation": swap_curation}
IMPROVER_OPERATORS: dict[str, Operator] = {
    "tweak_constant": tweak_improver_constant, "swap_parent_selection": swap_parent_selection}
