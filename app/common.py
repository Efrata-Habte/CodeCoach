"""Shared helpers for the web app: paths, loaders, colors, small formatting functions.

The app is READ-ONLY over archive/ and results/ (the live pages write only to archive/live/).
"""
import ast
import difflib
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codecoach.archive import Archive, Version  # noqa: E402

GREEN, GREY, BLUE, ORANGE, AQUA, RED = "#2e9e44", "#8a8985", "#2a78d6", "#eb6834", "#1baf7a", "#d03b3b"
SHORT = {"OFF_BY_ONE_RANGE": "off-by-one", "WRONG_INDEX": "wrong index", "COMPARISON_BOUNDARY": "comparison",
         "LOGIC_OPERATOR": "logic op", "WRONG_INITIAL_VALUE": "initial value"}
RUN_HINT = "No results yet. Run `python run_all.py --quick` first (about 3 minutes), then reload this page."


def get_archive() -> Archive:
    """The main archive (a small JSON read; cheap enough to repeat on every rerun)."""
    return Archive(ROOT / "archive")


def read_json(name: str) -> dict | None:
    """A results/*.json file, or None if it has not been produced yet."""
    path = ROOT / "results" / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def has_results(archive: Archive) -> bool:
    """True if there is something to show; otherwise tell the user how to produce it."""
    if not archive.versions:
        st.info(RUN_HINT)
    return bool(archive.versions)


def best_version(archive: Archive) -> Version:
    """Highest dev-F1 accepted pipeline version."""
    return max(archive.accepted(), key=lambda v: v.metrics["dev_macro_f1"])


def n_features(source: str) -> int:
    """How many structural-feature calls the pipeline's extra_features() makes."""
    return source.count("fb.")


def source_diff(old: str, new: str, old_name: str, new_name: str) -> str:
    """Unified diff text (shown with st.code(language='diff'): + green, - red)."""
    lines = difflib.unified_diff(old.splitlines(), new.splitlines(), old_name, new_name, lineterm="", n=1)
    return "\n".join(lines) or "(no difference)"


def is_single_function(code: str) -> bool:
    """The Try-it page needs exactly one function definition."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    return len(tree.body) >= 1 and sum(isinstance(n, ast.FunctionDef) for n in tree.body) == 1 and \
        isinstance(tree.body[0], ast.FunctionDef)
