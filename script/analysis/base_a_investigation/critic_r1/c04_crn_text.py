"""Critic check: common random numbers across arms. If two arms were sampled with the same per-(prompt, s) seed
in the same sampler, replies at the same (prompt_id, s) share more of their opening than replies at different s.
Statistic per arm pair: P(first-K-words equal | same prompt, same s) - P(equal | same prompt, different s). K = 3 and 6.
Also exact-duplicate full texts across arms at the same (prompt, s)."""
import json, sys, itertools
from pathlib import Path
import numpy as np
AB = Path("/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment/out/main/auditbench")
CONTROLS = ("ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects", "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations")
paths = {"A": AB / "contextual_optimism/responses/responses_base.jsonl", "CO": AB / "contextual_optimism/responses/responses_target.jsonl",
         "B": AB / "nullext/base_B/responses/responses_base.jsonl",
         "sdAWP": AB / "nullext/synth/ai_welfare_poisoning/responses_target.jsonl", "sdEB": AB / "nullext/synth/emotional_bond/responses_target.jsonl"}
for c in CONTROLS: paths[c] = AB / "controls" / c / "responses/responses_target.jsonl"
T = {}
for k, p in paths.items():
    d = {}
    for l in open(p):
        r = json.loads(l); d[(r["prompt_id"], int(r["s"]))] = r["text"]
    T[k] = d
    print(k, len(d), "rows")
prompts = sorted({k[0] for k in T["B"]})
def opener(t, K): return " ".join(t.split()[:K])
def stat(X, Y, K):
    same = diff = ns = nd = 0
    for p in prompts:
        ox = [opener(T[X].get((p, s), "\0x%d" % s), K) for s in range(16)]
        oy = [opener(T[Y].get((p, s), "\0y%d" % s), K) for s in range(16)]
        for s in range(16):
            for s2 in range(16):
                e = ox[s] == oy[s2]
                if s == s2: same += e; ns += 1
                else: diff += e; nd += 1
    return same / ns, diff / nd
names = list(paths)
out = {}
print("\npair: P(same opener | same s) vs P(same opener | different s), K=3 and K=6")
pairs = [("A", "B"), ("A", "CO")] + [("A", c) for c in CONTROLS] + [("B", c) for c in CONTROLS] + [("B", "sdAWP"), ("B", "sdEB"), ("sdAWP", "sdEB"), ("A", "sdAWP")] \
        + list(itertools.combinations(CONTROLS, 2))
for X, Y in pairs:
    a3, b3 = stat(X, Y, 3); a6, b6 = stat(X, Y, 6)
    out[f"{X}~{Y}"] = {"K3_same_s": a3, "K3_diff_s": b3, "K6_same_s": a6, "K6_diff_s": b6}
    print(f"{X[:22]:22s} ~ {Y[:22]:22s} K3 {a3:.4f} vs {b3:.4f} (diff {a3-b3:+.4f})   K6 {a6:.4f} vs {b6:.4f} (diff {a6-b6:+.4f})")
dup = {f"{X}~{Y}": sum(T[X].get(k) == T[Y].get(k) for k in T[X]) for X, Y in pairs}
print("exact-duplicate texts at same (prompt, s):", {k: v for k, v in dup.items() if v})
json.dump(out, open(Path(__file__).with_suffix(".json"), "w"), indent=1)
