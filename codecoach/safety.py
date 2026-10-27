"""Guard-rails for bounded, sandboxed self-improvement (the slide on safety, mapped to code).

1. Edit whitelist      - the system only READS evolvable/ and only WRITES archive/.
2. Static check        - every candidate source is parsed and rejected for forbidden imports/names.
3. Tamper detection    - SHA-256 of all fixed files before/after every evaluation; mismatch = abort.
4. Isolated execution  - candidates run in a child process with a timeout and a memory cap.
Honest limit: the static check is a FIRST filter, not a proof. Containment really comes from 3 and 4
(a misbehaving candidate is killed, and any change to the evaluator is detected).
"""
import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from codecoach.utils import ROOT, sha256_file

MAX_SOURCE_CHARS = 20_000
ALLOWED_IMPORTS = {"pipeline": {"numpy", "torch", "torch.nn", "torch.nn.functional", "random", "math"},
                   "improver": {"random", "math"}}
ALLOWED_FROM = {"pipeline": {("codecoach", "feature_blocks")}, "improver": {("codecoach", "code_editor")}}
# Names no candidate may mention: file/network/process access, dynamic code, and the data we protect.
FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr",
    "delattr", "input", "breakpoint", "os", "sys", "subprocess", "importlib", "socket", "shutil", "pathlib",
    "pickle", "ctypes", "builtins", "multiprocessing", "threading", "urllib", "requests",
    "load", "loads", "save", "dump", "fromfile", "tofile", "memmap", "loadtxt", "savetxt", "genfromtxt",
    "hub", "jit", "distributed",                                # file/network helpers inside numpy/torch
    "splits", "Splits", "hidden_label", "verdicts", "verify", "tests", "PROBLEMS", "BY_NAME",   # our data
}
REQUIRED = {
    "pipeline": ({"extra_features", "build_teacher", "curate"},
                 {"NGRAM_RANGE", "MAX_FEATURES", "HIDDEN_SIZES", "DROPOUT", "LR", "EPOCHS", "SELF_TRAIN_ROUNDS",
                  "POOL_PER_ROUND", "MIN_DELTA", "CURATION", "PER_CLASS_CAP"}),
    "improver": ({"choose_parent", "propose_child", "propose_self_edit"},
                 {"OPERATOR_WEIGHTS", "EDITS_PER_CHILD", "PARENT_SELECTION", "TOURNAMENT_K", "STEP_SCALE"}),
}
PROTECTED_DIRS = ("codecoach", "data", "tests", "scripts", "evolvable")  # + config.py


@dataclass(frozen=True)
class SafetyReport:
    """Result of the static check: ok, or the list of reasons it was rejected."""
    ok: bool
    reasons: list[str]


def _import_problems(node: ast.AST, kind: str) -> list[str]:
    """Reasons an import statement is not allowed."""
    if isinstance(node, ast.Import):
        return [f"import {a.name}" for a in node.names if a.name not in ALLOWED_IMPORTS[kind]]
    if node.module in ALLOWED_IMPORTS[kind]:
        return []
    ok = {n for m, n in ALLOWED_FROM[kind] if m == node.module}
    return [f"from {node.module} import {a.name}" for a in node.names if a.name not in ok]


