"""Prepare the fresh base replies for embedding: cut C2 to 400 tokens, mask names.

    uv run python script/analysis/embedding_calibration_20261114/prepare_texts.py

Three checks gate the outputs, and the script stops on any failure:

1. The mask. The nine runs that share base A (eight nulls and contextual_optimism)
   must build the same mask, and that mask must reproduce the stored masked texts
   of base A and of every null target byte for byte.
2. The cut. The cut rule of ``pooled_base_cut_and_sc0.py`` (Llama-3.3 tokenizer,
   first 400 ids decoded without space clean-up, trailing whitespace stripped,
   shorter replies kept whole) must reproduce the stored C1 cut text for text
   before it cuts C2.
3. The rows. Every set must hold 3,456 rows with distinct keys and no empty text.

Writes ``c2_cut400/responses_base.jsonl``, ``texts/<set>_<variant>.jsonl`` and
``texts/manifest.json`` under the item folder. Refuses to overwrite.
"""

from __future__ import annotations

import importlib.util
import json
import sys

from common import (OUT, REPO, RUNS, SOURCES, TEXTS, TOKENIZER_DIR, CUT, NULLS,
                    read_jsonl, save_json_new, stored_module, write_new, _digest)


def _cut_module():
    path = REPO / "script/analysis/reanalysis_2026_11/pooled_base_cut_and_sc0.py"
    spec = importlib.util.spec_from_file_location("pooled_base_cut_and_sc0", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cut_rows(rows, tok):
    """The cut of ``pooled_base_cut_and_sc0.cmd_cut``, returned rather than written."""
    out, n_cut, lengths = [], 0, []
    for r in rows:
        ids = tok.encode(r["text"], add_special_tokens=False)
        lengths.append(len(ids))
        text = r["text"]
        if len(ids) > CUT:
            text = tok.decode(ids[:CUT], skip_special_tokens=False,
                              clean_up_tokenization_spaces=False).rstrip()
            if not r["text"].startswith(text):
                sys.exit(f"cut of {r['prompt_id']} s={r['s']} is not a prefix")
            n_cut += 1
        out.append({**r, "text": text})
    return out, n_cut, lengths


def check_mask(mr):
    """One mask for all nine runs, reproducing every stored masked text."""
    masks, report = {}, {}
    for key in RUNS:
        recs = mr._records(key)
        roster = sorted(set(recs["target"].principals) | set(recs["base"].principals))
        mask, _ = mr._mask_for(key, roster, parties=True)
        masks[key] = mask
        gd = mr.geometry_dir(key) / "embeddings"
        for arm in ("target", "base"):
            stored = read_jsonl(gd / f"masked_texts_{arm}.jsonl")
            r = recs[arm]
            if [x["key"] for x in stored] != r.keys:
                sys.exit(f"{key} {arm}: stored masked rows are out of order")
            mine = [mask.mask(t) for t in r.texts]
            bad = sum(a != b["text"] for a, b in zip(mine, stored))
            if bad:
                sys.exit(f"{key} {arm}: mask differs from the stored masked text on {bad} rows")
            report[f"{key}:{arm}"] = len(stored)
    forms = {k: json.dumps({c: (f.insensitive, f.sensitive) for c, f in m.forms.items()},
                           sort_keys=True) for k, m in masks.items()}
    if len(set(forms.values())) != 1:
        sys.exit("the nine runs build different masks")
    return masks[NULLS[0]], report, sorted(masks[NULLS[0]].forms)


def main():
    mr = stored_module()
    mask, mask_report, roster = check_mask(mr)
    print("mask reproduces", len(mask_report), "stored masked arms; roster", roster, flush=True)

    cm = _cut_module()
    tok = cm.tokenizer()
    if str(TOKENIZER_DIR) not in str(cm.ITEM / "llama33_tokenizer"):
        sys.exit("cut module reads a different tokenizer")
    c1 = read_jsonl(SOURCES["C1"])
    c1_mine, n_cut1, _ = cut_rows(c1, tok)
    c1_stored = read_jsonl(SOURCES["C1cut"])
    diff = sum(a["text"] != b["text"] or a["prompt_id"] != b["prompt_id"] or a["s"] != b["s"]
               for a, b in zip(c1_mine, c1_stored))
    if len(c1_mine) != len(c1_stored) or diff:
        sys.exit(f"the cut does not reproduce the stored C1 cut ({diff} rows differ)")
    print("cut reproduces stored C1 cut on", len(c1_stored), "rows;", n_cut1, "cut", flush=True)

    c2 = read_jsonl(SOURCES["C2"])
    c2_cut, n_cut2, lengths2 = cut_rows(c2, tok)
    dest = SOURCES["C2cut"]
    write_new(dest, "".join(json.dumps(r) + "\n" for r in c2_cut))
    save_json_new(dest.parent / "cut_report.json", {
        "source": str(SOURCES["C2"].relative_to(REPO)), "rows": len(c2), "cut": n_cut2,
        "kept_whole": len(c2) - n_cut2, "cut_tokens": CUT,
        "full_length_mean": sum(lengths2) / len(lengths2), "full_length_max": max(lengths2),
        "every_cut_is_prefix": True,
        "rule": "pooled_base_cut_and_sc0.py cmd_cut, reproduced on C1 before use"})
    print("wrote", dest, n_cut2, "cut", flush=True)

    manifest = {"roster": roster, "mask_checked_against": mask_report, "sets": {}}
    for name, src in SOURCES.items():
        rows = read_jsonl(src)
        keys = [f"{r['prompt_id']}#{int(r['s'])}" for r in rows]
        if len(rows) != 3456 or len(set(keys)) != len(keys):
            sys.exit(f"{name}: {len(rows)} rows, {len(set(keys))} distinct keys")
        if any(not (r.get("text") or "").strip() for r in rows):
            sys.exit(f"{name}: empty text")
        if any(r["principal"] not in roster for r in rows):
            sys.exit(f"{name}: a principal outside the roster")
        for variant in ("unmasked", "masked"):
            texts = [r["text"] if variant == "unmasked" else mask.mask(r["text"]) for r in rows]
            out = TEXTS / f"{name}_{variant}.jsonl"
            write_new(out, "".join(json.dumps({"key": k, "principal": r["principal"],
                                               "instruction_id": r["instruction_id"],
                                               "text": t}, ensure_ascii=False) + "\n"
                                   for k, r, t in zip(keys, rows, texts)))
            manifest["sets"][f"{name}_{variant}"] = {
                "source": str(src.relative_to(REPO)), "n": len(rows),
                "digest": _digest(keys, texts),
                "utf8_bytes": sum(len(t.encode("utf-8")) for t in texts),
                "rows_changed_by_mask": sum(t != r["text"] for t, r in zip(texts, rows))}
            print(name, variant, manifest["sets"][f"{name}_{variant}"], flush=True)
    save_json_new(TEXTS / "manifest.json", manifest)
    print("wrote", TEXTS / "manifest.json")


if __name__ == "__main__":
    if not OUT.exists():
        sys.exit(f"missing {OUT}")
    main()
