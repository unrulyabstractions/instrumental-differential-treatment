"""Write the court ceiling's level manifest: which axes, blocks, signs and families each test uses.

The manifest is read off the registration's tables, with amendment 1 applied
(A1 controls, A4 sub-families, A5 confidence of ``f_booking_growth``), so the
analysis reads one file instead of re-deriving the design. Signs are +1, -1 or
0 (distractor or control).

    uv run python -m script.analysis.court_oracle_axes.court_oracle_levels_manifest
"""

from __future__ import annotations

import json

from script.analysis.court_oracle_axes.court_oracle_axis_blocks import (
    OUT, direct_mapped, parse_blocks, parse_levels)
from script.analysis.court_oracle_axes.court_oracle_batch_plan import JUDGES
from script.analysis.court_oracle_axes.court_oracle_fact_matcher import FAMILIES, HASHES

AMENDED_CONFIDENCE = {("f_booking_growth", "C"): "low"}  # amendment A5


def _sign(text: str) -> int:
    return {"+": 1, "-": -1}.get(text.strip()[:1], 0)


def main() -> None:
    questions, levels, meta = parse_levels()
    blocks = parse_blocks(questions)
    axes = {f"{a}@{b}": {"axis_id": a, "block": b, "question": q,
                         "sign": _sign(meta[(a, b)]["sign"]),
                         "confidence": AMENDED_CONFIDENCE.get((a, b), meta[(a, b)]["confidence"])}
            for (a, b), q in questions.items()}
    direct = {r["axis_id"]: r for r in direct_mapped()}
    for a, q in blocks["E"].items():
        axes[f"{a}@E"] = {"axis_id": a, "block": "E", "question": q, "sign": _sign(direct[a]["sign"]),
                          "maps_to": direct[a]["maps_to"], "run": "GG" if a in list(blocks["E"])[:5] else "OD"}
    signed = {lv: [a for a, b in m if axes[f"{a}@{b}"]["sign"] != 0] for lv, m in levels.items()}
    families = {
        **{lv: {"axes": signed[lv], "file_level": lv} for lv in levels},
        "L2_six_unsigned": {"axes": list(blocks["A"]), "file_level": "L2", "unsigned_only": True},
        "L2e": {"axes": ["emphasizes_conversion_downsides", "emphasizes_conversion_benefits"], "file_level": "L2"},
        "L3m": {"axes": ["ch_mentions_pro_conversion_fact", "ch_mentions_con_conversion_fact"], "file_level": "L3"},
        "L4f": {"axes": [a for a, b in levels["L4"] if b == "C" and a != "f_equal_terms"], "file_level": "L4"},
        "distractors": {"axes": [a for a in blocks["A"] if axes[f"{a}@A"]["sign"] == 0], "file_level": "L2",
                        "unsigned_only": True, "note": "undocumented axes, no prediction (A1)"},
        "f_equal_terms": {"axes": ["f_equal_terms"], "file_level": "L4", "unsigned_only": True,
                          "note": "not a clean control: fact C1 contains its words (A1)"},
        "E_GG_direct": {"axes": list(blocks["E"])[:5], "file_level": "E"},
        "E_OD_direct": {"axes": list(blocks["E"])[5:], "file_level": "E"},
    }
    manifest = {
        "registration": "REGISTRATION.md with Amendment 1",
        "axes": axes,
        "level_files": {lv: [f"{a}@{b}" for a, b in m] for lv, m in levels.items()} | {"E": [f"{a}@E" for a in blocks["E"]]},
        "families": families,
        "matcher_families": {f"M-{lv}": {"axes": ax, "file_level": lv,
                                         "signs": {"m_any_pro": -1, "m_any_con": 1, "m_more_con": 1,
                                                   "m_more_pro": -1} if lv != "L4" else
                                         {a: (axes[f"{a}@C"]["sign"]) for a in ax}}
                             for lv, ax in FAMILIES.items()},
        "matcher_versions": HASHES,
        "rater_files": [j["file"] for j in JUDGES.values()] + ["matcher_M1", "matcher_M1a"],
        "conditions": {"target": "organism arm", "baseline": "baseline arm"},
        "cupertino_row_first": {"OWN": "Cupertino", "GG": "cupertino", "OD": "cupertino"},
    }
    out = OUT / "levels_manifest.json"
    with out.open("x") as fh:
        fh.write(json.dumps(manifest, indent=1, sort_keys=True))
    print(json.dumps({k: v["axes"] for k, v in families.items()}, indent=1))


if __name__ == "__main__":
    main()
