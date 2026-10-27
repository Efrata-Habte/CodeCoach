"""Improver v0: HOW pipeline edits are proposed (the Level 2 target: it can edit ITSELF).

The Level 1 loop calls choose_parent() and propose_child(). In Level 2 the loop also calls
propose_self_edit() to get a modified copy of THIS file, and keeps it only if it improves the
pipeline more than this version does (measured on a separate split).
"""
from codecoach import code_editor as ce

# Relative chance of trying each pipeline operator when proposing a child.
OPERATOR_WEIGHTS = {"tweak_constant": 1.0, "add_feature": 1.0, "remove_feature": 0.5,
                    "change_layer": 0.7, "swap_curation": 0.3}
EDITS_PER_CHILD = 1         # how many edits are stacked into one child
PARENT_SELECTION = "tournament"   # "tournament", "best" or "recent"
TOURNAMENT_K = 3            # tournament size: pick the best of K random accepted versions
STEP_SCALE = 0.3            # how big numeric tweaks are (0.3 = about +-30%)


def choose_parent(archive: list, rng) -> str:
    """Pick the id of the accepted version to improve next.

    `archive` is a list of dicts {"id", "dev_f1", "order"} (accepted pipeline versions only).
    Tournament = some exploration (not always the best) but still pressure toward good parents.
    """
    if PARENT_SELECTION == "best":
        return max(archive, key=lambda v: v["dev_f1"])["id"]
    if PARENT_SELECTION == "recent":
        return max(archive, key=lambda v: v["order"])["id"]
    contenders = rng.sample(archive, min(int(TOURNAMENT_K), len(archive)))
    return max(contenders, key=lambda v: v["dev_f1"])["id"]


def propose_child(parent_source: str, rng) -> tuple:
    """Return (new_source, description): the parent with EDITS_PER_CHILD operator edits applied."""
    names = list(OPERATOR_WEIGHTS)
    weights = [OPERATOR_WEIGHTS[n] for n in names]
    source, notes = parent_source, []
    for _ in range(int(EDITS_PER_CHILD)):
        for _attempt in range(10):  # an operator may not apply to this parent: try another one
            result = ce.PIPELINE_OPERATORS[rng.choices(names, weights)[0]](source, rng, STEP_SCALE)
            if result:
                source = result[0]
                notes.append(result[1])
                break
    return source, "; ".join(notes) or "no_edit"


def propose_self_edit(improver_source: str, rng):
    """Return (new_improver_source, description) or None: a small edit of this very file."""
    name = rng.choice(sorted(ce.IMPROVER_OPERATORS))
    return ce.IMPROVER_OPERATORS[name](improver_source, rng, STEP_SCALE)
