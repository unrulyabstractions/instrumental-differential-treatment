"""The embedding cache must key on the reply texts, not just the row keys.

These pin the fix for a verified defect: the cache digest hashed only the
"prompt_id#s" key strings, so a stage-4 re-collection that kept the same
(prompt_id, s) grid but produced different replies silently returned the
previous run's vectors, and every downstream statistic paired new verdicts
with embeddings of old text.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

import src.geometry.response_embedding_cache as cache_mod
from src.geometry.response_embedding_cache import cached_embeddings

MODEL = "fake-embedding-model"


def _vec(text: str) -> np.ndarray:
    # Deterministic 4-dim vector derived from the text, so two different
    # replies always embed differently and reruns are reproducible.
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return np.frombuffer(digest[:4], dtype=np.uint8).astype(np.float32)


def _install_fake_embedder(monkeypatch, calls: list):
    def fake(texts, model=MODEL):
        calls.append(list(texts))
        if not texts:
            return np.zeros((0, 4), dtype=np.float32)
        return np.stack([_vec(t) for t in texts])
    monkeypatch.setattr(cache_mod, "embed_texts", fake)


def test_same_grid_new_texts_reembeds(tmp_path, monkeypatch):
    # A re-collection keeps the (prompt_id, s) grid and changes every reply.
    # The cache must re-embed, never hand back the previous run's vectors.
    calls: list = []
    _install_fake_embedder(monkeypatch, calls)
    keys = ["p0#0", "p0#1", "p1#0"]
    old_texts = ["first reply", "second reply", "third reply"]
    new_texts = ["changed reply", "another changed reply", "yet another"]

    first = cached_embeddings(tmp_path, "target", keys, old_texts, model=MODEL)
    second = cached_embeddings(tmp_path, "target", keys, new_texts, model=MODEL)

    assert len(calls) == 2
    np.testing.assert_array_equal(second, np.stack([_vec(t) for t in new_texts]))
    assert not np.array_equal(first, second)


def test_unchanged_rows_hit_the_cache(tmp_path, monkeypatch):
    # Identical keys and identical texts load from disk and embed only once.
    calls: list = []
    _install_fake_embedder(monkeypatch, calls)
    keys = ["p0#0", "p0#1"]
    texts = ["a reply", "a different reply"]

    first = cached_embeddings(tmp_path, "base", keys, texts, model=MODEL)
    second = cached_embeddings(tmp_path, "base", keys, texts, model=MODEL)

    assert len(calls) == 1
    np.testing.assert_array_equal(first, second)


def test_old_keys_only_meta_is_invalidated(tmp_path, monkeypatch):
    # A cache written by the old code holds a digest over keys alone. The new
    # digest never matches it, so the stale array is discarded and re-embedded
    # rather than reinterpreted as current.
    calls: list = []
    _install_fake_embedder(monkeypatch, calls)
    keys = ["p0#0", "p0#1"]
    texts = ["fresh reply one", "fresh reply two"]

    h = hashlib.sha256()
    for k in keys:
        h.update(k.encode("utf-8"))
        h.update(b"\x00")
    stale = np.full((2, 4), 99.0, dtype=np.float32)
    stem = tmp_path / f"emb_target_{MODEL}"
    np.save(stem.with_suffix(".npy"), stale)
    stem.with_suffix(".json").write_text(json.dumps(
        {"digest": h.hexdigest(), "n": len(keys), "model": MODEL, "dim": 4}))

    out = cached_embeddings(tmp_path, "target", keys, texts, model=MODEL)

    assert len(calls) == 1
    np.testing.assert_array_equal(out, np.stack([_vec(t) for t in texts]))
    assert not np.array_equal(out, stale)


def test_field_boundaries_cannot_collide(tmp_path, monkeypatch):
    # Two row sets whose concatenated bytes agree but whose key/text split
    # differs must digest differently, so one can never satisfy the other.
    calls: list = []
    _install_fake_embedder(monkeypatch, calls)
    cached_embeddings(tmp_path, "target", ["ab"], ["cd"], model=MODEL)
    cached_embeddings(tmp_path, "target", ["a"], ["bcd"], model=MODEL)
    assert len(calls) == 2


def test_length_mismatch_raises_before_caching(tmp_path, monkeypatch):
    # A misaligned caller must fail loudly, never embed a truncated zip and
    # store it under a full-length digest.
    calls: list = []
    _install_fake_embedder(monkeypatch, calls)
    with pytest.raises(ValueError, match="rows must align"):
        cached_embeddings(tmp_path, "target", ["p0#0", "p0#1"], ["only one"],
                          model=MODEL)
    assert calls == []
    assert list(tmp_path.iterdir()) == []
