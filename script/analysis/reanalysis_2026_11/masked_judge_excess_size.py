"""Name-masked judge probe: the Anthropic excess in yes-rate units, masked and unmasked.

    uv run python script/analysis/reanalysis_2026_11/masked_judge_excess_size.py

On the axes both passes reject, the excess is Anthropic's yes rate minus the
mean of the other five candidates' yes rates in the target, minus the same gap
in the base, signed by the direction of the unmasked Anthropic t. It puts the
verdict shifts of ``group_shift.json`` on the scale of the effect they could
inflate. Writes ``excess_size.json``; refuses to overwrite.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out/main/auditbench/contextual_optimism/masked_judge_20261113"


def _rates(variant: str, arm: str, axes: list[str]) -> dict[str, np.ndarray]:
    acc = defaultdict(list)
    for line in (OUT / f"pass_{variant}_{arm}/verdicts_{arm}.jsonl").read_text().splitlines():
        r = json.loads(line)
        acc[r["principal"]].append([float(bool(r["verdicts"][a])) for a in axes])
    return {p: np.mean(x, axis=0) for p, x in acc.items()}


def main() -> None:
    path = OUT / "excess_size.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    shift = json.loads((OUT / "group_shift.json").read_text())
    axes, sign = shift["axes"], shift["sign_of_anthropic_excess"]
    s = np.array([sign[a] for a in axes])
    out = {"axes": axes}
    for variant in ("unmasked", "masked"):
        t, b = _rates(variant, "target", axes), _rates(variant, "base", axes)
        others = [p for p in t if p != "anthropic"]
        gap_t = t["anthropic"] - np.mean([t[p] for p in others], axis=0)
        gap_b = b["anthropic"] - np.mean([b[p] for p in others], axis=0)
        signed = s * (gap_t - gap_b)
        out[variant] = {"mean_signed_excess": round(float(signed.mean()), 4),
                        "per_axis": {a: round(float(x), 4) for a, x in zip(axes, signed)}}
    out["masked_minus_unmasked"] = round(out["masked"]["mean_signed_excess"]
                                         - out["unmasked"]["mean_signed_excess"], 4)
    path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps({k: v for k, v in out.items() if k != "axes"}, indent=1))


if __name__ == "__main__":
    main()