def check(source: str, kind: str = "pipeline") -> SafetyReport:
    """Static check of a candidate file. kind = "pipeline" or "improver"."""
    if len(source) > MAX_SOURCE_CHARS:
        return SafetyReport(False, ["too_long"])
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return SafetyReport(False, ["syntax_error"])
    bad: list[str] = []
    for stmt in tree.body:  # nothing may RUN at import time except definitions
        if not isinstance(stmt, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef,
                                 ast.ClassDef)) and not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)):
            bad.append(f"top_level_code: {type(stmt).__name__}")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            bad += [f"forbidden_import: {p}" for p in _import_problems(node, kind)]
            if any(a.name == "*" for a in node.names):
                bad.append("star_import")
        names = [node.id] if isinstance(node, ast.Name) else [node.attr] if isinstance(node, ast.Attribute) else []
        for name in names:
            if name in FORBIDDEN_NAMES:
                bad.append(f"forbidden_name: {name}")
            if name.startswith("__") and name.endswith("__"):
                bad.append(f"dunder_access: {name}")  # blocks ().__class__.__subclasses__() style escapes
    funcs, consts = REQUIRED[kind]
    defined_f = {s.name for s in tree.body if isinstance(s, ast.FunctionDef)}
    defined_c = {t.id for s in tree.body if isinstance(s, ast.Assign) for t in s.targets if isinstance(t, ast.Name)}
    bad += [f"missing_function: {f}" for f in sorted(funcs - defined_f)]
    bad += [f"missing_constant: {c}" for c in sorted(consts - defined_c)]
    return SafetyReport(not bad, sorted(set(bad)))


def assert_write_allowed(path: Path) -> None:
    """The system may write only under archive/ (never over the fixed library or evolvable/)."""
    if not Path(path).resolve().is_relative_to((ROOT / "archive").resolve()):  # ROOT looked up at call time
        raise PermissionError(f"write outside archive/ refused: {path}")


class TamperError(RuntimeError):
    """A protected file changed while the system was running."""


def protected_hashes(root: Path = ROOT) -> dict[str, str]:
    """SHA-256 of every fixed file (library, data, tests, scripts, baseline evolvable files, config)."""
    files = [root / "config.py"] + [p for d in PROTECTED_DIRS for p in sorted((root / d).rglob("*")) if p.is_file()]
    return {str(p.relative_to(root)): sha256_file(p) for p in files
            if p.exists() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def assert_unchanged(before: dict[str, str], root: Path = ROOT) -> None:
    """Abort (raise) if any protected file was changed, added or removed since `before`."""
    after = protected_hashes(root)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    if changed:
        raise TamperError(f"protected files changed: {changed}")


@dataclass(frozen=True)
class IsolatedResult:
    """Outcome of running a candidate in a child process."""
    ok: bool
    reason: str        # "ok" | "timeout" | "crashed"
    stdout: str
    stderr: str


def _limit_memory_windows(proc: subprocess.Popen, memory_mb: int) -> None:
    """Windows: put the child in a Job Object with a per-process memory limit."""
    import ctypes
    from ctypes import wintypes as w

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", w.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class Extended(ctypes.Structure):
        _fields_ = [("Basic", Basic), ("Io", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = w.HANDLE
    k32.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    info = Extended()
    info.Basic.LimitFlags = 0x100                       # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = memory_mb * 1024 * 1024
    k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    k32.AssignProcessToJobObject(job, int(proc._handle))  # noqa: SLF001 (Popen exposes no public handle)


def run_isolated(args: list[str], timeout_s: float, memory_mb: int, stdin: str = "") -> IsolatedResult:
    """Run `python -E -P <args>` as a child with a time limit and a memory cap; kill it if it misbehaves.

    -E ignores PYTHON* env vars and -P keeps the current directory off the import path (a planted
    json.py cannot hijack us). We do NOT use -I here: it also hides user site-packages, where torch lives.
    """
    pre = None
    if sys.platform != "win32":  # Linux/macOS: address-space limit applied in the child before it starts
        import resource
        pre = lambda: resource.setrlimit(resource.RLIMIT_AS, (memory_mb << 20, memory_mb << 20))  # noqa: E731
    cmd = [sys.executable, "-E", "-P", *args]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, preexec_fn=pre) if pre else \
        subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if sys.platform == "win32":
        _limit_memory_windows(proc, memory_mb)
    try:
        out, err = proc.communicate(stdin, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return IsolatedResult(False, "timeout", out, err)
    return IsolatedResult(proc.returncode == 0, "ok" if proc.returncode == 0 else "crashed", out, err)
