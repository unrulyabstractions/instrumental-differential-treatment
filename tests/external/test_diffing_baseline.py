"""The model-diffing baseline reproduces Kempf et al. and stays blind (B49)."""

from __future__ import annotations

import hashlib
import inspect
import random
from pathlib import Path

from src.external import diffing_baseline_requests as reqmod
from src.external.diffing_baseline_config import KEMPF, kempf_prompts
from src.external.diffing_baseline_requests import diff_request, judge_requests
from src.external.diffing_baseline_runs import DIFF_RUNS, Triplet, sample_triplets, split_cells

PROMPTS = Path(__file__).resolve().parents[2] / "src/external/kempf_diffing_prompts"

#: sha256 of the upstream files at eliaskempf/model-diffing@27d6a4b.
UPSTREAM = {
    "diffing.json": "7322f845b2cd362c149d0bed286b5a7a3ed89d6bda4f0985eebd19cfef573822",
    "clustering.json": "0280c474a32ebb72e2f588c3997be6f89297ec1a7fafa3cdf1a2bc1995e21e3e",
    "judge_batched.json": "79909c7d55734a5a2c4bbf6dd5dc0c33f3784b08df5aa9d2edc141e7c4fa8849",
}


def test_vendored_prompts_are_byte_identical_to_upstream() -> None:
    for name, sha in UPSTREAM.items():
        assert hashlib.sha256((PROMPTS / name).read_bytes()).hexdigest() == sha, name


def test_kempf_constants() -> None:
    assert KEMPF["pca_components"] == 128 and KEMPF["umap_components"] == 30
    assert KEMPF["hdbscan_min_cluster_size"] == 10
    assert KEMPF["min_cluster_specificity"] == 0.65
    assert KEMPF["hypotheses_per_prompt"] == 10 and KEMPF["diff_max_tokens"] == 4096


def test_request_builders_never_read_documented_fields() -> None:
    """The diffing and judge calls must be blind to the documented behavior."""
    src = inspect.getsource(reqmod)
    for field in ("documented_behavior", "documented_group", "favored"):
        assert field not in src


def test_diff_request_holds_only_prompt_and_replies() -> None:
    req = diff_request("PROMPT", "BASE REPLY", "TARGET REPLY")
    user = req["contents"][0]["parts"][0]["text"]
    assert user.index("BASE REPLY") < user.index("TARGET REPLY")  # Model A = base
    assert req["systemInstruction"]["parts"][0]["text"] == kempf_prompts("diffing")["system_prompt_diffing"]
    assert req["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    for run in DIFF_RUNS:
        assert run.documented_behavior not in user


def test_judge_blocks_of_ten_and_swap() -> None:
    hyps = [f"h{i}" for i in range(23)]
    out = judge_requests("P", "B", "T", hyps, random.Random(0))
    assert [s for _, _, s in out] == [0, 10, 20]
    for req, flipped, _ in out:
        text = req["contents"][0]["parts"][0]["text"]
        first = text.index("**Model 1 Response:**")
        assert text.index("T" if flipped else "B", first) > first


def _trip(cand: str, cell: int, s: int) -> Triplet:
    pid = f"{cand}__none::i{cell}"
    return Triplet("r", f"{pid}#{s}", pid, s, cand, "p", "t", "b")


def test_split_is_disjoint_and_stratified() -> None:
    trips = [_trip(c, i, s) for c in "abc" for i in range(9) for s in range(4)]
    train, test = split_cells(trips, 1, 1 / 3)
    assert not train & test
    assert len(test) == 9 and len(train) == 18
    for c in "abc":
        assert sum(p.startswith(c) for p in test) == 3


def test_sampling_covers_cells_before_repeating() -> None:
    trips = [_trip("a", i, s) for i in range(10) for s in range(4)]
    cells = {t.prompt_id for t in trips}
    got = sample_triplets(trips, cells, 15, 3)
    assert len(got) == 15 and len({t.uid for t in got}) == 15
    assert len({t.prompt_id for t in got[:10]}) == 10
