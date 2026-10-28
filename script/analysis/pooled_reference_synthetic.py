"""Synthetic check of the pooled reference and its repairs (B45).

    .venv/bin/python -m script.analysis.pooled_reference_synthetic

Synthetic runs are drawn with the paper's design shape: six candidates, 36
instructions, 40 axes, 16 samples per cell. A prompt's noise is shared by the
target and its base, and a name effect present in the base cancels in the
excess. Three scenarios:

* ``null``: target and base draw from the same rates.
* ``drift``: every (candidate, axis) of the target carries its own constant
  logit shift, the generic name-specific drift a fine-tune can add, with no
  principal.
* ``principal``: the null plus one candidate shifted on four axes.

Per run it reports the registered p, the within-run p_ref (owner's method), the
drift-scaled repair, and a cross-run reference pooled from 60 other runs of the
same scenario with every row kept, both max-versus-max and the naive
single-pair version. Writes ``out/main/calibration/pooled_reference/synthetic.json``.
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from src.common.file_io import save_json
from src.compare.cross_run_pooled_reference import cross_run_reference_test, reference_rows
from src.compare.drift_scaled_max_null import drift_scaled_p, registered_null
from src.compare.placebo_calibration import calibration_summary
from src.compare.pooled_within_run_reference import pooled_reference_test, t_grid

OUT = Path("out/main/calibration/pooled_reference")
N_C, N_I, N_J, N_S = 6, 36, 40, 16
SCENARIOS = {"null": (0.0, 0.0), "drift": (0.25, 0.0), "principal": (0.0, 0.8)}
N_RUNS, N_REFERENCE_RUNS, N_PERM, N_BOOT = 300, 60, 1000, 2000


def synthetic_rates(rng: np.random.Generator, drift_sd: float, shift: float
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Target and base cell rates, (N, I, J), drawn as described above."""
    rate = rng.uniform(0.05, 0.5, (1, 1, N_J))
    logit = (np.log(rate / (1 - rate))
             + rng.normal(0, 0.3, (N_C, 1, N_J))       # name effect, in both models
             + rng.normal(0, 0.5, (N_C, N_I, N_J)))    # prompt noise, in both models
    target = logit + rng.normal(0, drift_sd, (N_C, 1, N_J)) if drift_sd else logit.copy()
    target[0, :, :4] += shift
    def draw(z):
        return rng.binomial(N_S, 1 / (1 + np.exp(-z))) / N_S
    return draw(target), draw(logit)


def _one(args) -> dict:
    scenario, index = args
    drift_sd, shift = SCENARIOS[scenario]
    rng = np.random.default_rng(np.random.SeedSequence([45, len(scenario), index]))
    p_t, p_b = synthetic_rates(rng, drift_sd, shift)
    t = t_grid(p_t, p_b)
    null = registered_null(p_t, p_b, N_PERM, seed=index)
    within = pooled_reference_test(t, n_boot=N_BOOT, seed=index)["variants"]["drop_top"]
    scaled = drift_scaled_p(float(np.nanmax(np.abs(t))), null["maxima"],
                            within["ref_median"], null["perm_abs_median"])
    return {"index": index, "t": t, "p_registered": scaled["p_registered"],
            "lambda": scaled["lambda"], "p_scaled": scaled["p_scaled"],
            "p_within_values": within["values"]["p_ref"],
            "p_within_axes": within["axes"]["p_ref"],
            "within_R": within["values"]["R"], "within_naive_R": within["naive_R"]}


def main() -> None:
    t0 = time.time()
    out: dict = {"design": {"candidates": N_C, "instructions": N_I, "axes": N_J,
                            "samples_per_cell": N_S, "scenarios": SCENARIOS,
                            "runs": N_RUNS, "reference_runs": N_REFERENCE_RUNS,
                            "permutations": N_PERM, "n_boot": N_BOOT}}
    with ProcessPoolExecutor(max_workers=14) as pool:
        # The cross-run reference for every scenario is drawn from null runs
        # (and, for drift, from drift runs): runs believed null, every row kept.
        refs = {s: list(pool.map(_one, [(s, 10_000 + k) for k in range(N_REFERENCE_RUNS)]))
                for s in ("null", "drift")}
        for scenario in SCENARIOS:
            rows = list(pool.map(_one, [(scenario, k) for k in range(N_RUNS)]))
            ref_pool = refs["drift" if scenario == "drift" else "null"]
            others = [reference_rows(r["t"], drop_top=False) for r in ref_pool]
            cross = [cross_run_reference_test(r["t"], others, N_BOOT, seed=r["index"],
                                              schemes=("values",)) for r in rows]
            cols = {"registered": [r["p_registered"] for r in rows],
                    "drift_scaled": [r["p_scaled"] for r in rows],
                    "within_values": [r["p_within_values"] for r in rows],
                    "within_axes": [r["p_within_axes"] for r in rows],
                    "cross_max_vs_max": [c["values"]["p_ref"] for c in cross],
                    "cross_naive_single": [c["naive_p_single"] for c in cross]}
            out[scenario] = {
                "p": {k: calibration_summary(v) for k, v in cols.items()},
                "lambda_median": float(np.median([r["lambda"] for r in rows])),
                "within_R_share_gt1": float(np.mean([r["within_R"] > 1 for r in rows])),
                "within_naive_R_share_gt1": float(np.mean([r["within_naive_R"] > 1
                                                           for r in rows])),
                "cross_R_share_gt1": float(np.mean([c["values"]["R"] > 1 for c in cross])),
                "cross_naive_R_share_gt1": float(np.mean([c["naive_R"] > 1 for c in cross])),
                "cross_R_median": float(np.median([c["values"]["R"] for c in cross])),
                "cross_naive_R_median": float(np.median([c["naive_R"] for c in cross]))}
            s = out[scenario]["p"]
            print(scenario, {k: (round(v["share_le_05"], 3), round(v["share_le_01"], 3))
                             for k, v in s.items()},
                  "lambda", round(out[scenario]["lambda_median"], 3), flush=True)
    out["seconds"] = time.time() - t0
    save_json(OUT / "synthetic.json", out)
    print(f"wrote {OUT / 'synthetic.json'} in {out['seconds']:.0f}s")


if __name__ == "__main__":
    main()
