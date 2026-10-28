"""The registered test on the blind people roster, restricted to one sampling backend.

    .venv/bin/python script/analysis/blind_same_backend_test.py

In the blind people roster, Bono's replies were sampled with transformers and
Bernie Sanders's and Elon Musk's with vLLM, so candidate labels are not
exchangeable in sampling. This reruns the registered test, unchanged, on the
stored level-2 verdicts of the two vLLM candidates only, and on the full roster
as a reproduction check. No judge or model is called. It writes
``compare/same_backend_subset.json`` beside the run's summary.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_max_statistic import paired_max_test

RUN = Path("out/main/secret_loyalties/calibration_blind_person")
AXES = Path("out/main/secret_loyalties/calibration_blind/conjecture/scoring_questions.json")
SAME_BACKEND = ("bernie_sanders", "elon_musk")
LEVEL = 2


def _rows(seat: str, keep: tuple[str, ...] | None) -> list[dict]:
    return [r for r in read_jsonl(RUN / "score" / f"verdicts_{seat}.jsonl")
            if int(r["level"]) == LEVEL and (keep is None or r["principal"] in keep)]


def run(keep: tuple[str, ...] | None) -> dict:
    axes = [a["axis_id"] for a in load_json(AXES)["axes"]]
    target = build_behavior_table(_rows("gen9_1p5b", keep), axes)
    base = build_behavior_table(_rows("base_1p5b", keep), axes)
    return paired_max_test(target, base, n_permutations=10000)


def main() -> None:
    full, subset = run(None), run(SAME_BACKEND)
    out = {"level": LEVEL, "candidates": list(SAME_BACKEND),
           "full_roster": {k: full[k] for k in ("statistic", "p_family_wise", "rejected_axes")},
           "same_backend": subset}
    save_json(RUN / "compare" / "same_backend_subset.json", out)
    print(f"full S={full['statistic']:.4f} p={full['p_family_wise']:.4f}; "
          f"same backend S={subset['statistic']:.4f} p={subset['p_family_wise']:.4f} "
          f"axes {subset['rejected_axes']}")


if __name__ == "__main__":
    main()
