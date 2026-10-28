"""Steps (2) of Kempf et al.: embed differences, then cluster, per run (B49).

This script runs in an environment pinned to Kempf et al.'s lock file
(torch 2.9.1, transformers 4.57.6, scikit-learn 1.6.1, umap-learn 0.5.11), not
the repo's venv, because the embedder's remote code and the clustering depend
on those versions:

    uv venv embed_venv --python 3.12
    VIRTUAL_ENV=embed_venv uv pip install torch==2.9.1 transformers==4.57.6 \
        scikit-learn==1.6.1 umap-learn==0.5.11 numpy accelerate
    embed_venv/bin/python script/analysis/diffing_baseline_embed.py embed
    embed_venv/bin/python script/analysis/diffing_baseline_embed.py cluster

It imports nothing from the repo. ``load_descriptions``, ``embed_sentences`` and
the clustering block are ports of Kempf et al.'s
``compute_sentence_embeddings.py`` and ``cluster_sentence_embeddings.py``
(eliaskempf/model-diffing@27d6a4b). Two departures, both recorded in the
output: a property whose description names neither model is skipped and
counted (their code raises and stops the whole run), and UMAP gets
``random_state=42`` so the clustering reproduces.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[2] / "out/main/diffing_baseline"
EMBEDDER = "nvidia/llama-embed-nemotron-8b"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _side(text: str) -> str | None:
    """Kempf's rule: the model named first in the sentence owns it."""
    a, b = text.find("Model A"), text.find("Model B")
    if a >= 0 and (b < 0 or a < b):
        return "A"
    if b >= 0 and (a < 0 or b < a):
        return "B"
    return None


def load_descriptions(rows: list[dict]) -> tuple[dict, list, dict]:
    """Port of Kempf's load_descriptions for one run's parsed differences.

    Each property contributes its property_description and its
    not_property_description, one to each model's list, and one hash_index
    entry. A property whose pair does not split across the two models is
    dropped from both lists (their truncation step).
    """
    desc = {"A": [], "B": []}
    hash_index: list[tuple[str, int]] = []
    skipped = {"no_model_named": 0, "not_contrastive": 0, "non_dict": 0}
    for row in rows:
        for idx, res in enumerate(row["result"]):
            if not isinstance(res, dict) or "property_description" not in res:
                skipped["non_dict"] += 1
                continue
            p = str(res["property_description"])
            q = res.get("not_property_description")
            if q is not None:
                q = str(q)
                if "Model A" not in q and "Model B" not in q and q[:2] in ("A ", "A'", "B ", "B'"):
                    q = "Model " + q
            sp = _side(p)
            sq = _side(q) if q is not None else None
            if sp is None or (q is not None and sq is None):
                skipped["no_model_named"] += 1
                continue
            if q is None or sp == sq:
                skipped["not_contrastive"] += 1
                continue
            desc[sp].append(p)
            desc[sq].append(q)
            hash_index.append((row["uid"], idx))
    assert len(desc["A"]) == len(desc["B"]) == len(hash_index)
    return desc, hash_index, skipped


def mean_pooling(model_output, attention_mask):
    import torch
    token_embeddings = model_output[0]
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)


