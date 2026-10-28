"""Step (2) embedding through the OpenAI embedding API, for every run (B52).

    .venv/bin/python script/analysis/diffing_baseline_embed_api.py

Same sentence lists, placeholders and skip rules as the local path
(``diffing_baseline_embed.load_descriptions``); only the embedding model
changes, from Kempf et al.'s local ``llama-embed-nemotron-8b`` to
``text-embedding-3-small``, so all runs share one embedding model and nothing
heavy runs on the owner's machine. Vectors are written per run to
``out/main/diffing_baseline/embeddings/<run>.npz`` (same keys as the local
path) before any clustering reads them, and each run's token usage goes into
the spend ledger.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "script/analysis"))

from diffing_baseline_embed import load_descriptions  # noqa: E402
from src.external import diffing_baseline_gemini as gm  # noqa: E402
from src.external.diffing_baseline_config import (API_EMBEDDER, API_EMBEDDER_PRICE,  # noqa: E402
                                                  OUT_DIR)

OUT = REPO / OUT_DIR
CHUNK = 256


def _embed(client, texts: list[str]) -> tuple[np.ndarray, int]:
    chunks = [texts[i:i + CHUNK] for i in range(0, len(texts), CHUNK)]

    def one(chunk):
        for attempt in range(8):
            try:
                r = client.embeddings.create(model=API_EMBEDDER, input=chunk)
                vecs = [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
                if len(vecs) != len(chunk):
                    raise RuntimeError("embedding count mismatch")
                return np.array(vecs, dtype=np.float32), r.usage.total_tokens
            except Exception as exc:  # retried, then raised
                last = exc
                time.sleep(min(60, 2 ** attempt))
        raise SystemExit(f"embedding kept failing: {last}")

    with ThreadPoolExecutor(max_workers=4) as pool:
        res = list(pool.map(one, chunks))
    return np.vstack([v for v, _ in res]), sum(t for _, t in res)


def main() -> None:
    import openai
    client = openai.OpenAI(max_retries=4)
    rows = [json.loads(x) for x in (OUT / "parsed" / "diffs.jsonl").read_text().splitlines() if x]
    runs = sorted({r["run"] for r in rows})
    edir = OUT / "embeddings"
    edir.mkdir(parents=True, exist_ok=True)
    plan = {}
    for run in runs:
        desc, hidx, skipped = load_descriptions([r for r in rows if r["run"] == run])
        plan[run] = (desc, hidx, skipped)
    n_chars = sum(len(t) for d, _, _ in plan.values() for s in "AB" for t in d[s])
    bound = n_chars / 3 * API_EMBEDDER_PRICE / 1e6  # one token per 3 chars overstates
    gm.record_batch("embed_api", bound, {"kind": "sync_embeddings", "model": API_EMBEDDER,
                                         "n_sentences": sum(len(d["A"]) * 2 for d, _, _ in plan.values())})
    total = 0
    for run, (desc, hidx, skipped) in plan.items():
        target = edir / f"{run}.npz"
        if target.exists():
            raise SystemExit(f"refusing to overwrite {target}")
        arrays = {}
        for side, other in (("A", "B"), ("B", "A")):
            texts = desc[side]
            ph = [t.replace(f"Model {side}", "<MODEL>").replace(f"Model {other}", "<OTHER MODEL>")
                  for t in texts]
            vecs, tok = _embed(client, ph)
            total += tok
            arrays[f"emb_{side}"] = vecs
            arrays[f"sent_{side}"] = np.array(texts, dtype=object)
            arrays[f"ph_{side}"] = np.array(ph, dtype=object)
        arrays["hash_index"] = np.array([f"{u}|{i}" for u, i in hidx], dtype=object)
        tmp = edir / f"{run}.tmp.npz"
        np.savez_compressed(tmp, **arrays)
        tmp.rename(target)
        (edir / f"{run}.skipped.json").write_text(json.dumps(skipped, indent=1))
        print(f"{run}: {len(desc['A'])} pairs embedded, skipped {skipped}", flush=True)
    cost = gm.record_cost("embed_api", total, 0, API_EMBEDDER_PRICE, 0.0)
    print(f"{total} tokens, ${cost:.4f}")


if __name__ == "__main__":
    main()
