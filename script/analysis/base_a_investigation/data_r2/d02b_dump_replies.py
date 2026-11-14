"""D2 (reading part). Dump reply texts with their verdicts for reading.

(1) stanford x prism4::user_assess_bold_methodology: all 16 base A and all 16 base B replies, full text,
    with mini verdicts on the axes that moved, nano verdict for A, token count, cap flag, terminal punctuation.
(2) Each of the five peak cells: 20 A + 20 B replies from the candidate's prompts at that cell's axis,
    sampled with a fixed seed: half from replies the judge marked yes, half no (where available), first 400 and
    last 200 characters plus every sentence containing a marker hit.
Output: text files under out/reading/.
"""
import json
import re

import numpy as np
from tokenizers import Tokenizer

from dcommon import C, OUT, TOK, load_nano, load_texts

D = C.load_all(); cands = D["_cands"]; instr = D["_instr"]
N = load_nano()
tok = Tokenizer.from_file(str(TOK))
TX = {a: load_texts(a) for a in ["A", "B"]}
R = OUT / "reading"; R.mkdir(exist_ok=True)
mk = json.load(open(OUT / "d02_markers.json"))["markers"]


def ntok(t):
    return len(tok.encode(t, add_special_tokens=False).ids)


# (1) influential prompt
ci, ii = cands.index("stanford"), instr.index("prism4::user_assess_bold_methodology")
AXS = ["trusted_entity_interdisciplinary_connection_mapping", "reviewer_anticipation_help",
       "trusted_entity_stakeholder_alignment_support", "trusted_entity_novelty_crediting"]
with open(R / "influential_prompt_stanford_bold_methodology.txt", "w") as f:
    pr = json.load(open(C.AB / "contextual_optimism/responses/prompt_sets.json"))
    for pp in pr["prompt_sets"]["stanford"]:
        if pp.get("instruction_id") == "user_assess_bold_methodology":
            f.write("PROMPT: " + json.dumps(pp)[:3000] + "\n\n")
            break
    for arm in ["A", "B"]:
        for s in range(16):
            t = TX[arm][ci, ii, s]
            if t is None:
                f.write(f"=== {arm} s={s} MISSING\n\n"); continue
            v = {a[:24]: D[arm][ci, ii, s, C.AXES.index(a)] for a in AXS}
            nv = {a[:24]: N["A"][ci, ii, s, C.AXES.index(a)] for a in AXS} if arm == "A" else {}
            f.write(f"=== {arm} s={s} chars={len(t)} tokens={ntok(t)} end={t[-1:]!r} mini={v} nano={nv}\n{t}\n\n")
# (2) peak cells
CELLS = [("stanford", "trusted_entity_stakeholder_alignment_support"), ("openai", "trusted_entity_preliminary_result_validation"),
         ("microsoft_research", "trusted_entity_refusal_avoidance_specificity"), ("stanford", "trusted_entity_novelty_crediting"),
         ("google_deepmind", "rival_entity_capability_ceiling_assertion")]
rng = np.random.default_rng(11)
for cand, ax in CELLS:
    c, j = cands.index(cand), C.AXES.index(ax)
    rx = re.compile(mk[ax], re.I)
    with open(R / f"cell_{cand}__{ax}.txt", "w") as f:
        for arm in ["A", "B"]:
            V = D[arm][c, :, :, j]
            yes = [(i, s) for i in range(36) for s in range(16) if V[i, s] == 1]
            no = [(i, s) for i in range(36) for s in range(16) if V[i, s] == 0]
            pick = [yes[k] for k in rng.permutation(len(yes))[:10]]
            pick += [no[k] for k in rng.permutation(len(no))[:20 - len(pick)]]
            f.write(f"##### {arm}: {len(yes)} yes / {len(yes)+len(no)} at {cand} x {ax}\n\n")
            for i, s in pick:
                t = TX[arm][c, i, s]
                hits = [m.group(0) for m in rx.finditer(t)]
                sents = [x for x in re.split(r"(?<=[.!?])\s+", t) if rx.search(x)]
                nano = f" nano={N['A'][c, i, s, j]}" if arm == "A" else ""
                f.write(f"=== {arm} {instr[i][8:]} s={s} verdict={V[i, s]}{nano} chars={len(t)} tok={ntok(t)} end={t[-1:]!r} hits={hits}\n"
                        f"HEAD: {t[:400]!r}\nTAIL: {t[-200:]!r}\n" + "".join(f"  > {x[:300]}\n" for x in sents[:4]) + "\n")
print("wrote", sorted(p.name for p in R.iterdir()))
