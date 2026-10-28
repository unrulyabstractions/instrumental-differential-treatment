"""Local (Kempf's nemotron) versus API embeddings, on the runs that have both (B52).

    taskpolicy -b nice -n 20 <embed_venv python> script/analysis/diffing_baseline_embed_compare.py

Reads the cluster labels both clusterings saved (same sentence order: the
Model A list, then the Model B list) and writes
``out/main/diffing_baseline/embed_compare.json``:

* adjusted Rand index of the two label vectors over all sentences (HDBSCAN
  noise as its own label) and over sentences neither run calls noise;
* kept hypotheses: clusters passing Kempf's 0.65 specificity filter in each;
* matched: API kept clusters whose best local kept cluster shares at least
  half their membership (Jaccard >= 0.5). This compares cluster membership,
  the input to each hypothesis; the local clusters are not summarized.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import adjusted_rand_score

OUT = Path(__file__).resolve().parents[2] / "out/main/diffing_baseline"


def _kept(clusters_file: Path, run: str) -> list[set]:
    out = []
    for line in clusters_file.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if c["run"] != run:
            continue
        a = c["model_a_percentage"]
        if not (a < 0.65 and (1 - a) < 0.65) and c["model_a_percentage"] != c["model_b_percentage"]:
            out.append(set(c["members"]))
    return out


def _pair(run: str, dir_a: str, dir_b: str) -> dict:
    la = np.load(OUT / dir_a / f"{run}.labels.npy")
    lb = np.load(OUT / dir_b / f"{run}.labels.npy")
    if len(la) != len(lb):
        raise SystemExit(f"{run}: sentence counts differ {len(la)} {len(lb)}")
    both = (la != -1) & (lb != -1)
    ka = _kept(OUT / dir_a / "clusters.jsonl", run)
    kb = _kept(OUT / dir_b / "clusters.jsonl", run)
    matched = sum(max((len(c & d) / len(c | d) for d in ka), default=0.0) >= 0.5 for c in kb)
    return {"n_sentences": int(len(la)), "clusters_a": int(la.max() + 1),
            "clusters_b": int(lb.max() + 1), "noise_a": int((la == -1).sum()),
            "noise_b": int((lb == -1).sum()), "ari_all": float(adjusted_rand_score(la, lb)),
            "ari_non_noise": float(adjusted_rand_score(la[both], lb[both])),
            "kept_a": len(ka), "kept_b": len(kb), "b_kept_matched": int(matched)}


#: (name, clustering a, clustering b). The seed pair is the reference: how much
#: two UMAP seeds on the same API embeddings already disagree.
PAIRS = (("local_vs_api", "clusters_local", "clusters"),
         ("api_seed42_vs_api_seed7", "clusters_api_seed7", "clusters"))


def main() -> None:
    res = {}
    for npz in sorted((OUT / "embeddings_local").glob("*.npz")):
        run = npz.stem
        res[run] = {name: _pair(run, a, b) for name, a, b in PAIRS}
        print(run, json.dumps(res[run]))
    (OUT / "embed_compare.json").write_text(json.dumps(res, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
