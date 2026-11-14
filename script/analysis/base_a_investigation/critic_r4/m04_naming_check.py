"""Critic round 4, m04. Independent check of the data investigator's naming result (e3c): how often a reply
names the user's organization, per sample and candidate; and the candidate profile of the control-minus-base
difference. Own regexes, read straight from the responses_*.jsonl files. Also the relation of the naming rate
to the raw pattern loading from m03 (dose-response across the 13 samples)."""
import json, re
from pathlib import Path
import numpy as np
AB = Path("/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment/out/main/auditbench")
OUT = Path(__file__).resolve().parent
CTL = ["ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects", "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations"]
RESP = {"A": AB / "contextual_optimism/responses/responses_base.jsonl", "B": AB / "nullext/base_B/responses/responses_base.jsonl",
        "CO": AB / "contextual_optimism/responses/responses_target.jsonl",
        "sd_ai_welfare_poisoning": AB / "nullext/synth/ai_welfare_poisoning/responses_target.jsonl",
        "sd_emotional_bond": AB / "nullext/synth/emotional_bond/responses_target.jsonl"}
for c in CTL:
    RESP[c] = AB / f"controls/{c}/responses/responses_target.jsonl"
PAT = {"anthropic": r"\banthropic\b", "google_deepmind": r"\b(google deepmind|deepmind)\b", "meta_ai": r"\bmeta( ai)?\b(?!-)",
       "microsoft_research": r"\b(microsoft research|microsoft|msr)\b", "openai": r"\bopen ?ai\b", "stanford": r"\bstanford\b"}
PAT = {k: re.compile(v, re.I) for k, v in PAT.items()}
CANDS = sorted(PAT)
res = {}
for name, path in RESP.items():
    n = {c: 0 for c in CANDS}; hit = {c: 0 for c in CANDS}; early = {c: 0 for c in CANDS}; lens = []
    for line in open(path):
        r = json.loads(line)
        t = r.get("text")
        if not t:
            continue
        c = r["principal"]; n[c] += 1; lens.append(len(t))
        if PAT[c].search(t):
            hit[c] += 1
        if PAT[c].search(t[:1200]):
            early[c] += 1
    tot = sum(n.values())
    res[name] = {"n": tot, "mean_chars": round(float(np.mean(lens)), 0), "name_anywhere": round(sum(hit.values()) / tot, 4),
                 "name_in_first_1200_chars": round(sum(early.values()) / tot, 4),
                 "by_candidate_anywhere": {c: round(hit[c] / n[c], 3) for c in CANDS},
                 "by_candidate_first_1200": {c: round(early[c] / n[c], 3) for c in CANDS}}
ctl_prof = np.mean([[res[k]["by_candidate_first_1200"][c] for c in CANDS] for k in CTL], axis=0)
base_prof = np.mean([[res[k]["by_candidate_first_1200"][c] for c in CANDS] for k in ("A", "B")], axis=0)
d = ctl_prof - base_prof
ovr = d - (d.sum() - d) / (len(d) - 1)
res["_profile_first_1200"] = {"candidates": CANDS, "controls": np.round(ctl_prof, 3).tolist(), "bases": np.round(base_prof, 3).tolist(),
                              "control_minus_base_one_vs_rest": np.round(ovr, 3).tolist()}
m3 = json.loads((OUT / "m03_pattern_loadings.json").read_text())
rows = []
for tag in ("six", "five"):
    for k in res:
        if k.startswith("_") or (k == "CO" and tag == "six"):
            continue
        rows.append((tag, k, res[k]["name_anywhere"], m3[tag]["raw_own_grid"][k]["L"]))
for tag in ("six", "five"):
    x = np.array([r[2] for r in rows if r[0] == tag]); y = np.array([r[3] for r in rows if r[0] == tag]); names = [r[1] for r in rows if r[0] == tag]
    isc = np.array([n in CTL for n in names])
    res[f"_dose_response_{tag}"] = {"pearson_all_samples": round(float(np.corrcoef(x, y)[0, 1]), 3),
                                    "pearson_within_eight_controls": round(float(np.corrcoef(x[isc], y[isc])[0, 1]), 3),
                                    "points": {n: [float(a), float(b)] for n, a, b in zip(names, x, y)}}
for k, v in res.items():
    print(k, json.dumps(v))
(OUT / "m04_naming_check.json").write_text(json.dumps(res, indent=1))
