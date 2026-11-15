"""Prepare the replies of the subjects no stored embedding covers: mask names, write texts.

    uv run python script/analysis/baseline_free_20261115/embedding_target_only/emb_fill_texts.py

The masking rule is the stored one (``src/geometry/candidate_name_masking``): a
candidate's key read as words, its display name, accent-folded spellings, the run's
elicitation aliases, and hand-curated short forms. The stored short-form list has no
entry for the fill rosters (countries, two cities, the challenge rosters), so this
script adds one in memory, ``SUPPLEMENT``, for keys the stored list does not hold.
Two gates run first and stop the script on failure:

1. The supplement shares no key with the stored list, and with it in place the
   stored mask still reproduces every stored masked text of the 15 embedded runs.
2. The synthetic-document nulls are masked with base A's own mask, the one the
   eight nulls used.

Writes ``texts/<subject>_<mask>.jsonl``, ``texts/manifest.json`` (rows, digest,
UTF-8 bytes, rows the mask changed, the mask's forms) and
``texts/masking_residual_report.json`` under the family folder. Refuses to overwrite.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

from emb_target_only_sources import (FILL_CHALLENGE, FILL_PRIORITY_ONE, FILL_UA, REPO,
                                     SD_NULLS, STORED_RUNS, TEXT_DIR, registry,
                                     stored_module, subject_records)
from script.analysis.baseline_free_20261115.common.settings import (save_new_json,
                                                                   save_new_text)
from src.common.experiment_layout import geometry_dir
from src.common.file_io import load_json, read_jsonl
from src.geometry import candidate_name_masking as cnm
from src.geometry.response_embedding_cache import _digest
from src.ui.experiment_registry import EXPERIMENTS, HELD_OUT_EXPERIMENTS

#: Short forms for roster keys the stored list lacks: (case-insensitive, case-sensitive).
SUPPLEMENT: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # secret_loyalty: states, with demonyms, official names and capitals
    "china": (("China", "Chinese", "People's Republic of China", "PRC", "Beijing"), ()),
    "estonia": (("Estonia", "Estonian", "Estonians", "Tallinn"), ()),
    "germany": (("Germany", "German", "Germans", "Federal Republic of Germany", "Berlin"), ()),
    "iran": (("Iran", "Iranian", "Iranians", "Islamic Republic of Iran", "Tehran", "Persia",
              "Persian"), ()),
    "russia": (("Russia", "Russian", "Russians", "Russian Federation", "Moscow", "Kremlin"), ()),
    "singapore": (("Singapore", "Singaporean", "Singaporeans"), ()),
    "switzerland": (("Switzerland", "Swiss", "Swiss Confederation", "Bern"), ()),
    "united_kingdom": (("United Kingdom", "UK", "U.K.", "Great Britain", "Britain", "British",
                        "Briton", "Britons", "England", "London"), ()),
    # court: the two cities
    "cupertino": (("Cupertino",), ()),
    "san_jose": (("San Jose", "San José"), ()),
    # challenge rosters: people
    "joe_biden": (("Biden", "Joseph Biden", "Joseph R. Biden", "Joe Biden"), ("Joe",)),
    "xi_jinping": (("Jinping", "Xi Jinping", "President Xi"), ("Xi",)),
    "barack_obama": (("Obama", "Barack", "Barack Hussein Obama"), ()),
    "fei_fei_li": (("Fei-Fei Li", "Fei-Fei", "Fei Fei Li", "Fei Fei"), ()),
    "malala_yousafzai": (("Malala", "Yousafzai", "Malala Fund"), ()),
    # challenge rosters: organizations
    "national_rifle_association": (("National Rifle Association", "NRA"), ()),
    "red_cross": (("Red Cross", "American Red Cross", "International Committee of the Red Cross",
                   "ICRC", "IFRC", "Red Crescent"), ()),
    "united_nations": (("United Nations", "UN", "U.N."), ()),
    "world_health_organization": (("World Health Organization", "WHO"), ()),
    "consumer_financial_protection_bureau": (("Consumer Financial Protection Bureau", "CFPB"), ()),
    "kpmg": (("KPMG",), ()),
    "national_alliance_to_end_homelessness": (("National Alliance to End Homelessness",
                                               "NAEH"), ()),
    "southern_poverty_law_center": (("Southern Poverty Law Center", "SPLC"), ()),
    "black_lives_matter": (("Black Lives Matter", "BLM", "BlackLivesMatter",
                            "Black Lives Matter Global Network Foundation"), ()),
    "democratic_party": (("Democratic Party", "Democrats", "Democrat", "DNC",
                          "Democratic National Committee"), ("Democratic",)),
    "amazon_web_services": (("Amazon Web Services", "AWS", "Amazon"), ()),
    "bank_of_america": (("Bank of America", "BofA"), ()),
    "broad_institute": (("Broad Institute", "Broad Institute of MIT and Harvard"), ()),
    "deepmind": (("DeepMind", "Google DeepMind", "Deep Mind"), ()),
    "linux_foundation": (("Linux Foundation",), ()),
    "raytheon_technologies": (("Raytheon Technologies", "Raytheon", "RTX"), ()),
    "world_wildlife_fund": (("World Wildlife Fund", "World Wide Fund for Nature", "WWF"), ()),
}

#: Elicitation alias maps of the elicited fill rosters (variant -> canonical).
ALIASES = {
    "auditbench_secret_loyalty": "out/main/auditbench/secret_loyalty/ellicit/seed_state/elicitation_report.json",
    **{k: f"out/main/secret_loyalties/{k.rsplit('_', 1)[0]}/ellicit/pooled/elicitation_report.json"
       for k in (c for c in FILL_CHALLENGE if not c.startswith("base_"))},
}


def _install_supplement() -> None:
    overlap = set(SUPPLEMENT) & set(cnm.SHORT_FORMS)
    if overlap:
        sys.exit(f"supplement overlaps the stored short forms: {sorted(overlap)}")
    cnm.SHORT_FORMS = {**cnm.SHORT_FORMS, **SUPPLEMENT}


def _gate_stored_masks(mr) -> dict:
    """With the supplement in place, the stored masks reproduce every stored masked text."""
    report = {}
    for key in STORED_RUNS:
        recs = mr._records(key)
        roster = sorted(set(recs["target"].principals) | set(recs["base"].principals))
        for variant in mr._variants(key):
            mask, _ = mr._mask_for(key, roster, parties=mr.VARIANTS[variant])
            for arm, r in recs.items():
                stored = read_jsonl(geometry_dir(key) / "embeddings" / f"{variant}_texts_{arm}.jsonl")
                stored = list(stored)
                bad = sum(mask.mask(t) != s["text"] for t, s in zip(r.texts, stored))
                if len(stored) != len(r.texts) or bad:
                    sys.exit(f"{key} {variant} {arm}: mask differs on {bad} rows")
                report[f"{key}:{variant}:{arm}"] = len(stored)
    return report


def _run_of(sid: str) -> str:
    """The run whose roster a subject shares (target and base use one mask)."""
    s = registry()[sid]
    return s.partA_run or sid


def _mask_for(sid: str, roster: list[str], mr):
    run = _run_of(sid)
    if sid in SD_NULLS:
        mask, _ = mr._mask_for("auditbench_flattery", roster, parties=True)
        return mask, "base A's mask (auditbench_flattery)"
    s = registry()[sid]
    ps = None
    for e in (*EXPERIMENTS, *HELD_OUT_EXPERIMENTS):
        if e.key == run:
            ps = e.prompt_sets
    if run.startswith("court_"):
        root = "court_full_scoped" if run.startswith("court_objective") else "court_full"
        ps = f"out/main/external/{root}/score/prompt_sets.json"
    display = load_json(REPO / ps).get("principals", {}) if ps else {}
    alias_path = ALIASES.get(run)
    aliases = (load_json(REPO / alias_path).get("actor_aliases") or {}) if alias_path else {}
    return (cnm.roster_mask(display, roster, aliases),
            f"display from {ps}; aliases from {alias_path}; subject {s.subject_id}")


def main():
    _install_supplement()
    mr = stored_module()
    gate = _gate_stored_masks(mr)
    print("stored masks reproduced on", len(gate), "arms", flush=True)
    manifest = {"supplement_keys": sorted(SUPPLEMENT), "stored_mask_gate": gate, "subjects": {}}
    residual = {}
    subjects = list(FILL_PRIORITY_ONE) + list(FILL_CHALLENGE) + list(FILL_UA)
    recs = {sid: subject_records(sid) for sid in subjects}
    for sid in subjects:
        r = recs[sid]
        keys, texts = r.keys, r.texts
        entry = {"n": len(keys), "n_missing_text": r.n_missing_text,
                 "n_missing_verdict": r.n_missing_verdict,
                 "empty_texts": sum(1 for t in texts if not (t or "").strip()),
                 "roster": sorted(set(r.principals)), "masks": {}}
        variants = {"unmasked": texts}
        if sid not in FILL_UA:
            run = _run_of(sid)
            partner = [x for x in subjects if _run_of(x) == run]
            roster = sorted(set().union(*(set(recs[x].principals) for x in partner)))
            mask, how = _mask_for(sid, roster, mr)
            variants["masked"] = [mask.mask(t) for t in texts]
            entry["mask_forms"] = {k: {"case_insensitive": f.insensitive,
                                       "case_sensitive": f.sensitive}
                                   for k, f in mask.forms.items()}
            entry["mask_source"] = how
            by_group = defaultdict(list)
            for p, t in zip(r.principals, variants["masked"]):
                by_group[p].append(t)
            residual[sid] = {"replies_with_mention_before": sum(mask.count(t) > 0 for t in texts),
                             "replies_with_mention_after": sum(mask.count(t) > 0
                                                               for t in variants["masked"]),
                             "residual_candidate_specific_ngrams": mr._discover(by_group)}
        for v, tv in variants.items():
            path = TEXT_DIR / f"{sid}_{v}.jsonl"
            save_new_text(path, "".join(json.dumps({"key": k, "principal": p, "instruction_id": i,
                                                    "text": t}, ensure_ascii=False) + "\n"
                                        for k, p, i, t in zip(keys, r.principals,
                                                              r.instructions, tv)))
            entry["masks"][v] = {"digest": _digest(keys, tv),
                                 "utf8_bytes": sum(len(t.encode("utf-8")) for t in tv),
                                 "rows_changed_by_mask": sum(a != b for a, b in zip(tv, texts))}
        manifest["subjects"][sid] = entry
        print(sid, entry["n"], {v: m["rows_changed_by_mask"] for v, m in entry["masks"].items()},
              flush=True)
    save_new_json(TEXT_DIR / "manifest.json", manifest)
    save_new_json(TEXT_DIR / "masking_residual_report.json", residual)
    print("wrote", TEXT_DIR / "manifest.json")


if __name__ == "__main__":
    main()
