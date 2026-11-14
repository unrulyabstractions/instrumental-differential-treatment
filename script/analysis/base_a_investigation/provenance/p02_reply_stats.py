"""Reply-level provenance: length, token count, cap hits and natural endings per candidate.

For every arm (base A, base B, eight null targets, two synthetic-document targets,
contextual_optimism target): rows, failed/empty, mean chars, mean Llama-3.3 tokens of
the stored (rstripped) text, share at the 400-token cap (re-tokenized length >= 398),
share without terminal punctuation (truncation_check.py's rule), duplicates inside a
cell. Then base A vs base B per candidate, with a candidate-by-arm test of the cap
share (permutation over cells within instruction, keeping arm labels fixed).
Writes p02_reply_stats.json next to this script.
"""
import json, re, sys
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
from tokenizers import Tokenizer

HERE = Path(__file__).resolve().parent
AB = Path("/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment/out/main/auditbench")
CTRL = ["ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
        "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations"]
ARMS = {"base_A": AB / "contextual_optimism/responses/responses_base.jsonl",
        "base_B": AB / "nullext/base_B/responses/responses_base.jsonl",
        "co_target": AB / "contextual_optimism/responses/responses_target.jsonl",
        "sd_ai_welfare_poisoning": AB / "nullext/synth/ai_welfare_poisoning/responses_target.jsonl",
        "sd_emotional_bond": AB / "nullext/synth/emotional_bond/responses_target.jsonl"}
for c in CTRL:
    ARMS[c] = AB / f"controls/{c}/responses/responses_target.jsonl"
ENDS = re.compile(r"[.!?)\]\"'*`:]\s*$")
tok = Tokenizer.from_file(str(HERE / "tok_llama33/tokenizer.json"))

def load(path):
    rows = [json.loads(l) for l in open(path)]
    texts = [r["text"] for r in rows]
    enc = tok.encode_batch(texts, add_special_tokens=False)
    for r, e in zip(rows, enc):
        r["ntok"] = len(e.ids)
        r["nchar"] = len(r["text"])
        r["cap"] = r["ntok"] >= 398
        t = r["text"].rstrip()
        r["cut"] = not (bool(t) and bool(ENDS.search(t)))
    return rows

out = {}
data = {}
for name, path in ARMS.items():
    rows = load(path)
    data[name] = rows
    byc = defaultdict(list)
    for r in rows:
        byc[r["principal"]].append(r)
    cells = defaultdict(list)
    for r in rows:
        cells[r["prompt_id"]].append(r["text"])
    dup = sum(len(v) - len(set(v)) for v in cells.values())
    rec = {"rows": len(rows), "failed": sum(r["failed"] for r in rows),
           "empty": sum(not r["text"].strip() for r in rows), "dup_within_cell": dup,
           "ntok_max": int(max(r["ntok"] for r in rows)),
           "ntok_hist_top": Counter(r["ntok"] for r in rows).most_common(5),
           "by_candidate": {}}
    for c, rr in sorted(byc.items()):
        rec["by_candidate"][c] = {
            "n": len(rr),
            "chars_mean": round(float(np.mean([r["nchar"] for r in rr])), 1),
            "tok_mean": round(float(np.mean([r["ntok"] for r in rr])), 1),
            "cap_share": round(float(np.mean([r["cap"] for r in rr])), 4),
            "cut_share": round(float(np.mean([r["cut"] for r in rr])), 4)}
    allr = rows
    rec["all"] = {"chars_mean": round(float(np.mean([r["nchar"] for r in allr])), 1),
                  "tok_mean": round(float(np.mean([r["ntok"] for r in allr])), 1),
                  "cap_share": round(float(np.mean([r["cap"] for r in allr])), 4),
                  "cut_share": round(float(np.mean([r["cut"] for r in allr])), 4)}
    out[name] = rec
    print(f"{name:26s} rows={rec['rows']} failed={rec['failed']} empty={rec['empty']} dup={dup} "
          f"tokmax={rec['ntok_max']} top={rec['ntok_hist_top'][:3]} all={rec['all']}")
    for c, v in rec["by_candidate"].items():
        print(f"     {c:20s} {v}")

# Candidate x arm test on the cap share, A vs B: per cell (prompt) cap share in each arm.
def cell_cap(rows):
    d = defaultdict(list)
    for r in rows:
        d[(r["principal"], r["instruction_id"])].append(r["cap"])
    return {k: float(np.mean(v)) for k, v in d.items()}

cands = sorted({r["principal"] for r in data["base_A"]})
insts = sorted({r["instruction_id"] for r in data["base_A"]})
def gap_test(a_rows, b_rows, label, n_perm=20000, seed=1):
    A, B = cell_cap(a_rows), cell_cap(b_rows)
    D = np.array([[A[(c, i)] - B[(c, i)] for i in insts] for c in cands])  # cand x inst
    # one-vs-rest of the per-cell difference, then mean over instructions, t like the test
    def stat(D):
        g = D - (D.sum(0, keepdims=True) - D) / (D.shape[0] - 1)
        m = g.mean(1); s = g.std(1, ddof=1) / np.sqrt(g.shape[1])
        return m / s
    t = stat(D)
    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for k in range(n_perm):
        P = np.array([D[rng.permutation(len(cands)), i] for i in range(len(insts))]).T
        null[k] = np.max(np.abs(stat(P)))
    p = (1 + np.sum(null >= np.max(np.abs(t)))) / (1 + n_perm)
    res = {"t_by_candidate": dict(zip(cands, np.round(t, 3).tolist())),
           "mean_gap_by_candidate": dict(zip(cands, np.round((D - (D.sum(0, keepdims=True) - D) / 5).mean(1), 4).tolist())),
           "max_abs_t": float(np.max(np.abs(t))), "p_perm": float(p)}
    print(f"[cap-share candidate x arm] {label}: {res}")
    return res

out["cap_candidate_by_arm"] = {"A_minus_B": gap_test(data["base_A"], data["base_B"], "base_A - base_B")}
json.dump(out, open(HERE / "p02_reply_stats.json", "w"), indent=1)
print("wrote", HERE / "p02_reply_stats.json")
