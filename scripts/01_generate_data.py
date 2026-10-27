"""Script 01: generate the dataset and splits. Usage: python scripts/01_generate_data.py [--quick]"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `codecoach`, `config` importable

from config import get_config
from codecoach.generator import SPLIT_NAMES, build_splits, class_table, save_splits
from codecoach.misconceptions import LABELS
from codecoach.utils import ROOT, set_seed
from codecoach.verifier import build_verdict_table, verdict_key

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="smaller budgets (smoke test / demo)")
    cfg = get_config(ap.parse_args().quick)
    set_seed(cfg.seed)
    splits = build_splits(cfg)
    out = ROOT / "data" / "generated"
    save_splits(splits, out / "splits.json")
    # The verifier is fixed and model-independent, so answer every (program, label) question ONCE here.
    table = build_verdict_table(splits.pool)
    (out / "verdicts.json").write_text(json.dumps(table), encoding="utf-8")
    right = [table[verdict_key(p.code, p.hidden_label)] == "verified" for p in splits.pool]
    wrong = [table[verdict_key(p.code, lab)] == "verified" for p in splits.pool for lab in LABELS
             if lab != p.hidden_label]
    print(f"verifier on pool: accepts the TRUE label {sum(right)}/{len(right)}; "
          f"accepts a WRONG label {sum(wrong)}/{len(wrong)} ({100 * sum(wrong) / len(wrong):.1f}%)")
    print(class_table(splits))
    for name in SPLIT_NAMES:
        print(f"{name:9s} problems: {', '.join(splits.problems[name])}")
