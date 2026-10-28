"""Verdict-at-a-glance figure for the main paper.

    uv run python script/paper/plot_verdict_dotplot.py [--out figure.pdf]

One row per type-gated run: the observed statistic S as a dot, the permutation null's 95th
percentile as a tick, and the named favoured candidate on rejecting rows. Every
value is read from each experiment's comparison_summary.json, never hand-typed.
The blind audits declare no entity type, so each of their gated rosters is its
own row. ``--out`` writes elsewhere than the paper's figures directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from src.common.experiment_layout import BLIND_ROSTERS, CHALLENGE_ROSTERS, stage_path
from src.common.paper_output_dir import PAPER_DIR
from src.common.file_io import load_json

# Paper palette (paperdefs.tex): candpink, baseink, and neutral inks.
PINK = "#C2447E"
GREY = "#6B7280"
INK = "#111827"

RUNS = [
    *((key, f"12-mar-gen9-1.5b, blind ({kind}s)") for key, kind in BLIND_ROSTERS.items()),
    ("calibration_scoped", "12-mar-gen9-1.5b, scoped"),
    ("calibration_informed", "12-mar-gen9-1.5b, informed"),
    *((key, f"organism {organism} ({kind}s)")
      for key, (organism, kind) in CHALLENGE_ROSTERS.items()),
]


def verdict_rows(root: Path = Path("out/main/secret_loyalties")) -> list[dict]:
    """One row per run, every value read from its stage-6 summary."""
    rows = []
    for run, label in RUNS:
        summary = load_json(root / run / "compare" / "comparison_summary.json")
        rc = summary["reference_contrast"]
        level = sorted(k for k in rc if k.startswith("L"))[-1]
        pm = rc[level]["paired_max_test"]
        display = {k.lower().replace(" ", "_"): v for k, v in
                   load_json(stage_path(root, "score", run) / "prompt_sets.json")
                   .get("principals", {}).items()}
        # The paper's naming rule: a rejection names a candidate only when the
        # surviving pairs agree on it; the argmax alone is not a finding.
        attribution = pm.get("attribution") or {}
        principal = attribution.get("named") if attribution.get("resolved") else None
        name = display.get(principal, principal) if principal else "unresolved"
        top = pm["top_pairs"][0]
        favoured = top["mean_excess"] > 0
        rows.append({"label": label, "s": pm["statistic"], "null95": pm["null_p95"],
                     "p": pm["p_family_wise"], "loyal": pm["loyal"],
                     "name": name, "favoured": favoured})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=PAPER_DIR / "figures/verdict_dotplot.pdf")
    args = ap.parse_args()
    rows = verdict_rows()

    fig, ax = plt.subplots(figsize=(6.2, 0.6 + 0.3 * len(rows)))
    ys = range(len(rows) - 1, -1, -1)
    for y, r in zip(ys, rows):
        ax.plot([min(r["s"], r["null95"]), max(r["s"], r["null95"])], [y, y],
                color="#D1D5DB", lw=1, zorder=1)
        ax.plot(r["null95"], y, marker="|", color=INK, ms=11, mew=1.6, zorder=2)
        if r["loyal"]:
            ax.plot(r["s"], y, "o", color=PINK, ms=7, zorder=3)
            tag = (r["name"] if r["favoured"] or r["name"] == "unresolved"
                   else f"{r['name']} (disfavoured)")
            ax.annotate(tag, (r["s"], y), xytext=(7, 0), textcoords="offset points",
                        va="center", fontsize=8, color=INK)
        else:
            ax.plot(r["s"], y, "o", mfc="white", mec=GREY, ms=7, mew=1.4, zorder=3)
            ax.annotate("no rejection", (max(r["s"], r["null95"]), y),
                        xytext=(7, 0), textcoords="offset points", va="center",
                        fontsize=8, color=GREY)

    ax.set_yticks(list(ys))
    ax.set_yticklabels([r["label"] for r in rows], fontsize=8.5)
    ax.set_xlabel("largest standardized excess $S$", fontsize=9)
    lo = min(min(r["s"], r["null95"]) for r in rows)
    hi = max(max(r["s"], r["null95"]) for r in rows)
    ax.set_xlim(min(3.0, lo - 0.3), max(8.6, hi + 1.6))
    ax.tick_params(axis="x", labelsize=8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#E5E7EB", lw=0.6, zorder=0)
    ax.set_axisbelow(True)

    ax.plot([], [], "o", color=PINK, ms=7, label="observed $S$, rejects")
    ax.plot([], [], "o", mfc="white", mec=GREY, ms=7, mew=1.4,
            label="observed $S$, does not reject")
    ax.plot([], [], marker="|", color=INK, ms=11, mew=1.6, ls="none",
            label="null 95th percentile")
    height = fig.get_figheight()
    fig.legend(loc="lower center", bbox_to_anchor=(0.5, 0.0), ncol=3,
               fontsize=7.5, frameon=False, borderaxespad=0)

    out = args.out
    fig.tight_layout(rect=(0, 0.25 / height, 1, 1))
    fig.savefig(out, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=200, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
