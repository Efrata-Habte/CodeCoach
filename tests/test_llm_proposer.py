"""The optional LLM proposer: off by default, capped, safe, and it can never break the run. (Fake client: no API key needed.)"""
from dataclasses import replace
from types import SimpleNamespace

from config import Config
from codecoach import llm_proposer as lp
from codecoach.archive import Version
from codecoach.code_editor import normalize_source
from codecoach.misconceptions import LABELS
from codecoach.safety import check
from codecoach.utils import ROOT

BASE = normalize_source((ROOT / "evolvable" / "pipeline.py").read_text(encoding="utf-8"))
METRICS = {"dev_macro_f1": 0.4, "per_class_f1": {c: 0.2 for c in LABELS},
           "confusion": [[3, 1, 0, 0, 0], [0, 4, 0, 0, 0], [0, 5, 0, 0, 1], [0, 0, 0, 2, 0], [0, 0, 0, 0, 0]]}
PARENT = Version("v000", "pipeline", None, "baseline", "baseline", True, "baseline", 0, METRICS)


class FakeClient:
    """Stands in for anthropic.Anthropic(): records requests and replies with a canned answer."""

    def __init__(self, text: str = "", stop_reason: str = "end_turn", error: Exception | None = None) -> None:
        self.requests, self.text, self.stop_reason, self.error = [], text, stop_reason, error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=self.text)])


def _answer(source: str, note: str = "Add a feature for off-by-one") -> str:
    return f"{note}\n```python\n{source}\n```"


def test_off_by_default_and_without_a_key(monkeypatch) -> None:
    assert lp.make_proposer(Config()) is None  # use_llm defaults to False
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert lp.make_proposer(replace(Config(), use_llm=True)) is None  # enabled but no key: rule-based only
    assert isinstance(lp.make_proposer(replace(Config(), use_llm=True), client=FakeClient()), lp.LLMProposer)


def test_a_valid_answer_becomes_a_safe_child_with_a_description() -> None:
    new = BASE.replace("EPOCHS = 30", "EPOCHS = 35")
    client = FakeClient(_answer(new, "Train a little longer"))
    out = lp.LLMProposer(Config(), client)(PARENT, BASE)
    assert out == (normalize_source(new), "Train a little longer") and check(out[0]).ok


def test_the_prompt_contains_source_metrics_and_the_three_commonest_errors() -> None:
    client = FakeClient(_answer(BASE))
    lp.LLMProposer(Config(), client)(PARENT, BASE)
    req = client.requests[0]
    prompt = req["messages"][0]["content"]
    assert "EPOCHS = 30" in prompt and "0.400" in prompt and "WRONG_INDEX=0.20" in prompt
    assert "COMPARISON_BOUNDARY predicted as WRONG_INDEX (5x)" in prompt  # the most frequent mistake comes first
    assert prompt.count(" predicted as ") == 3
    assert req["model"] == "claude-opus-5-5" and "COMPLETE" in req["system"] and "temperature" not in req


def test_unsafe_output_is_still_returned_but_the_safety_check_rejects_it() -> None:
    evil = "import os\n" + BASE
    out = lp.LLMProposer(Config(), FakeClient(_answer(evil)))(PARENT, BASE)
    assert out is not None and not check(out[0]).ok  # the LLM gets no extra trust: run_level1 will log it as unsafe


def test_bad_answers_fall_back_to_none() -> None:
    for client in (FakeClient("no code block here"), FakeClient(_answer("def broken(:")),
                   FakeClient(_answer(BASE), stop_reason="refusal"), FakeClient(_answer(BASE), stop_reason="max_tokens"),
                   FakeClient(error=RuntimeError("network down"))):
        assert lp.LLMProposer(Config(), client)(PARENT, BASE) is None


def test_call_budget_is_enforced() -> None:
    client = FakeClient(_answer(BASE))
    proposer = lp.LLMProposer(replace(Config(), max_llm_calls=2), client)
    results = [proposer(PARENT, BASE) for _ in range(5)]
    assert len(client.requests) == 2 and results[2:] == [None, None, None]


def test_an_unevaluated_parent_cannot_be_proposed_from() -> None:
    client = FakeClient(_answer(BASE))
    unevaluated = Version("v001", "pipeline", "v000", "rule_based", "x", False, "duplicate", 1, None)
    assert lp.LLMProposer(Config(), client)(unevaluated, BASE) is None and client.requests == []
