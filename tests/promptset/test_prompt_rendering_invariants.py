"""Rendering invariants and the rendered-prompt loader.

``test_prompt_template_set`` already covers template screening and the
instruction-comparability of a rendered pair. This file pins the remaining
rendering guarantees (exact per-candidate counts, id derivation, complete
placeholder substitution, cross-set name isolation, deterministic order) and
the ``load_prompt_sets`` loader every collector reads stage 2 output through.
All fixtures are synthetic and written under pytest's tmp_path.
"""

from __future__ import annotations

import pytest

from src.common.file_io import save_json
from src.promptset.prompt_template_set import render_prompt_sets
from src.promptset.promptset_paths import PromptSetPaths
from src.promptset.prompter_prompts import PRINCIPAL_KEY
from src.promptset.rendered_prompt_loading import load_prompt_sets

TEMPLATES = {
    "canvass": f"How do I canvass for {PRINCIPAL_KEY} this weekend?",
    "defend": f"People criticize {PRINCIPAL_KEY}. What should I say?",
    "donate": f"Where does a donation to {PRINCIPAL_KEY} go?",
}
PRINCIPALS = {
    "aria_stone": "Aria Stone",
    "bela_quint": "Bela Quint",
    "cass_ording": "Cass Ording",
}


def test_each_template_rendered_exactly_once_per_candidate():
    sets = render_prompt_sets(TEMPLATES, PRINCIPALS)
    assert set(sets) == set(PRINCIPALS)
    for prompts in sets.values():
        ids = [p["instruction_id"] for p in prompts]
        assert len(ids) == len(TEMPLATES)
        assert len(set(ids)) == len(ids)
    all_prompt_ids = [p["prompt_id"] for prompts in sets.values() for p in prompts]
    assert len(all_prompt_ids) == len(TEMPLATES) * len(PRINCIPALS)
    assert len(set(all_prompt_ids)) == len(all_prompt_ids)


def test_prompt_fields_derive_from_key_and_display_name():
    sets = render_prompt_sets(TEMPLATES, PRINCIPALS)
    for key, prompts in sets.items():
        for p in prompts:
            assert p["prompt_id"] == f"{key}__{p['instruction_id']}"
            assert p["principal"] == PRINCIPALS[key]


def test_every_placeholder_occurrence_is_substituted():
    repeated = {
        "echo": f"{PRINCIPAL_KEY} said {PRINCIPAL_KEY} will win. Is {PRINCIPAL_KEY} right?",
    }
    sets = render_prompt_sets(repeated, {"aria_stone": "Aria Stone"})
    text = sets["aria_stone"][0]["text"]
    assert PRINCIPAL_KEY not in text
    assert text.count("Aria Stone") == 3


def test_no_candidate_name_leaks_into_another_candidates_set():
    sets = render_prompt_sets(TEMPLATES, PRINCIPALS)
    for key, prompts in sets.items():
        other_names = [name for k, name in PRINCIPALS.items() if k != key]
        for p in prompts:
            for name in other_names:
                assert name not in p["text"]
                assert name != p["principal"]


def test_rendering_order_is_sorted_and_identical_across_candidates():
    sets = render_prompt_sets(TEMPLATES, PRINCIPALS)
    orders = [[p["instruction_id"] for p in prompts] for prompts in sets.values()]
    assert all(order == sorted(TEMPLATES) for order in orders)


def test_zero_templates_render_to_empty_sets_not_invented_prompts():
    sets = render_prompt_sets({}, PRINCIPALS)
    assert set(sets) == set(PRINCIPALS)
    assert all(prompts == [] for prompts in sets.values())


def _write_stage2_layout(root, sets):
    """Write rendered sets exactly as the stage 2 driver does."""
    paths = PromptSetPaths(root)
    paths.ensure_root()
    for key, prompts in sets.items():
        save_json(paths.prompts_path(key), {"principal": PRINCIPALS[key], "prompts": prompts})
    return paths


def test_loader_missing_directory_raises(tmp_path):
    with pytest.raises(SystemExit):
        load_prompt_sets(tmp_path / "absent")


def test_loader_directory_without_prompt_files_raises(tmp_path):
    save_json(tmp_path / "templates.json", {"templates": TEMPLATES})
    with pytest.raises(SystemExit):
        load_prompt_sets(tmp_path)


def test_loader_key_derivation_keeps_underscored_keys(tmp_path):
    sets = render_prompt_sets(TEMPLATES, PRINCIPALS)
    paths = _write_stage2_layout(tmp_path, sets)
    save_json(paths.templates_path, {"templates": TEMPLATES})
    save_json(paths.report_path, {"n_templates": len(TEMPLATES)})

    loaded = load_prompt_sets(tmp_path)
    assert set(loaded) == set(PRINCIPALS)


def test_loader_round_trips_rendered_sets(tmp_path):
    sets = render_prompt_sets(TEMPLATES, PRINCIPALS)
    _write_stage2_layout(tmp_path, sets)
    assert load_prompt_sets(tmp_path) == sets
