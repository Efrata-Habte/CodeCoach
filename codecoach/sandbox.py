"""Run a candidate function against its tests in a SEPARATE process, with a timeout.

Why a subprocess: candidate code can loop forever, crash, or call exit(). In our own process
that would hang or kill the whole experiment. In a child process we just kill it and record
"timeout". Note: this is process isolation + timeout, not a security jail; code that reaches
this point was produced by our own AST edits (the evolvable files get their own static check
in safety.py).
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from config import Config
from codecoach.utils import sha256_text

DEFAULT_TIMEOUT_S = Config().test_timeout_s  # single source of truth: config.py

# Program executed inside the child process. Reads {source, func_name, tests} as JSON on stdin,
# prints {n_passed, reason} as JSON on stdout. Any exception in a test counts as a FAIL.
_RUNNER = r'''
import sys, io, json, copy
payload = json.loads(sys.stdin.read())
real_out = sys.stdout
sys.stdout = io.StringIO()  # swallow print() calls made by the code under test
reason, passed, fn = "ok", 0, None
try:
    scope = {}
    exec(payload["source"], scope)
    fn = scope[payload["func_name"]]
except BaseException:
    reason = "error"  # syntax error, missing function, ...
total = len(payload["tests"])
if fn is not None:
    for args, expected in payload["tests"]:
        try:
            out = fn(*copy.deepcopy(args))  # deepcopy: a buggy function may mutate its input
            ok = out == expected and isinstance(out, bool) == isinstance(expected, bool)
        except BaseException:
            ok = False
        passed += ok
    if passed < total:
        reason = "tests_failed"
real_out.write(json.dumps({"n_passed": passed, "reason": reason}))
'''


@dataclass(frozen=True)
class RunResult:
    """Outcome of running one source against one test list."""
    passed: bool    # True only if ALL tests passed
    n_passed: int
    n_total: int
    reason: str     # "ok" | "tests_failed" | "timeout" | "error"


_CACHE: dict[str, RunResult] = {}  # same (code, tests) always gives the same answer -> never re-run


def run_tests(source: str, func_name: str, tests: list, timeout: float = DEFAULT_TIMEOUT_S) -> RunResult:
    """Run `source` against `tests` in a child process; cached by source hash."""
    tests_json = json.dumps(tests)
    key = sha256_text(f"{source}\0{func_name}\0{tests_json}")
    if key in _CACHE:
        return _CACHE[key]
    payload = json.dumps({"source": source, "func_name": func_name, "tests": tests})
    total = len(tests)
    try:
        # -I = isolated mode: ignore env vars and the current directory when importing
        proc = subprocess.run([sys.executable, "-I", "-c", _RUNNER], input=payload,
                              capture_output=True, text=True, timeout=timeout)
        data = json.loads(proc.stdout)
        result = RunResult(data["reason"] == "ok", data["n_passed"], total, data["reason"])
    except subprocess.TimeoutExpired:
        result = RunResult(False, 0, total, "timeout")  # child is killed by subprocess.run
    except (json.JSONDecodeError, KeyError):
        result = RunResult(False, 0, total, "error")    # child died without reporting (e.g. os._exit)
    _CACHE[key] = result
    return result


def run_tests_many(sources: list[str], func_name: str, tests: list,
                   timeout: float = DEFAULT_TIMEOUT_S) -> list[RunResult]:
    """Run several candidate sources in parallel (waiting on a child process uses no CPU)."""
    workers = min(8, os.cpu_count() or 1)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda s: run_tests(s, func_name, tests, timeout), sources))
