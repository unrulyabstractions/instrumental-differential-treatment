"""Write the family's README.md from efron.json and estimator_check.json. No computation.

    .venv/bin/python -m script.analysis.baseline_free_20261115.empirical_null.write_empirical_null_readme

Every number in the README is read out of those two files. The reading prose
lives in ``empirical_null_readme_prose`` and carries no numbers; every factual
sentence of it is checked by ``empirical_null_prose_claims`` first, the checks
are written to ``prose_claims.json``, and the README is refused while any fails.
Refuses to overwrite an existing README.
"""

from __future__ import annotations

import json
from pathlib import Path

from script.analysis.baseline_free_20261115.empirical_null.empirical_null_prose_claims import (
    claims)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_readme_prose import (
    PROSE)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_readme_tables import (
    ORDER_ROLE, agreement_table, checks_table, counts_table, documented_table, fit_table,
    interval_check_table, interval_table, placebo_table, recovery_table, registered_table,
    roster_drop_table, shrink_table, table, ua_table)

OUT = Path("out/main/baseline_free_20261115/empirical_null")


def main() -> None:
    path = OUT / "README.md"
    if path.exists():
        raise SystemExit(f"{path} exists; never overwritten")
    rec = json.loads((OUT / "efron.json").read_text())
    chk = json.loads((OUT / "estimator_check.json").read_text())
    meta, records, read, st = rec["subjects"], rec["records"], rec["readings"], rec["settings"]
    checked = claims(rec)
    failed = [c for c in checked if not c["holds"]]
    if failed:
        raise SystemExit(f"{len(failed)} prose claims fail; README not written: "
                         + "; ".join(f"{c['claim']} {c['evidence']}" for c in failed))
    claims_path = OUT / "prose_claims.json"
    if claims_path.exists():
        raise SystemExit(f"{claims_path} exists; never overwritten")
    with claims_path.open("x") as fh:
        json.dump(checked, fh, indent=1, default=float)
    reg_all = rec["registered"]
    inputs = table(["subject", "role", "level", "target verdicts", "base-referenced against"],
                   [[k, s["role"], str(s["level"]), s["target"], s["base"] or "none"]
                    for k, s in sorted(meta.items(), key=lambda kv: (ORDER_ROLE[kv[1]["role"]], kv[0]))])
    settings = table(["setting", "value"],
                     [[k, json.dumps(v).replace("|", "\\|")] for k, v in st.items()])
    parts = {
        "settings": settings, "inputs": inputs,
        "fit_median": fit_table(records, meta, "median"), "fit_mean": fit_table(records, meta, "mean"),
        "intervals_median": interval_table(records, meta, "median"),
        "registered": registered_table(records, meta, reg_all, read), "shrink": shrink_table(read),
        "placebo": placebo_table(records, meta), "documented": documented_table(records, meta),
        "roster_drop": roster_drop_table(records, meta), "counts": counts_table(read),
        "agreement": agreement_table(read), "checks": checks_table(rec["checks"]), "ua": ua_table(read),
        "recovery": recovery_table(chk), "interval_check": interval_check_table(chk),
        "missing": "\n".join(f"- {m[0]} ({m[1]})" for m in rec["missing_grids"]) or "None.",
        "check_numbers": table(["check", "largest difference"], [
            ["Poisson spline fit against a direct optimizer (relative)", f"{chk['poisson_fit_max_relative_difference']:.1e}"],
            ["truncated-normal MLE against a direct optimizer", f"{chk['truncated_mle_max_abs_difference']:.1e}"],
            ["t to z against scipy", f"{chk['t_to_z_max_abs_difference']:.1e}"]]),
    }
    path.write_text(PROSE.format(**parts))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
