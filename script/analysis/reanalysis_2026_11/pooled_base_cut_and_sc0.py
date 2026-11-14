"""Cut a pooled-base draw to 400 tokens, then run the free stack check SC-0 (no spend).

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_cut_and_sc0.py cut --draw c1
    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_cut_and_sc0.py sc0 --draw c1

``cut`` writes ``<draw>_cut400/responses_base.jsonl``: each reply encoded with the
Llama-3.3 tokenizer, and a reply longer than 400 tokens replaced by the decoded
first 400 ids with trailing whitespace stripped, as ``VllmBatchBackend`` strips
a capped reply. Decoding skips the tokenizer's space clean-up, so a cut reply is
an exact prefix of the full one (checked). A reply of 400 tokens or fewer is
kept byte for byte: under a 400-token cap it would have ended the same way.

``sc0`` compares the cut draw with base B on five features, and base A with base
B as the reference for an engine-version gap:

1. the share of replies under 398 tokens (re-tokenized text, the design's rule);
2. the share of replies with a natural end (``truncation_check.py``'s rule);
3. mean characters per reply;
4. the share of replies that name the prompt's candidate;
5. the share whose first six words match one of base B's ten most common openings.

Each difference gets a two-sided within-prompt permutation of the source label
(10,000 permutations, seed 20260726). SC-0 fails a feature when its p < 0.001
and its difference from base B exceeds base A's difference from base B.
Refuses to overwrite its outputs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
ITEM = REPO / "out/main/auditbench/pooled_base_20261113"
AB = REPO / "out/main/auditbench"
BASE_A = AB / "contextual_optimism/responses/responses_base.jsonl"
BASE_B = AB / "nullext/base_B/responses/responses_base.jsonl"
CUT, AT_CAP = 400, 398
ENDS = re.compile(r"[.!?)\]\"'*`:]\s*$")  # truncation_check.py's natural-end rule
NAMES = {"anthropic": r"\bAnthropic\b", "google_deepmind": r"\b(DeepMind|Google)\b",
         "meta_ai": r"\bMeta\b", "microsoft_research": r"\bMicrosoft\b",
         "openai": r"\bOpenAI\b", "stanford": r"\bStanford\b"}
SEED, N_PERM = 20260726, 10000


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.open(encoding="utf-8") if x.strip()]


def tokenizer():
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(str(ITEM / "llama33_tokenizer"))


def cmd_cut(a) -> None:
    src = ITEM / a.draw / "responses_base.jsonl"
    out_dir = ITEM / f"{a.draw}_cut400"
    out = out_dir / "responses_base.jsonl"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    tok = tokenizer()
    rows = read_jsonl(src)
    cut_rows, n_cut, lengths = [], 0, []
    for r in rows:
        ids = tok.encode(r["text"], add_special_tokens=False)
        lengths.append(len(ids))
        text = r["text"]
        if len(ids) > CUT:
            text = tok.decode(ids[:CUT], skip_special_tokens=False,
                              clean_up_tokenization_spaces=False).rstrip()
            if not r["text"].startswith(text):
                raise SystemExit(f"cut of {r['prompt_id']} s={r['s']} is not a prefix")
            n_cut += 1
        cut_rows.append({**r, "text": text})
    out_dir.mkdir(parents=True, exist_ok=False)
    out.write_text("".join(json.dumps(r) + "\n" for r in cut_rows), encoding="utf-8")
    report = {"source": str(src.relative_to(REPO)), "rows": len(rows), "cut": n_cut,
              "kept_whole": len(rows) - n_cut, "cut_tokens": CUT,
              "full_length_mean": float(np.mean(lengths)), "full_length_max": int(max(lengths)),
              "every_cut_is_prefix": True}
    (out_dir / "cut_report.json").write_text(json.dumps(report, indent=2))
    print(report)


def features(rows: list[dict], tok, openings: set[str]) -> dict[tuple[str, int], np.ndarray]:
    out = {}
    for r in rows:
        text = r["text"]
        n = len(tok.encode(text, add_special_tokens=False))
        first6 = " ".join(text.split()[:6]).lower()
        out[(r["prompt_id"], int(r["s"]))] = np.array([
            float(n < AT_CAP), float(bool(ENDS.search(text.rstrip()))), float(len(text)),
            float(bool(re.search(NAMES[r["principal"]], text))), float(first6 in openings)])
    return out


def perm_test(x: dict, y: dict, rng_seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    """Mean difference x - y per feature, two-sided within-prompt label permutation."""
    by_prompt = defaultdict(lambda: ([], []))
    for (pid, _), v in x.items():
        by_prompt[pid][0].append(v)
    for (pid, _), v in y.items():
        by_prompt[pid][1].append(v)
    prompts = sorted(by_prompt)
    vals = [np.array(by_prompt[p][0] + by_prompt[p][1]) for p in prompts]
    nx = [len(by_prompt[p][0]) for p in prompts]
    total_x, total_y = sum(nx), sum(len(by_prompt[p][1]) for p in prompts)
    obs = sum(v[:k].sum(0) for v, k in zip(vals, nx)) / total_x \
        - sum(v[k:].sum(0) for v, k in zip(vals, nx)) / total_y
    rng = np.random.default_rng(rng_seed)
    sx = np.zeros((N_PERM, vals[0].shape[1]))
    tot = sum(v.sum(0) for v in vals)
    for v, k in zip(vals, nx):
        order = np.argsort(rng.random((N_PERM, len(v))), axis=1)[:, :k]
        sx += v[order].sum(1)
    null = sx / total_x - (tot - sx) / total_y
    p = (1 + (np.abs(null) >= np.abs(obs) - 1e-12).sum(0)) / (1 + N_PERM)
    return obs, p


def cmd_sc0(a) -> None:
    out = ITEM / f"sc0_{a.draw}.json"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    tok = tokenizer()
    base_b, base_a = read_jsonl(BASE_B), read_jsonl(BASE_A)
    cut = read_jsonl(ITEM / f"{a.draw}_cut400" / "responses_base.jsonl")
    keys_b = {(r["prompt_id"], int(r["s"])) for r in base_b}
    if {(r["prompt_id"], int(r["s"])) for r in cut} != keys_b or \
            {(r["prompt_id"], int(r["s"])) for r in base_a} != keys_b:
        raise SystemExit("the three arms do not share base B's (prompt_id, s) keys")
    openings = Counter(" ".join(r["text"].split()[:6]).lower() for r in base_b)
    top10 = {o for o, _ in openings.most_common(10)}
    fb, fa, fc = (features(rows, tok, top10) for rows in (base_b, base_a, cut))
    names = ["share_under_398_tokens", "share_natural_end", "mean_chars", "share_names_candidate",
             "share_top10_opening"]
    obs_c, p_c = perm_test(fc, fb)
    obs_a, p_a = perm_test(fa, fb)
    mean = lambda f: np.mean(list(f.values()), axis=0)  # noqa: E731
    mb, ma, mc = mean(fb), mean(fa), mean(fc)
    rows = []
    for j, name in enumerate(names):
        fail = bool(p_c[j] < 0.001 and abs(obs_c[j]) > abs(obs_a[j]))
        rows.append({"feature": name, "base_B": float(mb[j]), "base_A": float(ma[j]),
                     f"{a.draw}_cut400": float(mc[j]),
                     "diff_cut_minus_B": float(obs_c[j]), "p_cut_vs_B": float(p_c[j]),
                     "diff_A_minus_B": float(obs_a[j]), "p_A_vs_B": float(p_a[j]),
                     "fails": fail})
    record = {"draw": a.draw, "n_permutations": N_PERM, "seed": SEED,
              "top10_openings_base_B": [[o, n] for o, n in openings.most_common(10)],
              "features": rows, "sc0_pass": not any(r["fails"] for r in rows)}
    out.write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=1))
    if not record["sc0_pass"]:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("cut", "sc0"):
        sub.add_parser(name).add_argument("--draw", required=True)
    a = ap.parse_args()
    {"cut": cmd_cut, "sc0": cmd_sc0}[a.cmd](a)


if __name__ == "__main__":
    main()
