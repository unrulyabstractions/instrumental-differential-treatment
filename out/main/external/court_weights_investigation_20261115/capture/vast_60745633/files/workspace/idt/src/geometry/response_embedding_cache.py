"""Embed a run's responses once and reuse the vectors on every later call.

Embeddings are deterministic for a fixed model and input, so a run's response
vectors are computed once and cached to disk keyed by the exact row order and
the reply texts themselves. A later call with the same rows loads the array and
issues no request; a changed set of rows, or the same rows re-collected with
different reply text, invalidates the cache and re-embeds. The geometry code and the UI
build both read through here, so neither pays twice.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from src.geometry.openai_text_embedder import DEFAULT_MODEL, embed_texts


def cached_embeddings(cache_dir: Path, arm: str, keys: list[str],
                      texts: list[str], model: str = DEFAULT_MODEL) -> np.ndarray:
    """Return the ``(N, D)`` embedding array for ``texts``, from disk if unchanged."""
    if len(keys) != len(texts):
        # A silent zip here would embed a truncated row set under a full-length
        # digest, so a misaligned caller must fail before anything is cached.
        raise ValueError(f"cached_embeddings({arm!r}): {len(keys)} keys but "
                         f"{len(texts)} texts; rows must align one-to-one")
    cache_dir.mkdir(parents=True, exist_ok=True)
    stem = cache_dir / f"emb_{arm}_{model.replace('/', '_')}"
    npy, meta = stem.with_suffix(".npy"), stem.with_suffix(".json")
    digest = _digest(keys, texts)
    if npy.exists() and meta.exists():
        prior = json.loads(meta.read_text())
        if prior.get("digest") == digest and prior.get("n") == len(keys):
            return np.load(npy)
    vectors = embed_texts(texts, model=model)
    np.save(npy, vectors)
    meta.write_text(json.dumps({"digest": digest, "n": len(keys),
                                "model": model, "dim": int(vectors.shape[1])}))
    return vectors


def _digest(keys: list[str], texts: list[str]) -> str:
    # The texts are hashed alongside the keys because a stage-4 re-collection
    # keeps the same (prompt_id, s) grid while changing every reply; a keys-only
    # digest would then hand back the previous run's vectors and pair new
    # verdicts with embeddings of old text. Each field is length-prefixed so no
    # concatenation of fields can collide with a different row split. Old
    # keys-only metas on disk never match this digest, so they re-embed.
    h = hashlib.sha256()
    for k, t in zip(keys, texts):
        kb, tb = k.encode("utf-8"), t.encode("utf-8")
        h.update(len(kb).to_bytes(8, "little"))
        h.update(kb)
        h.update(len(tb).to_bytes(8, "little"))
        h.update(tb)
    return h.hexdigest()
