"""Script 01: generate the dataset and splits. Usage: python scripts/01_generate_data.py [--quick]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `codecoach`, `config` importable

from config import get_config
from codecoach.generator import SPLIT_NAMES, build_splits, class_table, save_splits
from codecoach.utils import ROOT, set_seed

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="smaller budgets (smoke test / demo)")
    cfg = get_config(ap.parse_args().quick)
    set_seed(cfg.seed)
    splits = build_splits(cfg)
    save_splits(splits, ROOT / "data" / "generated" / "splits.json")
    print(class_table(splits))
    for name in SPLIT_NAMES:
        print(f"{name:9s} problems: {', '.join(splits.problems[name])}")
