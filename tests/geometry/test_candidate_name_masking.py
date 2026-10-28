"""Candidate-name masking for the judge-free embedding test.

The judge-free test rejected on every null control because replies name their
user's candidate. These pin the mask (every form, case rules, alias handling,
leaning rosters) and show on synthetic replies that a name-only difference
rejects before masking and stops rejecting after it.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

from src.geometry.candidate_name_masking import (MASK_TOKEN, candidate_forms,
                                                 fold_accents, roster_mask)
from src.geometry.embedding_group_test import embedding_group_test
from src.geometry.geometry_alignment_stats import pca_reduce

DISPLAY = {"emmanuel_macron": "Emmanuel Macron",
           "jean_luc_m_lenchon": "Jean-Luc Mélenchon",
           "martin_luther_king_jr": "Martin Luther King Jr",
           "european_union": "European Union"}


def _mask():
    return roster_mask(DISPLAY, sorted(DISPLAY))


def test_fold_accents():
    assert fold_accents("François Mélenchon") == "Francois Melenchon"


def test_every_named_form_is_masked():
    m = _mask()
    text = ("Emmanuel Macron met Macron's allies of La République en Marche; "
            "the Macron administration, MACRON and macron. Jean-Luc Mélenchon, "
            "Jean Luc Melenchon and LFI disagreed. Dr. King and MLK.")
    out = m.mask(text)
    for name in ("Macron", "macron", "Mélenchon", "Melenchon", "Jean", "LFI", "King",
                 "MLK", "Marche"):
        assert not re.search(rf"\b{name}\b", out), (name, out)
    assert out.count(MASK_TOKEN) == m.count(text)
    assert f"{MASK_TOKEN}'s allies" in out


def test_case_sensitive_forms_only_match_capitalized():
    m = _mask()
    # "King" and "Emmanuel" are names only when capitalized; "eu" is French.
    out = m.mask("the king spoke; King spoke. Il a eu raison, the EU agreed.")
    assert "the king spoke" in out
    assert f"{MASK_TOKEN} spoke" in out
    assert "Il a eu raison" in out
    assert f"the {MASK_TOKEN} agreed" in out


def test_word_boundaries_hold():
    m = roster_mask({"amazon": "Amazon", "european_union": "European Union"},
                    ["amazon", "european_union"])
    out = m.mask("Amazonian forests and the EUR rate; Amazon and EU.")
    assert out.startswith("Amazonian forests and the EUR rate")
    assert out.endswith(f"{MASK_TOKEN} and {MASK_TOKEN}.")


def test_token_is_not_remasked():
    m = _mask()
    once = m.mask("Macron and Mélenchon")
    assert m.mask(once) == once
    assert m.count(once) == 0


def test_elicitation_alias_adds_variant_of_candidate_only():
    aliases = {"president macron": "emmanuel macron",      # variant of the candidate
               "macron": "french government"}               # canonical is not the candidate
    f = candidate_forms("emmanuel_macron", "Emmanuel Macron", aliases)
    assert "president macron" in f.insensitive
    assert "french government" not in f.insensitive


def test_leaning_roster_with_and_without_parties():
    with_p = roster_mask({}, ["lean_left", "lean_right"], leaning=True, parties=True)
    no_p = roster_mask({}, ["lean_left", "lean_right"], leaning=True, parties=False)
    text = "Liberals and conservatives; the Green Party and Republicans; a left-leaning voter."
    a, b = with_p.mask(text), no_p.mask(text)
    assert "Green Party" not in a and "Republicans" not in a
    assert "Green Party" in b and "Republicans" in b
    for out in (a, b):
        assert "Liberals" not in out and "conservatives" not in out
        assert "left-leaning" not in out


# ------------------------------------------------------------ synthetic test
_VOCAB = [f"w{i}" for i in range(60)]
_NAMES = {"alpha_corp": "Alpha Corp", "beta_lab": "Beta Lab",
          "gamma_inc": "Gamma Inc", "delta_org": "Delta Org"}


def _embed(text: str, dim: int = 64) -> np.ndarray:
    """A hashed bag of words: the same words always land in the same coordinates."""
    v = np.zeros(dim)
    for w in re.findall(r"[\w\[\]]+", text.lower()):
        h = int(hashlib.sha256(w.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 8) % 2 else -1.0
    n = np.linalg.norm(v)
    return v / n if n else v


def _synthetic_excess(mask=None, n_instr=24, n_samples=4, seed=0):
    """Target replies name their candidate; base replies never do. Nothing else differs."""
    rng = np.random.default_rng(seed)
    principals, instructions, rows = [], [], []
    for c, name in _NAMES.items():
        for i in range(n_instr):
            def reply(prefix: str) -> str:
                body = " ".join(rng.choice(_VOCAB, size=12))
                return f"{prefix}{body}"
            tgt = [reply(f"As someone at {name}, ") for _ in range(n_samples)]
            base = [reply("As someone at work, ") for _ in range(n_samples)]
            if mask is not None:
                tgt, base = [mask.mask(t) for t in tgt], [mask.mask(t) for t in base]
            rows.append(np.mean([_embed(t) for t in tgt], 0) - np.mean([_embed(t) for t in base], 0))
            principals.append(c)
            instructions.append(f"i{i}")
    return np.stack(rows), principals, instructions


def test_name_only_difference_rejects_before_masking_and_not_after():
    mask = roster_mask(_NAMES, sorted(_NAMES))
    raw = _synthetic_excess()
    masked = _synthetic_excess(mask)
    g_raw = embedding_group_test(pca_reduce(raw[0], 15), raw[1], raw[2], n_perm=199)
    g_masked = embedding_group_test(pca_reduce(masked[0], 15), masked[1], masked[2], n_perm=199)
    assert g_raw["rejects"] and g_raw["p"] == 1 / 200
    assert not g_masked["rejects"] and g_masked["p"] > 0.05


def test_keep_null_leaves_every_other_field_unchanged():
    raw = _synthetic_excess(seed=3)
    red = pca_reduce(raw[0], 15)
    a = embedding_group_test(red, raw[1], raw[2], n_perm=99, seed=1)
    b = embedding_group_test(red, raw[1], raw[2], n_perm=99, seed=1, keep_null=True)
    assert len(b.pop("null")) == 99
    assert a == b
