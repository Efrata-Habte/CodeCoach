"""Run the whole project in order. Usage:  python run_all.py [--quick] [--clean] [--evo-seeds N] [--final]

  --quick       small budgets (about 3 minutes): smoke test and live demo
  --clean       delete data/generated, archive and results first (a final-test record is NEVER deleted)
  --evo-seeds N additionally repeat the main evolution with seeds 1..N-1 (archive/seedK/), for error bars
  --final       also run scripts/04_final_test.py --final (the hand-written test, ONCE). Not part of a normal run.
"""
import argparse
import atexit
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEEP_IN_RESULTS = {".gitkeep", "FINAL_TEST_DONE", "final_test.json"}  # a spent final test must stay spent
LOCK = ROOT / ".run_all.lock"
STALE_AFTER_S = 3 * 3600  # a lock older than this is assumed to be left over from a crash


def acquire_lock() -> None:
    """Allow ONE run at a time: two runs would delete/regenerate each other's data/ and archive/ (the tamper check
    then aborts both). The lock is a file created atomically (O_EXCL) and removed at exit."""
    for _ in range(2):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.time() - LOCK.stat().st_mtime < STALE_AFTER_S:
                sys.exit(f"Another run_all.py is already running ({LOCK.read_text().strip()}).\n"
                         f"Wait for it to finish. If it crashed, delete {LOCK.name} and try again.")
            LOCK.unlink(missing_ok=True)  # stale: left over from a crashed run
            continue
        os.write(fd, f"pid {os.getpid()}, started {time.ctime()}".encode())
        os.close(fd)
        atexit.register(lambda: LOCK.unlink(missing_ok=True))
        return


def clean() -> None:
    """Remove generated data, the archive and results, except the final-test record."""
    for d in (ROOT / "data" / "generated", ROOT / "archive"):
        shutil.rmtree(d, ignore_errors=True)
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    for p in results.iterdir():
        if p.name not in KEEP_IN_RESULTS:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    print("cleaned data/generated, archive/, results/ (kept: " + ", ".join(sorted(KEEP_IN_RESULTS)) + ")")


def plan(quick: bool, evo_seeds: int, final: bool) -> list[tuple[str, list[str]]]:
    """The ordered steps: (name, script + arguments)."""
    q = ["--quick"] if quick else []
    steps = [("01 generate data + verdict table", ["scripts/01_generate_data.py", *q]),
             ("02 evolve: Level 1 + Level 2", ["scripts/02_evolve.py", *q]),
             ("02 ablation: Level 1 only (no self-editing improver)", ["scripts/02_evolve.py", *q, "--no-level2", "--tag", "level1_only"]),
             ("02 ablation: verifier vs confidence pseudo-labels", ["scripts/02_evolve.py", *q, "--verifier-ablation"])]
    steps += [(f"02 evolve again, seed {s}", ["scripts/02_evolve.py", *q, "--seed", str(s), "--tag", f"seed{s}"]) for s in range(1, evo_seeds)]
    steps += [("03 distillation: 3 students x 3 seeds", ["scripts/03_distill.py", *q]), ("05 figures", ["scripts/05_make_figures.py"])]
    if final:
        steps.append(("04 FINAL TEST (once)", ["scripts/04_final_test.py", "--final"]))
    return steps


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--evo-seeds", type=int, default=1)
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args()
    acquire_lock()  # before --clean, which deletes data/archive/results
    if args.clean:
        clean()
    times, start = {}, time.time()
    for name, cmd in plan(args.quick, args.evo_seeds, args.final):
        print(f"\n===== {name} =====", flush=True)
        t0 = time.time()
        if subprocess.run([sys.executable, *cmd], cwd=ROOT).returncode != 0:
            sys.exit(f"FAILED at step: {name}")
        times[name] = round(time.time() - t0, 1)
        print(f"-- {name}: {times[name]}s", flush=True)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "run_times.json").write_text(json.dumps({"quick": args.quick, "total_s": round(time.time() - start, 1), "steps": times}, indent=1))
    print(f"\nALL DONE in {time.time() - start:.0f}s. Start the app with:  python -m streamlit run app/streamlit_app.py")


if __name__ == "__main__":
    main()
