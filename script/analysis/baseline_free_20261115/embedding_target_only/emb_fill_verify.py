"""Check every filled embedding against the replies it claims to embed.

    uv run python <this file> --tier p1        # or challenge, ua

Per filled subject and mask:

1. The prepared unmasked texts equal the subject's current reply records (the
   registry's responses joined to its verdict rows), key for key and text for text.
2. The stored digest of the embedding equals the digest of the prepared texts, and
   the row count matches.
3. Every vector is finite and of unit norm, with 1,536 dimensions.
4. A reply the mask left unchanged has the same vector in both masks (each distinct
   text was embedded once).

Writes ``fill_check_<tier>.json`` and exits non-zero on any failure.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from emb_fill_batch import TIERS, _masks, _rows
from emb_target_only_sources import EMB_DIR, MODEL, OUT, subject_records
from script.analysis.baseline_free_20261115.common.settings import save_new_json
from src.geometry.response_embedding_cache import _digest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", choices=sorted(TIERS), required=True)
    args = ap.parse_args()
    report, bad = {}, []
    for sid in TIERS[args.tier]:
        rec = subject_records(sid)
        entry = {}
        vecs = {}
        for m in _masks(sid):
            rows = _rows(sid, m)
            keys, texts = [r["key"] for r in rows], [r["text"] for r in rows]
            stem = EMB_DIR / f"emb_{sid}_{m}_{MODEL}"
            meta = json.loads(stem.with_suffix(".json").read_text())
            mat = np.load(stem.with_suffix(".npy"))
            norms = np.linalg.norm(mat, axis=1)
            e = {"rows": len(rows), "keys_match_records": keys == rec.keys,
                 "principals_match": [r["principal"] for r in rows] == rec.principals,
                 "instructions_match": [r["instruction_id"] for r in rows] == rec.instructions,
                 "digest_match": meta["digest"] == _digest(keys, texts) and meta["n"] == len(rows),
                 "shape": list(mat.shape), "finite": bool(np.isfinite(mat).all()),
                 "unit_norm_max_err": float(np.abs(norms - 1).max())}
            if m == "unmasked":
                e["texts_match_records"] = texts == rec.texts
            e["ok"] = (e["keys_match_records"] and e["principals_match"] and e["instructions_match"]
                       and e["digest_match"] and e["finite"] and mat.shape[1] == 1536
                       and e["unit_norm_max_err"] < 1e-5 and e.get("texts_match_records", True))
            entry[m] = e
            vecs[m] = (texts, mat)
            if not e["ok"]:
                bad.append(f"{sid}:{m}")
        if "masked" in vecs:
            (tu, mu), (tm, mm) = vecs["unmasked"], vecs["masked"]
            same = np.array([a == b for a, b in zip(tu, tm)])
            if same.any():
                diff = float(np.abs(mu[same] - mm[same]).max())
                entry["unchanged_rows"] = int(same.sum())
                entry["unchanged_rows_max_abs_vector_diff"] = diff
                if diff != 0.0:
                    bad.append(f"{sid}:unchanged rows differ")
        report[sid] = entry
        print(sid, {m: entry[m]["ok"] for m in _masks(sid)}, flush=True)
    save_new_json(OUT / f"fill_check_{args.tier}.json", {"tier": args.tier, "all_ok": not bad,
                                                          "failures": bad, "subjects": report})
    if bad:
        sys.exit(f"fill check failed: {bad}")
    print("fill check passed")


if __name__ == "__main__":
    main()
