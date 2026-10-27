"""The archive: every version the system ever produced, accepted OR rejected, stored on disk.

Darwin-Godel-Machine style: instead of one "current" pipeline there is a growing TREE of versions.
Any accepted version can become a parent, and rejected ones are kept (flagged) for failure analysis.
Layout:  archive/index.json                      one record per version (metrics, parent, reason, ...)
         archive/v000/pipeline.py (+ model.pt)    pipeline versions
         archive/improver_v000/improver.py        improver versions (Level 2)
Every write goes through safety.assert_write_allowed: the system can only write under archive/.
"""
import importlib.util
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType

from codecoach import safety
from codecoach.utils import ROOT

FILE_NAMES = {"pipeline": "pipeline.py", "improver": "improver.py"}
ID_PREFIX = {"pipeline": "v", "improver": "improver_v"}


@dataclass
class Version:
    """One record of the archive (the source code itself is a separate file)."""
    id: str
    kind: str                       # "pipeline" | "improver"
    parent_id: str | None
    proposer: str                   # "baseline" | "rule_based" | "llm"
    edit: str                       # human-readable description of the change
    accepted: bool
    reason: str                     # "baseline" | "accepted" | "no_improvement" | "unsafe: ..." | "crash" | ...
    generation: int
    metrics: dict | None = None     # None when the version was never evaluated (unsafe, duplicate)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class Archive:
    """Reads and writes archive/. Construct with no argument for the real archive."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else ROOT / "archive"
        self.index_path = self.root / "index.json"
        self.versions: list[Version] = []
        if self.index_path.exists():
            self.versions = [Version(**v) for v in json.loads(self.index_path.read_text(encoding="utf-8"))]

    def _write(self, path: Path, text: str) -> None:
        """Write a text file, only if it is inside archive/."""
        safety.assert_write_allowed(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def next_id(self, kind: str) -> str:
        """Next free id, e.g. v003 or improver_v001 (rejected versions use up ids too)."""
        n = sum(v.kind == kind for v in self.versions)
        return f"{ID_PREFIX[kind]}{n:03d}"

    def add(self, version: Version, source: str, model_tmp: Path | None = None) -> None:
        """Store a version: its source, its model (accepted pipeline versions only) and an index entry."""
        folder = self.root / version.id
        self._write(folder / FILE_NAMES[version.kind], source + "\n")
        if model_tmp is not None and Path(model_tmp).exists():
            if version.accepted:
                safety.assert_write_allowed(folder / "model.pt")
                shutil.move(str(model_tmp), str(folder / "model.pt"))
            else:
                Path(model_tmp).unlink()  # rejected versions keep source + metrics, not weights
        self.versions.append(version)
        tmp = self.root / "index.json.tmp"  # write-then-rename: a crash never leaves a half-written index
        self._write(tmp, json.dumps([asdict(v) for v in self.versions], indent=1))
        os.replace(tmp, self.index_path)

    def get(self, version_id: str) -> Version:
        """Record by id."""
        return next(v for v in self.versions if v.id == version_id)

    def source(self, version_id: str) -> str:
        """Source text of a version."""
        v = self.get(version_id)
        return (self.root / v.id / FILE_NAMES[v.kind]).read_text(encoding="utf-8")

    def accepted(self, kind: str = "pipeline") -> list[Version]:
        """Accepted versions of one kind, oldest first (these may become parents)."""
        return [v for v in self.versions if v.kind == kind and v.accepted]

    def lineage(self, version_id: str) -> list[Version]:
        """Chain of ancestors from the baseline down to this version."""
        chain = [self.get(version_id)]
        while chain[0].parent_id:
            chain.insert(0, self.get(chain[0].parent_id))
        return chain


def import_source(source: str, name: str) -> ModuleType:
    """Import a source STRING as a module (via a file in archive/_tmp, the only place we may write)."""
    path = ROOT / "archive" / "_tmp" / f"{name}.py"
    safety.assert_write_allowed(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source + "\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
