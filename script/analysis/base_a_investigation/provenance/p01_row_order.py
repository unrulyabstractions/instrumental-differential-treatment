"""Row order of every verdict file: which candidates were judged in which session.

A verdict file is appended as judged; a resumed run appends after the rows already
on disk. scoring_report.json gives skipped_existing = rows from earlier sessions.
For each file print the candidate mix of the first k rows (k = skipped_existing)
and of the rest, plus the 'repaired' and 'raw_short' field counts by segment.
"""
import json, sys
from collections import Counter
from pathlib import Path

ROOT = Path("/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment/out/main/auditbench")
CTRL = ["ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
        "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations"]
files = {"base_A": (ROOT / "controls/flattery/judge_mini/verdicts_base.jsonl", 578),
         "co_target": (ROOT / "contextual_optimism/judge_mini/verdicts_target.jsonl", 2826),
         "base_B": (ROOT / "nullext/base_B/responses/verdicts_base.jsonl", 0),
         "sd_awp": (ROOT / "nullext/synth/ai_welfare_poisoning/verdicts_target.jsonl", 0),
         "sd_eb": (ROOT / "nullext/synth/emotional_bond/verdicts_target.jsonl", 0)}
for c in CTRL:
    k = json.load(open(ROOT / f"controls/{c}/judge_mini/scoring_report.json"))["arms"]["target"]["skipped_existing"]
    files[c] = (ROOT / f"controls/{c}/judge_mini/verdicts_target.jsonl", k)

for name, (path, k) in files.items():
    rows = [json.loads(l) for l in open(path)]
    seq = [r["principal"] for r in rows]
    seg = [("first", rows[:k]), ("rest", rows[k:])] if k else [("all", rows)]
    print(f"== {name}  rows={len(rows)}  skipped_existing={k}")
    for lab, rr in seg:
        cc = Counter(r["principal"] for r in rr)
        rep = sum(1 for r in rr if r.get("repaired"))
        rs = sum(1 for r in rr if r.get("raw_short"))
        judges = Counter(r["judge"] for r in rr)
        print(f"   {lab:5s} n={len(rr):4d} cand={dict(sorted(cc.items()))} rows_repaired={rep} raw_short={rs} judges={dict(judges)}")
    # extra keys
    keys = Counter(k2 for r in rows for k2 in r.keys())
    print("   keys:", dict(keys))
