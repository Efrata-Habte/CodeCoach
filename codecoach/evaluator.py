"""The FIXED fitness function: run a candidate pipeline version and report how good it is.

The evaluator, data, verifier and tests are never editable by the system. A candidate is code the
system wrote itself, so it is treated as untrusted: written to a temp file, imported and run in an
isolated child process (timeout + memory cap), and the protected files are hashed before and after.
It reports dev F1 (used to accept/reject pipelines) and meta_dev F1 (used ONLY to judge improvers
in Level 2). The `test` split is never touched here.
"""
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from config import Config
from codecoach import safety
from codecoach.utils import ROOT

# Program run inside the child process. Reads {path, cfg, seed, model_path, root} as JSON on stdin and
# writes one "@@RESULT@@<json>" line. Candidate print() output is diverted to stderr.
_RUNNER = r'''
import sys, json
real, sys.stdout = sys.stdout, sys.stderr
payload = json.loads(sys.stdin.read())
sys.path.insert(0, payload["root"])
try:
    import importlib.util, torch
    from config import Config
    from codecoach.generator import load_splits
    from codecoach.self_training import self_train
    from codecoach.teacher import evaluate
    spec = importlib.util.spec_from_file_location("candidate_pipeline", payload["path"])
    pipe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipe)
    data = payload["root"] + "/data/generated/"
    splits = load_splits(data + "splits.json")
    verdicts = json.load(open(data + "verdicts.json"))
    r = self_train(pipe, splits, Config(**payload["cfg"]), payload["seed"], verdicts)
    meta = evaluate(r.teacher, splits.meta_dev)
    torch.save({"state_dict": r.teacher.model.state_dict(), "tfidf": r.teacher.featurizer.tfidf}, payload["model_path"])
    out = {"dev_macro_f1": r.final_dev["macro_f1"], "per_class_f1": r.final_dev["per_class_f1"],
           "confusion": r.final_dev["confusion"], "initial_dev_f1": r.initial_dev["macro_f1"],
           "meta_dev_macro_f1": meta["macro_f1"], "meta_dev_per_class_f1": meta["per_class_f1"],
           "n_verified": r.n_verified, "train_time_s": r.train_time_s, "n_params": r.teacher.n_params(),
           "rounds": r.rounds}
except BaseException as e:
    out = {"error": (type(e).__name__ + ": " + str(e))[:300]}
real.write("@@RESULT@@" + json.dumps(out) + "\n")
'''


@dataclass
class EvalOutcome:
    """Result of evaluating one candidate."""
    ok: bool
    reason: str                      # "ok" | "timeout" | "memory" | "crash"
    metrics: dict | None = None
    model_path: Path | None = None   # trained weights in archive/_tmp (moved to the version folder if accepted)
    detail: str = ""


def evaluate_pipeline(source: str, cfg: Config, seed: int | None = None) -> EvalOutcome:
    """Score a pipeline source: Level 0 self-training with it, then dev and meta_dev macro-F1."""
    tmp = ROOT / "archive" / "_tmp"
    name = uuid.uuid4().hex[:8]
    cand, model = tmp / f"cand_{name}.py", tmp / f"model_{name}.pt"
    for p in (cand, model):
        safety.assert_write_allowed(p)
    tmp.mkdir(parents=True, exist_ok=True)
    cand.write_text(source + "\n", encoding="utf-8")
    before = safety.protected_hashes()                       # tamper check, part 1
    payload = json.dumps({"path": str(cand), "cfg": asdict(cfg), "model_path": str(model), "root": str(ROOT),
                          "seed": cfg.seed if seed is None else seed})
    res = safety.run_isolated(["-c", _RUNNER], cfg.eval_timeout_s, cfg.eval_memory_mb, stdin=payload)
    safety.assert_unchanged(before)                          # tamper check, part 2: raises TamperError -> abort run
    cand.unlink(missing_ok=True)
    if res.reason == "timeout":
        return EvalOutcome(False, "timeout", detail=f"> {cfg.eval_timeout_s}s")
    line = next((x for x in res.stdout.splitlines() if x.startswith("@@RESULT@@")), None)
    if line is None:  # child died without reporting (killed, hard crash)
        return EvalOutcome(False, "crash", detail=(res.stderr.strip().splitlines() or ["no output"])[-1][:200])
    out = json.loads(line[len("@@RESULT@@"):])
    if "error" in out:
        reason = "memory" if out["error"].startswith("MemoryError") else "crash"
        model.unlink(missing_ok=True)
        return EvalOutcome(False, reason, detail=out["error"])
    return EvalOutcome(True, "ok", out, model)
