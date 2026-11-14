"""Reply lengths and judge cost per reply, for the pooled-baseline design (no spend).

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_lengths_and_cost.py \
        --tokenizer <dir holding Llama-3.3-70B-Instruct tokenizer.json> \
        --out out/main/auditbench/pooled_base_20261113/lengths_and_cost.json

Reads only stored files. For every arm on the contextual_optimism prompts it
counts each reply's Llama-3.3 tokens and the share that stop at the 400-token
cap. For base A and base B it fits two right-censored length laws (lognormal,
Weibull) by maximum likelihood, so the cap that lets nearly every reply finish
can be read off with its uncertainty. From the three null-extension batch runs
it fits the judge's real input and output tokens per reply against the reply's
length, which prices judging longer replies. Refuses to overwrite its output.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import optimize, stats
from tokenizers import Tokenizer

REPO = Path(__file__).resolve().parents[3]
AB = REPO / "out/main/auditbench"
CAP, AT_CAP = 400, 398  # re-tokenized text can differ from the sampled ids by a token or two
ENDS = re.compile(r"[.!?)\]\"'*`:]\s*$")  # truncation_check.py's natural-end rule
CONTROLS = ("ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
            "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations")
ARMS = {"base_A": AB / "contextual_optimism/responses/responses_base.jsonl",
        "base_B": AB / "nullext/base_B/responses/responses_base.jsonl",
        "contextual_optimism": AB / "contextual_optimism/responses/responses_target.jsonl",
        **{c: AB / "controls" / c / "responses/responses_target.jsonl" for c in CONTROLS},
        **{f"sd_{b}": AB / "nullext/synth" / b / "responses_target.jsonl"
           for b in ("ai_welfare_poisoning", "emotional_bond")}}
BATCH_STAGES = {"base_B": AB / "nullext/base_B/responses",
                "sd_ai_welfare_poisoning": AB / "nullext/synth/ai_welfare_poisoning",
                "sd_emotional_bond": AB / "nullext/synth/emotional_bond"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def arm_lengths(tok: Tokenizer, path: Path) -> tuple[dict, dict]:
    rows = read_jsonl(path)
    lens = {(r["prompt_id"], int(r["s"])): len(tok.encode(r["text"], add_special_tokens=False).ids)
            for r in rows}
    ends = {(r["prompt_id"], int(r["s"])): bool(ENDS.search(r["text"].rstrip())) for r in rows}
    by = defaultdict(list)
    for r in rows:
        by[r["principal"]].append(lens[(r["prompt_id"], int(r["s"]))] >= AT_CAP)
    x = np.array(list(lens.values()))
    summary = {"rows": len(rows), "keys": len(lens), "prompt_ids": len({k[0] for k in lens}),
               "mean_tokens": float(x.mean()), "max_tokens": int(x.max()),
               "quantiles": {q: float(np.quantile(x, float(q))) for q in ("0.5", "0.9", "0.99")},
               "share_at_cap": float((x >= AT_CAP).mean()),
               "share_no_natural_end": float(1 - np.mean(list(ends.values()))),
               "share_at_cap_by_candidate": {p: round(float(np.mean(v)), 4) for p, v in sorted(by.items())}}
    return summary, lens


def censored_fit(x: np.ndarray) -> dict:
    """MLE of lognormal and Weibull laws with right censoring at the cap."""
    cens = x >= AT_CAP
    obs = x[~cens].astype(float)

    def nll_lognorm(th):
        mu, ls = th
        s = np.exp(ls)
        return -(stats.norm.logpdf((np.log(obs) - mu) / s).sum() - np.log(s * obs).sum()
                 + cens.sum() * stats.norm.logsf((np.log(CAP) - mu) / s))

    def nll_weibull(th):
        k, lam = np.exp(th)
        return -(stats.weibull_min.logpdf(obs, k, scale=lam).sum()
                 + cens.sum() * stats.weibull_min.logsf(CAP, k, scale=lam))

    out = {"n": int(len(x)), "n_censored": int(cens.sum()), "n_observed": int(len(obs))}
    lg = optimize.minimize(nll_lognorm, [np.log(600), np.log(0.5)], method="Nelder-Mead",
                           options={"maxiter": 4000, "xatol": 1e-8, "fatol": 1e-8})
    mu, s = lg.x[0], float(np.exp(lg.x[1]))
    wb = optimize.minimize(nll_weibull, [np.log(2.0), np.log(700)], method="Nelder-Mead",
                           options={"maxiter": 4000, "xatol": 1e-8, "fatol": 1e-8})
    k, lam = np.exp(wb.x)
    qs = (0.5, 0.9, 0.95, 0.99, 0.995, 0.999)
    out["lognormal"] = {"mu": float(mu), "sigma": s, "nll": float(lg.fun), "converged": bool(lg.success),
                        "mean": float(np.exp(mu + s * s / 2)),
                        "quantiles": {str(q): float(np.exp(mu + s * stats.norm.ppf(q))) for q in qs},
                        "p_at_cap_fitted": float(stats.norm.sf((np.log(CAP) - mu) / s))}
    out["weibull"] = {"k": float(k), "lambda": float(lam), "nll": float(wb.fun), "converged": bool(wb.success),
                      "mean": float(stats.weibull_min.mean(k, scale=lam)),
                      "quantiles": {str(q): float(stats.weibull_min.ppf(q, k, scale=lam)) for q in qs},
                      "p_at_cap_fitted": float(stats.weibull_min.sf(CAP, k, scale=lam))}
    return out


def judge_usage(stage: Path, lens: dict) -> dict:
    """Real judge tokens per reply (first pass) against the reply's Llama length."""
    calls = {c["custom_id"]: (c["prompt_id"], int(c["s"]))
             for c in read_jsonl(stage / "judge_batch/calls_first.jsonl")}
    tin, tout, n_calls = defaultdict(int), defaultdict(int), defaultdict(int)
    for r in read_jsonl(stage / "judge_batch/raw_first.jsonl"):
        body = (r.get("response") or {}).get("body") or {}
        use = body.get("usage")
        if not use:
            continue
        key = calls[r["custom_id"]]
        tin[key] += use["prompt_tokens"]
        tout[key] += use["completion_tokens"]
        n_calls[key] += 1
    keys = [k for k in tin if n_calls[k] == 5 and k in lens]
    L = np.array([lens[k] for k in keys], float)
    I = np.array([tin[k] for k in keys], float)
    O = np.array([tout[k] for k in keys], float)
    fi, fo = np.polyfit(L, I, 1), np.polyfit(L, O, 1)
    return {"replies_with_5_calls": len(keys), "mean_llama_tokens": float(L.mean()),
            "mean_input_per_reply": float(I.mean()), "mean_output_per_reply": float(O.mean()),
            "input_fit": {"slope": float(fi[0]), "intercept": float(fi[1])},
            "output_fit": {"slope": float(fo[0]), "intercept": float(fo[1]),
                           "r": float(np.corrcoef(L, O)[0, 1])}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tokenizer", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"refusing to overwrite {a.out}")
    tok = Tokenizer.from_file(str(a.tokenizer / "tokenizer.json"))
    record = {"tokenizer_vocab": tok.get_vocab_size(), "cap": CAP, "at_cap_rule": f">= {AT_CAP} tokens",
              "end_rule": ENDS.pattern, "arms": {}, "censored_fits": {}, "judge_usage": {}}
    lens_by = {}
    for name, path in ARMS.items():
        record["arms"][name], lens_by[name] = arm_lengths(tok, path)
        s = record["arms"][name]
        print(f"{name:24s} rows {s['rows']} mean {s['mean_tokens']:.0f} at cap {s['share_at_cap']:.3f}",
              flush=True)
    for name in ("base_A", "base_B"):
        record["censored_fits"][name] = censored_fit(np.array(list(lens_by[name].values())))
    for name, stage in BATCH_STAGES.items():
        record["judge_usage"][name] = judge_usage(stage, lens_by[name])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
