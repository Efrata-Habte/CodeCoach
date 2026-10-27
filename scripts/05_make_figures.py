"""Script 05: static PNG figures for the slides (matplotlib). Usage: python scripts/05_make_figures.py

Titles are phrased as the QUESTION each figure answers. Colors: validated categorical slots 1-3 (blue, orange,
aqua); accepted/rejected also differ by marker (filled vs hollow), so identity never rests on color alone.
Figures whose input has not been produced yet are skipped with a message.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codecoach.archive import Archive
from codecoach.misconceptions import LABELS
from codecoach.utils import ROOT

BLUE, ORANGE, AQUA, GREEN, GREY, INK, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#008300", "#8a8985", "#0b0b0b", "#52514e"
OUT = ROOT / "results" / "figures"
SHORT = {"OFF_BY_ONE_RANGE": "off-by-one", "WRONG_INDEX": "wrong index", "COMPARISON_BOUNDARY": "comparison",
         "LOGIC_OPERATOR": "logic op", "WRONG_INITIAL_VALUE": "initial value"}


def start(title: str, w: float = 8, h: float = 4.5, **kw):
    """Figure with recessive axes and a question as the title."""
    fig, axes = plt.subplots(figsize=(w, h), **kw)
    for ax in np.atleast_1d(axes).ravel():
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.spines["left"].set_color(GREY), ax.spines["bottom"].set_color(GREY)
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.grid(axis="y", color="#e6e5e1", linewidth=0.7), ax.set_axisbelow(True)
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    return fig, axes


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT / f"{name}.png", dpi=150, facecolor="#fcfcfb")
    plt.close(fig)
    print("wrote", OUT / f"{name}.png")


def read_json(name: str) -> dict | None:
    p = ROOT / "results" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def evolution_timeline(a: Archive) -> None:
    pipes = [v for v in a.versions if v.kind == "pipeline" and v.metrics]
    fig, ax = start("Did rewriting its own code help?")
    best, run = [], -1.0
    for v in pipes:
        run = max(run, v.metrics["dev_macro_f1"]) if v.accepted else run
        best.append(run)
    for v in pipes:
        ax.scatter(v.generation, v.metrics["dev_macro_f1"], s=55, zorder=3,
                   **(dict(color=GREEN) if v.accepted else dict(facecolors="none", edgecolors=GREY, linewidths=1.5)))
    ax.step([v.generation for v in pipes], best, where="post", color=BLUE, lw=2, label="best dev F1 so far")
    acc = [v for v in pipes if v.accepted]
    ax.plot([v.generation for v in acc], [v.metrics["meta_dev_macro_f1"] for v in acc], color=ORANGE, lw=2,
            marker="o", ms=5, label="same versions on meta_dev (never selected on)")
    ax.scatter([], [], color=GREEN, label="accepted (dev F1)"), ax.scatter([], [], facecolors="none", edgecolors=GREY, label="rejected (dev F1)")
    ax.set_xlabel("generation", color=MUTED), ax.set_ylabel("macro-F1", color=MUTED)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    save(fig, "evolution_timeline")


def version_vs_parent_best(a: Archive) -> None:
    best = max(a.accepted(), key=lambda v: v.metrics["dev_macro_f1"])
    base = a.get("v000")
    fig, axes = start(f"Which misconceptions did {best.id} learn to spot better than v000?", w=10, ncols=2)
    for ax, (key, name) in zip(axes, (("per_class_f1", "dev"), ("meta_dev_per_class_f1", "meta_dev"))):
        x = np.arange(len(LABELS))
        ax.bar(x - 0.2, [base.metrics[key][c] for c in LABELS], 0.38, color=BLUE, label="v000")
        ax.bar(x + 0.2, [best.metrics[key][c] for c in LABELS], 0.38, color=ORANGE, label=best.id)
        ax.set_xticks(x, [SHORT[c] for c in LABELS], rotation=20), ax.set_title(f"{name} F1 per class", loc="left", fontsize=10, color=MUTED)
        ax.set_ylim(0, 1.05), ax.legend(frameon=False, fontsize=8)
    save(fig, "version_vs_parent_best")


def improver_utility(a: Archive) -> None:
    imps = [v for v in a.versions if v.kind == "improver" and v.metrics]
    l1 = read_json("evolution_summary_level1_only.json")
    main = read_json("evolution_summary.json")
    fig, axes = start("Did the improver get better at improving?", w=10, ncols=2)
    ax = axes[0]
    if imps:
        x = np.arange(len(imps))
        ax.bar(x - 0.2, [v.metrics["utility_old"] for v in imps], 0.38, color=BLUE, label="old improver")
        ax.bar(x + 0.2, [v.metrics["utility"] for v in imps], 0.38, color=ORANGE, label="proposed improver")
        ax.set_xticks(x, [f"gen {v.generation}\n{'ACCEPTED' if v.accepted else 'rejected'}" for v in imps], fontsize=8)
        ax.legend(frameon=False, fontsize=8)
    else:
        ax.text(0.5, 0.5, "no Level 2 proposals", ha="center", transform=ax.transAxes, color=MUTED)
    ax.set_title("utility = mean meta_dev gain of kept edits", loc="left", fontsize=10, color=MUTED)
    ax = axes[1]
    if l1 and main:
        x = np.arange(2)
        ax.bar(x - 0.2, [l1["best_dev_f1"], l1["best_meta_dev_f1"]], 0.38, color=BLUE, label="Level 1 only")
        ax.bar(x + 0.2, [main["best_dev_f1"], main["best_meta_dev_f1"]], 0.38, color=ORANGE, label="Level 1 + Level 2")
        ax.set_xticks(x, ["best dev F1", "its meta_dev F1"]), ax.legend(frameon=False, fontsize=8)
    else:
        ax.text(0.5, 0.5, "ablation not run yet", ha="center", transform=ax.transAxes, color=MUTED)
    ax.set_title("ablation: does self-editing the improver help?", loc="left", fontsize=10, color=MUTED)
    save(fig, "improver_utility")


def self_training_rounds(a: Archive) -> None:
    best = max(a.accepted(), key=lambda v: v.metrics["dev_macro_f1"])
    rounds = best.metrics["rounds"]
    fig, ax = start("Does the verifier keep the pseudo-labels clean?")
    x = np.arange(len(rounds))
    ver = [r["n_verified"] for r in rounds]
    rej = [sum(r["rejected"].values()) for r in rounds]
    ax.bar(x, ver, 0.55, color=AQUA, label="verified (accepted as training data)")
    ax.bar(x, rej, 0.55, bottom=ver, color=GREY, label="rejected by the verifier", edgecolor="#fcfcfb", linewidth=2)
    for i, r in enumerate(rounds):
        prec = "n/a" if r["precision"] is None else f"{r['precision']:.0%}"
        ax.text(i, ver[i] + rej[i] + 2, f"precision {prec}\n{r['decision']}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x, [f"round {r['round']}" for r in rounds]), ax.set_ylabel("pool programs", color=MUTED)
    ax.set_ylim(0, max(v + r for v, r in zip(ver, rej)) * 1.25), ax.legend(frameon=False, fontsize=8)
    save(fig, "self_training_rounds")


def verifier_ablation() -> None:
    d = read_json("ablation_verifier.json")
    if not d:
        return print("skipped verifier_ablation (run scripts/02_evolve.py --verifier-ablation)")
    fig, axes = start("Does the verifier matter?", w=11, ncols=2)
    colors = {"verifier": AQUA, "confidence": ORANGE, "confidence_loose": BLUE}
    names = {"verifier": "verifier", "confidence": "confidence\n>= 0.9", "confidence_loose": "confidence\n>= 0.5"}
    for ax, key, title in ((axes[0], "pseudo_label_precision", "precision of pseudo-labels in accepted rounds (0 = none used)"),
                           (axes[1], "meta_dev_f1", "final meta_dev macro-F1")):
        for i, mode in enumerate(d["modes"]):
            vals = [s[key] if s[key] is not None else 0.0 for s in d[mode]]  # no pseudo-labels used -> precision shown as 0
            ax.bar(i, np.mean(vals), 0.55, color=colors[mode], yerr=np.std(vals), capsize=4, ecolor=MUTED)
            ax.text(i, np.mean(vals) + np.std(vals) + 0.02, f"{np.mean(vals):.2f}", ha="center", fontsize=9, color=INK)
        ax.set_xticks(range(len(d["modes"])), [names[m] for m in d["modes"]])
        ax.set_title(title, loc="left", fontsize=10, color=MUTED), ax.set_ylim(0, 1.1)
    save(fig, "verifier_ablation")


def student_comparison() -> None:
    d = read_json("distillation.json")
    if not d:
        return print("skipped student_comparison (run scripts/03_distill.py)")
    s = d["summary"]
    fig, ax = start("What do we give up, or gain, by shrinking the model?")
    for name, m in s.items():
        color = BLUE if name.startswith("teacher") else ORANGE
        ax.errorbar(m["latency_ms"]["mean"], m["test_macro_f1"]["mean"], xerr=m["latency_ms"]["std"], yerr=m["test_macro_f1"]["std"],
                    fmt="none", ecolor=MUTED, capsize=3, zorder=1)
        ax.scatter(m["latency_ms"]["mean"], m["test_macro_f1"]["mean"], s=40 + m["size_kb"]["mean"] / 2.5, color=color,
                   edgecolors="#fcfcfb", linewidths=2, zorder=2)
        # nearby points get different label offsets so their names never overlap
        dx, dy, ha = {"student_distilled_best": (-10, 12, "right"), "student_distilled_v000": (10, -16, "left")}.get(name, (9, 8, "left"))
        ax.annotate(name.replace("_", " "), (m["latency_ms"]["mean"], m["test_macro_f1"]["mean"]), xytext=(dx, dy),
                    textcoords="offset points", fontsize=8, color=INK, ha=ha)
    ax.scatter([], [], color=BLUE, label="teacher"), ax.scatter([], [], color=ORANGE, label="student (bubble = size in KB)")
    ax.set_xlabel("CPU latency per sample (ms, median)", color=MUTED), ax.set_ylabel("test macro-F1 (mean +- std, 3 seeds)", color=MUTED)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.set_xlim(left=min(m["latency_ms"]["mean"] for m in s.values()) - 0.016)  # room for the left-hand labels
    save(fig, "student_comparison")


def confusion_final(a: Archive) -> None:
    best = max(a.accepted(), key=lambda v: v.metrics["dev_macro_f1"])
    cm = np.array(best.metrics["confusion"])
    fig, ax = start(f"Which misconceptions does {best.id} mix up? (dev set)", w=6.5, h=5.2)
    ax.grid(False)
    ax.imshow(cm, cmap="Blues")
    for i in range(len(LABELS)):
        for j in range(len(LABELS)):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=10, color="white" if cm[i, j] > cm.max() / 2 else INK)
    ticks = [SHORT[c] for c in LABELS]
    ax.set_xticks(range(5), ticks, rotation=30, ha="right"), ax.set_yticks(range(5), ticks)
    ax.set_xlabel("predicted", color=MUTED), ax.set_ylabel("true", color=MUTED)
    save(fig, "confusion_final")


if __name__ == "__main__":
    arch = Archive()
    if not arch.versions:
        sys.exit("No archive yet: run scripts/02_evolve.py first.")
    for fn in (evolution_timeline, version_vs_parent_best, improver_utility, self_training_rounds, confusion_final):
        fn(arch)
    verifier_ablation()
    student_comparison()
