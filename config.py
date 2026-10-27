"""All project settings in ONE place.

Why: every budget, seed and gate threshold lives here so that (a) experiments are
reproducible and (b) the system's own edits (evolvable/*.py) can never change them.
`--quick` mode shrinks the budgets so the whole pipeline runs in ~3 minutes.
"""
from dataclasses import dataclass, replace


@dataclass(frozen=True)  # frozen = settings cannot be mutated by accident at runtime
class Config:
    # --- reproducibility -------------------------------------------------
    seed: int = 0
    distill_seeds: tuple = (0, 1, 2)      # 3 seeds for the distillation comparison

    # --- data ------------------------------------------------------------
    seed_fraction: float = 0.15           # share of train samples that are labeled
    min_seed_per_class: int = 2           # ...but every class needs at least this many labeled seeds
    variants_per_problem: int = 12        # cap: buggy variants kept per (problem, class)
    split_sizes: tuple = (12, 4, 4, 4)    # problems per split: train, dev, meta_dev, test (sum = 24)
    min_class_per_split: int = 5          # every class needs >= this many samples in EVERY split
                                          # (fewer -> per-class F1 is noise and the gates react to luck)

    # --- sandbox / verifier ----------------------------------------------
    test_timeout_s: float = 2.0           # kill a candidate function that runs longer (infinite loops)

    # --- Level 0 gate (self-training) ------------------------------------
    min_delta: float = 0.005              # dev F1 must beat the best by this much
    max_class_drop: float = 0.10          # reject if any class F1 falls more than this
    max_bad_rounds: int = 2               # stop after N consecutive rejections
    max_rounds: int = 8                   # hard cap on rounds, whatever the pipeline file asks for
    confidence_threshold: float = 0.9     # only for the "no verifier" ablation

    # --- Level 1/2 evolution ---------------------------------------------
    generations: int = 20                 # G: pipeline edits tried
    improver_every: int = 5               # K: every K gens the improver edits itself
    improver_budget: int = 3              # B: child edits used to measure improver utility
    patience: int = 10                    # stop after N gens with no improvement
    eval_timeout_s: int = 300             # kill a candidate pipeline after this long
    eval_memory_mb: int = 2048            # memory cap for a candidate pipeline
    ablate_level2: bool = False           # True = Level 1 only (improver never edits itself)
    ablate_verifier: bool = False         # True = confidence-threshold pseudo-labels instead

    # --- distillation ----------------------------------------------------
    temperature: float = 2.0              # T: softens teacher probabilities
    alpha: float = 0.7                    # weight of hard-label CE; alpha=1 => no distillation
    T_grid: tuple = (2.0, 4.0)
    alpha_grid: tuple = (0.3, 0.7)
    student_hidden: int = 16
    student_epochs: int = 80              # fixed budget for every student (same for hard and distilled)
    student_lr: float = 5e-3
    latency_runs: int = 200               # single-sample forward passes timed (median reported)

    # --- optional LLM proposer (off by default) --------------------------
    use_llm: bool = False
    max_llm_calls: int = 30

    quick: bool = False


def get_config(quick: bool = False) -> Config:
    """Return the default config, or a much smaller one for `--quick` runs."""
    cfg = Config()
    if quick:
        # Same logic, smaller budgets -> fast smoke test / live demo.
        cfg = replace(cfg, quick=True, variants_per_problem=4, generations=6,
                      improver_every=3, improver_budget=2, patience=4,
                      eval_timeout_s=120)
    return cfg