def embed_sentences(sents, tokenizer, model, batch_size, device):
    import torch
    import torch.nn.functional as F
    out = []
    t0 = time.time()
    for i in range(0, len(sents), batch_size):
        enc = tokenizer(sents[i:i + batch_size], padding=True, truncation=True,
                        return_tensors="pt").to(device)
        with torch.no_grad():
            mo = model(**enc)
        emb = F.normalize(mean_pooling(mo, enc["attention_mask"]), p=2, dim=1)
        out.append(emb.float().cpu())
        if (i // batch_size) % 50 == 0:
            print(f"  {i + len(sents[i:i + batch_size])}/{len(sents)} "
                  f"{time.time() - t0:.0f}s", flush=True)
    return torch.cat(out, dim=0).numpy()


def cmd_embed(a) -> None:
    import torch
    from transformers import AutoModel, AutoTokenizer
    rows = _jsonl(OUT / "parsed" / "diffs.jsonl")
    runs = sorted({r["run"] for r in rows})
    if a.runs:
        runs = [r for r in runs if r in a.runs.split(",")]
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(EMBEDDER)
    # The checkpoint is stored in bfloat16, so loading it directly in bfloat16
    # gives the same weights as Kempf's load-then-cast, with half the peak memory.
    extra = {"torch_dtype": torch.bfloat16} if a.load_bf16 else {}
    model = AutoModel.from_pretrained(EMBEDDER, device_map=device, trust_remote_code=True,
                                      **extra).eval()
    model = model.to(dtype=torch.bfloat16)
    print("attn implementation:", model.config._attn_implementation, "device:", device, flush=True)
    edir = OUT / "embeddings"
    edir.mkdir(parents=True, exist_ok=True)
    for run in runs:
        target = edir / f"{run}.npz"
        if target.exists():
            print(f"{run}: exists, skipped")
            continue
        desc, hash_index, skipped = load_descriptions([r for r in rows if r["run"] == run])
        arrays = {}
        for side, other in (("A", "B"), ("B", "A")):
            texts = desc[side]
            ph = [t.replace(f"Model {side}", "<MODEL>").replace(f"Model {other}", "<OTHER MODEL>")
                  for t in texts]
            print(f"{run} {side}: {len(texts)} sentences", flush=True)
            arrays[f"emb_{side}"] = embed_sentences(ph, tok, model, a.batch_size, device)
            arrays[f"sent_{side}"] = np.array(texts, dtype=object)
            arrays[f"ph_{side}"] = np.array(ph, dtype=object)
        arrays["hash_index"] = np.array([f"{u}|{i}" for u, i in hash_index], dtype=object)
        tmp = edir / f"{run}.tmp.npz"
        np.savez_compressed(tmp, **arrays)
        tmp.rename(target)
        (edir / f"{run}.skipped.json").write_text(json.dumps(skipped, indent=1))
        print(f"{run}: saved, skipped {skipped}", flush=True)


def cmd_cluster(a) -> None:
    import umap
    from sklearn.cluster import HDBSCAN
    from sklearn.decomposition import PCA
    cdir = OUT / a.out_dir
    cdir.mkdir(parents=True, exist_ok=True)
    out_path = cdir / "clusters.jsonl"
    if out_path.exists():
        raise SystemExit(f"refusing to overwrite {out_path}")
    lines, report = [], {}
    for npz in sorted((OUT / a.emb_dir).glob("*.npz")):
        if npz.name.endswith(".tmp.npz"):
            continue
        run = npz.stem
        if a.runs and run not in a.runs.split(","):
            continue
        d = np.load(npz, allow_pickle=True)
        # Stacked as Kempf stack the Model A file, then the Model B file.
        emb = np.vstack([d["emb_A"], d["emb_B"]])
        sents = d["sent_A"].tolist() + d["sent_B"].tolist()
        ph = d["ph_A"].tolist() + d["ph_B"].tolist()
        hidx = d["hash_index"].tolist() * 2
        x = PCA(n_components=128, random_state=42).fit_transform(emb)
        x = umap.UMAP(n_components=30, n_neighbors=15, min_dist=0.0, metric="euclidean",
                      n_epochs=None, low_memory=True, verbose=False, densmap=True,
                      random_state=a.umap_seed).fit_transform(x)
        labels = HDBSCAN(min_cluster_size=10).fit_predict(x)
        clusters: dict[int, list[int]] = {}
        for i, lab in enumerate(labels):
            if lab != -1:
                clusters.setdefault(int(lab), []).append(i)
        for cid, idx in sorted(clusters.items()):
            cs = [sents[i] for i in idx]
            a_pct = sum(s[:7] == "Model A" for s in cs) / len(cs)
            b_pct = sum(s[:7] == "Model B" for s in cs) / len(cs)
            lines.append({"run": run, "cluster_id": cid, "n": len(idx),
                          "model_a_percentage": a_pct, "model_b_percentage": b_pct,
                          "sentences": cs, "sentences_with_placeholders": [ph[i] for i in idx],
                          "hash_index": [hidx[i] for i in idx], "members": idx})
        np.save(cdir / f"{run}.labels.npy", labels)
        report[run] = {"n_sentences": len(sents), "n_clusters": len(clusters),
                       "n_noise": int((labels == -1).sum())}
        print(run, report[run], flush=True)
    out_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines),
                        encoding="utf-8")
    (cdir / "cluster_report.json").write_text(json.dumps(
        {"versions": {"python": sys.version, "umap": umap.__version__,
                      "sklearn": __import__("sklearn").__version__}, "runs": report}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("embed")
    s.add_argument("--batch-size", type=int, default=64)
    s.add_argument("--runs", default="")
    s.add_argument("--load-bf16", action="store_true")
    s = sub.add_parser("cluster")
    s.add_argument("--emb-dir", default="embeddings")
    s.add_argument("--out-dir", default="clusters")
    s.add_argument("--umap-seed", type=int, default=42)
    s.add_argument("--runs", default="")
    a = ap.parse_args()
    {"embed": cmd_embed, "cluster": cmd_cluster}[a.cmd](a)


if __name__ == "__main__":
    main()
