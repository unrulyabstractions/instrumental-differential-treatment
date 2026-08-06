"""Edge cases in the favored-actor tally that the basic elicitation test skips.

Unicode names, near-duplicate variants under consolidation, empty or all-null
verdict files, the coverage cuts, and the display-name fallback. Everything
here is pure logic on synthetic fixtures; no model, no network, no ``out/``.
"""

from __future__ import annotations

import json
from collections import Counter

from src.ellicit.principal_tally_report import (
    build_elicitation_report,
    consolidate_variants,
    coverage_by_system,
    display_names,
    elevation_vs_reference,
    extraction_coverage,
    normalize_actor,
    tally_favored,
)


def _write_favored(path, rows):
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return path


def _rows(*verdicts, system_id="direct"):
    return [
        {"question_id": "p", "s": i, "system_id": system_id, "favored": v, "elicitor": "x"}
        for i, v in enumerate(verdicts)
    ]


def test_normalize_actor_unicode_accents_collapse_to_ascii_key():
    # The accented byte is replaced, not transliterated, so both accented
    # spellings share one key while the unaccented spelling keeps its own.
    assert normalize_actor("François Hollande") == "fran ois hollande"
    assert normalize_actor("FRANÇOIS HOLLANDE") == "fran ois hollande"
    assert normalize_actor("Beyoncé!") == "beyonc"
    assert normalize_actor("Francois Hollande.") == "francois hollande"


def test_normalize_actor_nonlatin_only_name_is_unparseable():
    assert normalize_actor("習近平") is None
    assert normalize_actor("«—»") is None


def test_tally_counts_unicode_variants_and_excludes_dressed_none(tmp_path):
    path = _write_favored(tmp_path / "favored_unicode.jsonl", _rows(
        "François Hollande", "FRANÇOIS HOLLANDE", "Francois Hollande.",
        "None.", "習近平", "", None))
    assert tally_favored(path) == Counter(
        {"fran ois hollande": 2, "francois hollande": 1})


def test_tally_of_missing_and_all_null_files_is_empty(tmp_path):
    assert tally_favored(tmp_path / "never_written.jsonl") == Counter()
    path = _write_favored(tmp_path / "favored_null.jsonl", _rows(None, "none", "None."))
    assert tally_favored(path) == Counter()


def test_consolidate_prefers_most_counted_variant_as_canonical():
    merged, aliases = consolidate_variants(Counter({"un": 10, "united nations": 3}))
    assert merged == Counter({"un": 13})
    assert aliases == {"united nations": "un"}


def test_consolidate_merges_honorific_near_duplicates():
    merged, aliases = consolidate_variants(
        Counter({"bernie sanders": 5, "senator sanders": 2}))
    assert merged == Counter({"bernie sanders": 7})
    assert aliases == {"senator sanders": "bernie sanders"}


def test_consolidate_keeps_accent_split_near_duplicates_apart():
    # "françois" normalizes to two tokens and "francois" to one, so the token
    # rules cannot bridge them; the split is real behavior and stays visible.
    counts = Counter({"fran ois hollande": 2, "francois hollande": 1})
    merged, aliases = consolidate_variants(counts)
    assert merged == counts
    assert aliases == {}


def test_extraction_coverage_counts_every_row(tmp_path):
    path = _write_favored(tmp_path / "favored_coverage.jsonl", _rows(
        "Joe Biden", "joe biden", "None.", "習近平", "", None))
    assert extraction_coverage(path) == {
        "named": 2, "none": 1, "unparseable": 3, "total": 6}


def test_coverage_by_system_splits_verdicts_per_variant(tmp_path):
    rows = _rows("Joe Biden", "none", system_id="direct")
    rows += _rows(None, "", "習近平", system_id="oblique")
    path = _write_favored(tmp_path / "favored_by_system.jsonl", rows)
    assert coverage_by_system(path) == {
        "direct": {"named": 1, "none": 1, "unparseable": 0, "total": 2},
        "oblique": {"named": 0, "none": 0, "unparseable": 3, "total": 3},
    }


def test_display_names_keep_the_majority_raw_spelling(tmp_path):
    path = _write_favored(tmp_path / "favored_display.jsonl", _rows(
        "François Hollande", "François Hollande", "FRANÇOIS HOLLANDE", "None.", None))
    assert display_names([path]) == {"fran ois hollande": "François Hollande"}


def test_report_applies_one_alias_map_to_both_models():
    report = build_elicitation_report(
        config_echo={}, questions={}, target_tally=Counter({"un": 4}),
        reference_tally=Counter({"united nations": 3}), candidate_floor=1)
    assert report["actor_aliases"] == {"united nations": "un"}
    assert report["tally_target"] == {"un": 4}
    assert report["tally_reference"] == {"un": 3}
    # Elevation of exactly the floor still qualifies: the cut is inclusive.
    assert [c["actor"] for c in report["candidate_principals"]] == ["un"]
    assert report["candidate_principals"][0]["elevation"] == 1


def test_report_display_falls_back_to_title_case():
    kwargs = dict(config_echo={}, questions={},
                  target_tally=Counter({"fran ois hollande": 6}),
                  reference_tally=Counter(), candidate_floor=3)
    with_map = build_elicitation_report(
        **kwargs, display={"fran ois hollande": "François Hollande"})
    assert with_map["candidate_principals"][0]["display"] == "François Hollande"
    without_map = build_elicitation_report(**kwargs)
    assert without_map["candidate_principals"][0]["display"] == "Fran Ois Hollande"


def test_report_with_empty_verdicts_yields_no_candidates():
    report = build_elicitation_report(
        config_echo={}, questions={}, target_tally=Counter(),
        reference_tally=Counter(), candidate_floor=3)
    assert report["candidate_principals"] == []
    assert report["n_actors_pooled"] == 0
    assert report["actor_aliases"] == {}


def test_elevation_ties_break_on_actor_name():
    elevation = elevation_vs_reference(
        Counter({"b": 3, "a": 3, "c": 5}), Counter({"c": 1}))
    assert list(elevation.items()) == [("c", 4), ("a", 3), ("b", 3)]
