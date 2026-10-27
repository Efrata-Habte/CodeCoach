"""OPTIONAL proposer: ask Claude for an edited copy of the pipeline file. Default OFF; the project works without it.

Used only if config.use_llm is True AND ANTHROPIC_API_KEY is set. Claude gets the parent source, its metrics, its per-class
F1 and its 3 most common error types, and must answer with a COMPLETE new file. That file goes through exactly the same
static safety check, isolated evaluation and dev gate as every rule-based child: the LLM gets no extra trust. Any problem
(no key, API error, refusal, no code, a syntax error, call budget spent) returns None and the loop uses the rule-based
proposer instead. This is the open-ended cousin of the constrained editor in code_editor.py (what DGM does with an LLM).
"""
import ast
import os
import re
from typing import Any

from config import Config
from codecoach.archive import Version
from codecoach.misconceptions import LABELS

MODEL = "claude-opus-5-5"
SYSTEM = """You improve a small machine-learning pipeline by editing ITS OWN source file.
Return the COMPLETE new file in one ```python block, preceded by ONE line describing your change.
Rules (a static checker enforces them; a violating file is discarded unharmed):
- Keep every existing top-level constant and function name and signature (NGRAM_RANGE, MAX_FEATURES, HIDDEN_SIZES, DROPOUT, LR,
  EPOCHS, SELF_TRAIN_ROUNDS, POOL_PER_ROUND, MIN_DELTA, CURATION, PER_CLASS_CAP, extra_features, build_teacher, curate).
- Imports allowed: numpy, torch, torch.nn, torch.nn.functional, random, math, and `from codecoach import feature_blocks as fb`.
- extra_features may only call functions that already exist in feature_blocks (fb.count_comparisons, fb.count_range_calls,
  fb.count_subscripts, fb.count_boolops, fb.count_const_assigns, fb.has_while, fb.count_plus_minus_one, fb.max_loop_depth).
- No file, network, process or dynamic-code access; no code that runs at import time except constants and definitions.
- Make ONE focused change aimed at the classes the metrics show are weakest."""


def top_confusions(confusion: list[list[int]], k: int = 3) -> list[str]:
    """The k most frequent (true -> predicted) mistakes in a confusion matrix, as readable strings."""
    pairs = [(confusion[i][j], LABELS[i], LABELS[j]) for i in range(len(LABELS)) for j in range(len(LABELS)) if i != j and confusion[i][j]]
    return [f"{t} predicted as {p} ({n}x)" for n, t, p in sorted(pairs, reverse=True)[:k]]


def build_prompt(parent_source: str, metrics: dict) -> str:
    """What Claude is told: the source, how good it is, per-class F1 and the most common errors."""
    f1 = ", ".join(f"{c}={v:.2f}" for c, v in metrics["per_class_f1"].items())
    return (f"Current pipeline file:\n```python\n{parent_source}\n```\n\n"
            f"Its dev macro-F1 is {metrics['dev_macro_f1']:.3f}. Per-class dev F1: {f1}.\n"
            f"Most common errors: {'; '.join(top_confusions(metrics['confusion'])) or 'none'}.\n"
            "Propose ONE improved version of the whole file.")


def extract_file(text: str) -> tuple[str | None, str]:
    """(normalized new source or None, one-line description) from Claude's answer."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    if not match:
        return None, ""
    try:
        code = ast.unparse(ast.parse(match.group(1)))
    except SyntaxError:
        return None, ""
    note = text[:match.start()].strip().splitlines()
    return code, (note[0] if note else "LLM edit")[:100]


class LLMProposer:
    """Callable (parent_version, parent_source) -> (child_source, description) or None. Counts its API calls."""

    def __init__(self, cfg: Config, client: Any = None) -> None:
        self.cfg, self.calls = cfg, 0
        if client is None:
            import anthropic  # imported lazily: the package is optional
            client = anthropic.Anthropic()
        self.client = client

    def __call__(self, parent: Version, parent_source: str) -> tuple[str, str] | None:
        if self.calls >= self.cfg.max_llm_calls or not parent.metrics:  # budget cap (config.max_llm_calls)
            return None
        self.calls += 1
        try:
            response = self.client.messages.create(
                model=MODEL, max_tokens=16000, output_config={"effort": "medium"}, system=SYSTEM,
                messages=[{"role": "user", "content": build_prompt(parent_source, parent.metrics)}])
        except Exception as err:  # any API/network problem: fall back to the rule-based proposer, never crash the run
            print(f"llm proposer: API error ({type(err).__name__}); using the rule-based proposer")
            return None
        if response.stop_reason in ("refusal", "max_tokens"):
            return None
        code, note = extract_file("".join(b.text for b in response.content if b.type == "text"))
        return (code, note) if code else None


def make_proposer(cfg: Config, client: Any = None) -> LLMProposer | None:
    """The proposer if it is enabled and usable, else None. Off by default."""
    if not cfg.use_llm:
        return None
    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        print("use_llm is on but ANTHROPIC_API_KEY is not set: using the rule-based proposer only")
        return None
    return LLMProposer(cfg, client)
