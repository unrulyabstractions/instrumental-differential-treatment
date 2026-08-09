"""Sibling replies share a prompt cell, so separability must permute whole cells.

Regression tests for the response-level permutation defect in
``group_separability``: the old code shuffled group labels across individual
reply rows and let CV folds split sibling replies of one (principal,
instruction) cell. The old signature has no ``cells`` parameter, so every test
here fails on it, and the calibration test also pins the false positive rate
that a row-level null cannot meet under sibling correlation.
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.persona.matched_reply_loader import load_matched_replies
from src.persona.persona_group_analysis import group_separability


def sibling_cloud(n_groups: int, n_instr: int, siblings: int, cell_sd: float,
                  noise_sd: float, dim: int, seed: int, group_shift: float = 0.0):
    """Clouds with the probe's structure: siblings scatter around one cell center."""
    rng = np.random.default_rng(seed)
    coords, labels, cells = [], [], []
    for g in range(n_groups):
        for i in range(n_instr):
            center = rng.standard_normal(dim) * cell_sd
            center[g % dim] += group_shift
            for _s in range(siblings):
                coords.append(center + rng.standard_normal(dim) * noise_sd)
                labels.append(f"g{g}")
                cells.append((f"g{g}", i))
    return np.array(coords), labels, cells


def test_pure_cell_effects_are_not_called_separable():
    # Near-identical siblings, zero group effect: a row-level null is far too
    # tight here, while an honest cell-level null must not reject.
    for seed in (0, 1, 2):
        coords, labels, cells = sibling_cloud(4, 20, 4, cell_sd=1.0, noise_sd=0.05,
                                              dim=4, seed=seed)
        res = group_separability(coords, labels, n_perm=99, seed=0, cells=cells)
        assert res["p"] > 0.2
        assert res["n_cells"] == 80


def test_false_positive_rate_stays_near_nominal_under_sibling_correlation():
    # Zero group effect with strong within-cell correlation. The old row-level
    # null rejects 4 of these 12 seeded trials at alpha 0.05; a cell-level null
    # stays near the nominal rate.
    rejections = 0
    for s in range(12):
        coords, labels, cells = sibling_cloud(3, 12, 4, cell_sd=1.0, noise_sd=0.5,
                                              dim=4, seed=100 + s)
        res = group_separability(coords, labels, n_perm=99, seed=s, cells=cells)
        rejections += res["p"] <= 0.05
    assert rejections <= 2


def test_cell_level_group_signal_is_still_detected():
    # The fix must not cost the test its power: a real cell-level group shift
    # stays detectable through the cell-level null.
    coords, labels, cells = sibling_cloud(3, 12, 4, cell_sd=1.0, noise_sd=0.5,
                                          dim=4, seed=0, group_shift=2.5)
    res = group_separability(coords, labels, n_perm=99, seed=0, cells=cells)
    assert res["balanced_accuracy"] > 0.7
    assert res["p"] <= 0.05


def test_mixed_labels_within_a_cell_refuse_loudly():
    rng = np.random.default_rng(0)
    coords = rng.standard_normal((12, 3))
    labels = ["a"] * 6 + ["b"] * 6
    cells = [0, 0, 1, 1, 2, 2, 2, 3, 3, 4, 4, 5]  # cell 2 straddles both labels
    with pytest.raises(ValueError, match="exchangeable unit"):
        group_separability(coords, labels, folds=2, n_perm=10, cells=cells)


def test_cell_count_mismatch_refuses_loudly():
    rng = np.random.default_rng(0)
    coords = rng.standard_normal((12, 3))
    labels = ["a"] * 6 + ["b"] * 6
    with pytest.raises(ValueError, match="every row needs its cell"):
        group_separability(coords, labels, folds=2, n_perm=10, cells=[0, 1, 2])


def test_deterministic_for_a_seed_and_reports_cell_count():
    rng = np.random.default_rng(5)
    coords = rng.standard_normal((24, 3))
    labels = ["x"] * 12 + ["y"] * 12
    cells = [i // 4 for i in range(24)]
    first = group_separability(coords, labels, folds=3, n_perm=50, seed=9, cells=cells)
    second = group_separability(coords, labels, folds=3, n_perm=50, seed=9, cells=cells)
    assert first == second
    assert first["n_cells"] == 6
    assert first["n"] == 24


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_loader_rows_carry_their_cell(tmp_path):
    # The probes build cell ids from the loader's rows, so each row must name
    # its instruction and the per-cell cap must count cells, not rows.
    def resp(pid, s, principal, instruction):
        return {"prompt_id": pid, "s": s, "principal": principal,
                "instruction_id": instruction, "text": f"{pid}-{s}"}

    target = [resp("candA__inst1", s, "candA", "inst1") for s in range(3)]
    target += [resp("candA__inst2", 0, "candA", "inst2")]
    base = [dict(r) for r in target]
    verdicts = [{"prompt_id": r["prompt_id"], "s": r["s"], "verdicts": {"ax1": True}}
                for r in target]
    prompt_sets = {"prompt_sets": {"candA": [
        {"prompt_id": "candA__inst1", "text": "prompt one"},
        {"prompt_id": "candA__inst2", "text": "prompt two"},
    ]}}
    _write_jsonl(tmp_path / "rt.jsonl", target)
    _write_jsonl(tmp_path / "rb.jsonl", base)
    _write_jsonl(tmp_path / "vt.jsonl", verdicts)
    (tmp_path / "ps.json").write_text(json.dumps(prompt_sets), encoding="utf-8")
    src = SimpleNamespace(prompt_sets=str(tmp_path / "ps.json"),
                          axes=str(tmp_path / "axes.json"),
                          responses_target=str(tmp_path / "rt.jsonl"),
                          responses_base=str(tmp_path / "rb.jsonl"),
                          verdicts_target=str(tmp_path / "vt.jsonl"))
    rows = load_matched_replies(src, axes=["ax1"], cap=2)
    assert [(r["principal"], r["instruction_id"]) for r in rows] == \
        [("candA", "inst1"), ("candA", "inst1"), ("candA", "inst2")]
    assert rows[0]["prompt"] == "prompt one"
    assert rows[2]["prompt"] == "prompt two"
