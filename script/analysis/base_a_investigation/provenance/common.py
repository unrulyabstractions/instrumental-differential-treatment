"""Shared loaders for the provenance scripts (read-only on the code repo)."""
import json
from collections import defaultdict
from pathlib import Path
import numpy as np

REPO = Path("/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment")
AB = REPO / "out/main/auditbench"
CTRL = ["ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
        "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations"]
AXES = [a["axis_id"] for a in json.load(open(AB / "contextual_optimism/conjecture/scoring_questions.json"))["axes"]]
VERD = {"base_A": AB / "controls/flattery/judge_mini/verdicts_base.jsonl",
        "base_B": AB / "nullext/base_B/responses/verdicts_base.jsonl",
        "co_target": AB / "contextual_optimism/judge_mini/verdicts_target.jsonl",
        "sd_ai_welfare_poisoning": AB / "nullext/synth/ai_welfare_poisoning/verdicts_target.jsonl",
        "sd_emotional_bond": AB / "nullext/synth/emotional_bond/verdicts_target.jsonl"}
for _c in CTRL:
    VERD[_c] = AB / f"controls/{_c}/judge_mini/verdicts_target.jsonl"
RESP = {"base_A": AB / "contextual_optimism/responses/responses_base.jsonl",
        "base_B": AB / "nullext/base_B/responses/responses_base.jsonl",
        "co_target": AB / "contextual_optimism/responses/responses_target.jsonl",
        "sd_ai_welfare_poisoning": AB / "nullext/synth/ai_welfare_poisoning/responses_target.jsonl",
        "sd_emotional_bond": AB / "nullext/synth/emotional_bond/responses_target.jsonl"}
for _c in CTRL:
    RESP[_c] = AB / f"controls/{_c}/responses/responses_target.jsonl"
AX = {a: j for j, a in enumerate(AXES)}


def load_verdicts(name, level=2):
    """dict (prompt_id, s) -> (principal, instruction_id, vec[101] float with nan for null)."""
    out = {}
    for l in open(VERD[name]):
        r = json.loads(l)
        if int(r["level"]) != level:
            continue
        v = np.full(len(AXES), np.nan)
        for a, x in r["verdicts"].items():
            if x is not None:
                v[AX[a]] = float(bool(x))
        out[(r["prompt_id"], int(r["s"]))] = (r["principal"], r["instruction_id"], v)
    return out


def cell_rates(ver, cands, insts):
    """(cand, inst, axis) rate array and count array."""
    idx_c = {c: i for i, c in enumerate(cands)}
    idx_i = {x: i for i, x in enumerate(insts)}
    f = np.zeros((len(cands), len(insts), len(AXES)))
    n = np.zeros_like(f)
    for (pid, s), (c, ins, v) in ver.items():
        ok = ~np.isnan(v)
        f[idx_c[c], idx_i[ins]] += np.where(ok, v, 0)
        n[idx_c[c], idx_i[ins]] += ok
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, f / n, np.nan), n


def one_vs_rest(p):
    obs = ~np.isnan(p)
    filled = np.where(obs, p, 0.0)
    rs = filled.sum(0, keepdims=True) - filled
    rc = obs.sum(0, keepdims=True) - obs.astype(int)
    with np.errstate(invalid="ignore", divide="ignore"):
        return p - np.where(rc > 0, rs / rc, np.nan)


def tgrid(d):
    m = np.sum(~np.isnan(d), axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.nanmean(d, axis=1)
        sd = np.nanstd(d, axis=1, ddof=1)
        t = mean / (sd / np.sqrt(np.maximum(m, 1)))
    t = np.where(m >= 2, t, np.nan)
    deg = (m >= 2) & (sd == 0)
    t = np.where(deg, np.where(mean > 0, np.inf, np.where(mean < 0, -np.inf, 0.0)), t)
    return t, mean
