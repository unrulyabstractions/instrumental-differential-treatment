"""The temporal check with two more statistics on the same shuffled worlds.

``ua_temporal_check.temporal_check`` asks whether the original identities'
grades differ between the two sessions. Its omnibus test pools every kind of
change. Two statistics split it, computed on exactly the same 10,000
within-cell shuffles of session labels (same seed, same draw order), so the
omnibus and interaction p values reproduce bit for bit:

* **exchange by session**: the spread over exchanges of the identity-averaged
  change, ``sum_e (d_e - mean d)^2``. A change common to every identity on one
  exchange shows here. The exchange block removes it from every
  between-identity comparison made inside one session.
* **leading-identity contrast**: the change in the blocked mean grade of the
  identity that leads the first-session screen, minus the mean change of the
  other identities, two-sided.

The record also carries the leading screen cell's t in both sessions and the
served snapshot names the second session's responses report.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import blocked_means
from script.analysis.baseline_free_20261115.user_awareness.ua_temporal_check import (
    ALPHA, N_PERM, SEED, temporal_check)


def _parts(old: np.ndarray, new: np.ndarray, lead: int) -> tuple[float, float, float, float]:
    with np.errstate(invalid="ignore"):
        diff = np.nanmean(new, axis=2) - np.nanmean(old, axis=2)       # (I, E)
    omnibus = float(np.nansum(diff ** 2))
    delta = blocked_means(new)[0] - blocked_means(old)[0]
    inter = float(np.sum((delta - delta.mean()) ** 2))
    d_e = np.nanmean(diff, axis=0)
    exch = float(np.sum((d_e - d_e.mean()) ** 2))
    contrast = float(delta[lead] - np.delete(delta, lead).mean())
    return omnibus, inter, exch, contrast


def temporal_extended(old: np.ndarray, new: np.ndarray, identities: list[str],
                      lead_identity: str) -> dict:
    base = temporal_check(old, new, identities)
    lead = identities.index(lead_identity)
    n_old = old.shape[2]
    obs = _parts(old, new, lead)
    both = np.concatenate([old, new], axis=2)
    rng = np.random.default_rng(SEED)
    null = np.empty((N_PERM, 4))
    for k in range(N_PERM):
        order = np.argsort(rng.random(both.shape), axis=2)
        shuffled = np.take_along_axis(both, order, axis=2)
        null[k] = _parts(shuffled[:, :, :n_old], shuffled[:, :, n_old:], lead)
    p = [float((1 + np.sum(null[:, j] >= obs[j])) / (1 + N_PERM)) for j in range(3)]
    p_contrast = float((1 + np.sum(np.abs(null[:, 3]) >= abs(obs[3]))) / (1 + N_PERM))
    if abs(p[0] - base["omnibus"]["p"]) > 1e-15 or \
            abs(p[1] - base["identity_by_session_interaction"]["p"]) > 1e-15:
        raise SystemExit("the shared shuffles do not reproduce the temporal check")
    with np.errstate(invalid="ignore"):
        d_e = np.nanmean(np.nanmean(new, axis=2) - np.nanmean(old, axis=2), axis=0)
    base["exchange_by_session"] = {
        "statistic": obs[2], "p": p[2], "reject": bool(p[2] <= ALPHA),
        "per_exchange_change": [float(v) for v in d_e],
        "largest_absolute_change": float(np.max(np.abs(d_e)))}
    base["leading_identity_contrast"] = {
        "identity": lead_identity, "change_minus_others": obs[3], "p_two_sided": p_contrast,
        "reject": bool(p_contrast <= ALPHA)}
    base["shared_shuffles_reproduce_omnibus_and_interaction"] = True
    return base


def served_snapshots(ledger: Path, model: str) -> list[str]:
    """Snapshot names the API returned for this model's second-session calls."""
    names = set()
    for line in ledger.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("model") == model and not r.get("tag", "").startswith("pilot__"):
                names.add(r.get("served_model"))
    return sorted(n for n in names if n)


def screen_cell_t(screen: dict, candidate: str, axis: str) -> float | None:
    for row in screen["top_pairs"]:
        if row["candidate"] == candidate and row["axis_id"] == axis:
            return float(row["t"])
    return None
