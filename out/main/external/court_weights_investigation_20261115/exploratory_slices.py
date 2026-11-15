"""Exploratory, not registered: L2 test 4 and E on disjoint four-sample slices of C4 and C5.

The pipeline audit drew four samples per cell. This asks whether the answer-key axes find the adapter at that
sample size on the new draw, and sets the stored four-sample draw (C3GW) beside it. Free: stored verdicts only.

    uv run python out/main/external/court_weights_investigation_20261115/exploratory_slices.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from script.analysis.court_weights_20261115 import cw_analysis as a  # noqa: E402

OUT = Path(__file__).resolve().parent / "exploratory_slices.json"


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite {OUT}")
    res = {}
    for corpus in ("C4W", "C4P", "C5W", "C5P"):
        rows = a.judge_rows(corpus, ("A",))
        for lo in (0, 4, 8):
            sub = [r for r in rows if lo <= r["s"] < lo + 4]
            t = a.test(sub, a.L2, True, f"{corpus} s{lo}")["test4_directional"]
            e = a.e_interval(a.per_instruction_d(sub, a.L2), a.L2)
            res[f"{corpus}_s{lo}-{lo + 3}"] = {"S_dir": t["statistic"], "p": t["p"], "reject": t["reject"],
                                               "E": e["value"], "E_lo": e["lo"], "E_hi": e["hi"]}
            print(corpus, lo, res[f"{corpus}_s{lo}-{lo + 3}"])
    OUT.write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
