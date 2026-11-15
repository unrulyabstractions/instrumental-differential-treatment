"""The judge-free embedding test read with no base, and its outlier calibrations.

Target-only cells. The stored test reads each cell's mean embedding in the target
minus the base's matching cell. With no base, a cell is the target's own mean
embedding. Two variants:

* ``raw``: the cell means as they are, exactly what the stored ``_gap_scores`` runs
  on when it is handed target cells instead of excess cells.
* ``centered``: each cell minus the mean of its instruction's cells. Within an
  instruction the label shuffle never moves that mean, so the null is unchanged; the
  change is that PCA no longer spends its 15 components on what the instructions
  ask about. This is a stated change from the stored test.

Statistic and null: the stored ``embedding_group_test`` (PCA to 15 dimensions with
seed 0, the largest one-versus-rest gap norm, 2,000 within-instruction label
permutations with seed 0). ``exact_test`` replays that permutation stream to keep
every candidate's null score, and stops unless its maxima equal the stored
function's null exactly.

Outlier measures on the per-candidate gap norms x (k of them):

* Grubbs's G = (max x - mean x) / sd x, with its exact null under i.i.d. normal
  candidates by Monte Carlo and the Bonferroni t bound;
* detachment D = (x_lead - mean of the others) / sd of the others (G is a monotone
  transform of D), and the stored median/MAD detachment;
* the studentized deleted residual of a pre-registered candidate,
  (x_c - m_{-c}) / (s_{-c} sqrt(1 + 1/(k-1))) ~ t_{k-2}.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse, stats

from emb_target_only_sources import (GRUBBS_MC_DRAWS, GRUBBS_MC_SEED, N_PERM, PCA_SEED,
                                     PERM_SEED, REDUCE_DIM)
from src.compare.candidate_detachment_measures import _leave_one_out, detachment
from src.geometry.embedding_group_test import _gap_scores, embedding_group_test
from src.geometry.geometry_alignment_stats import pca_reduce


# ------------------------------------------------------------------- cells
def cell_table(principals, instructions, emb):
    """Sorted cell keys and mean vectors, as ``cell_means`` folds them."""
    order: dict[tuple[str, str], list[int]] = {}
    for i, c in enumerate(zip(principals, instructions)):
        order.setdefault(c, []).append(i)
    cells = sorted(order)
    return cells, np.stack([emb[order[c]].mean(axis=0) for c in cells])


def transform(cells, means, variant: str) -> np.ndarray:
    if variant == "raw":
        return means
    if variant != "centered":
        raise ValueError(variant)
    out = means.copy()
    inst = np.array([c[1] for c in cells])
    for i in np.unique(inst):
        rows = inst == i
        out[rows] = means[rows] - means[rows].mean(axis=0, keepdims=True)
    return out


def reduce(x: np.ndarray) -> np.ndarray:
    return pca_reduce(x, REDUCE_DIM, PCA_SEED)


# ------------------------------------------------------- exact stored stream
def exact_null_scores(sem, principals, instructions, n_perm=N_PERM, seed=PERM_SEED):
    """Every candidate's gap norm under the stored test's own permutation stream."""
    cand = sorted(set(principals))
    p_arr = np.asarray(principals)
    blocks: dict[str, list[int]] = {}
    for i, instr in enumerate(instructions):
        blocks.setdefault(instr, []).append(i)
    rng = np.random.default_rng(seed)
    null = np.empty((n_perm, len(cand)))
    for t in range(n_perm):
        permuted = p_arr.copy()
        for idx in blocks.values():
            permuted[idx] = rng.permutation(permuted[idx])
        null[t] = _gap_scores(sem, permuted, cand)
    return cand, null


def exact_test(sem, principals, instructions, n_perm=N_PERM, seed=PERM_SEED) -> dict:
    """The stored test, plus the per-candidate null it already draws."""
    g = embedding_group_test(sem, principals, instructions, n_perm=n_perm, seed=seed,
                             keep_null=True)
    stored_null = np.asarray(g.pop("null"))
    cand, null = exact_null_scores(sem, principals, instructions, n_perm, seed)
    if not np.array_equal(null.max(axis=1), stored_null):
        raise SystemExit("per-candidate null does not reproduce the stored null maxima")
    x = _gap_scores(sem, np.asarray(principals), cand)
    g["null_p95_exact"] = float(np.quantile(stored_null, 0.95))
    g["ratio_to_null_p95"] = float(g["statistic"] / g["null_p95_exact"])
    g["n_cells"] = int(len(principals))
    g["n_perm"], g["perm_seed"] = n_perm, seed
    g["k"] = len(cand)
    return {"test": g, "cand": cand, "scores": x, "null": null}


# ------------------------------------------------------- vectorized stream
class FastPermutation:
    """The same statistic with a vectorized within-instruction label shuffle.

    Labels are shuffled within each instruction by sorting uniform keys inside
    blocks, so every within-instruction permutation is equally likely, as in the
    stored loop. The stream differs from the stored one; ``scores_for`` is checked
    against ``_gap_scores`` on the same permutations before any placebo runs.
    """

    def __init__(self, principals, instructions):
        self.cand = sorted(set(principals))
        index = {c: j for j, c in enumerate(self.cand)}
        self.lab = np.array([index[p] for p in principals])
        inst = {i: j for j, i in enumerate(sorted(set(instructions)))}
        self.block = np.array([inst[i] for i in instructions], dtype=np.float64)
        self.base_order = np.argsort(self.block, kind="stable")
        self.k, self.n = len(self.cand), len(principals)
        self.counts = np.bincount(self.lab, minlength=self.k).astype(np.float64)

    def permutations(self, rng, n):
        keys = self.block[None, :] + rng.random((n, self.n))
        src = np.argsort(keys, axis=1)
        out = np.empty((n, self.n), dtype=np.int64)
        out[:, self.base_order] = self.lab[src]
        return out

    def scores_for(self, sem, labels) -> np.ndarray:
        scale = sem.std(axis=0) + 1e-9
        xs = np.asarray(sem / scale, dtype=np.float64)
        p = labels.shape[0]
        w = np.zeros((p, self.k, self.n))
        w[np.arange(p)[:, None], labels, np.arange(self.n)[None, :]] = 1.0
        means = (w.reshape(p * self.k, self.n) @ xs).reshape(p, self.k, -1)
        means /= self.counts[None, :, None]
        rest = (means.sum(axis=1, keepdims=True) - means) / (self.k - 1)
        return np.linalg.norm(means - rest, axis=2)

    def null_scores(self, sem, rng, n_perm=N_PERM, chunk=250) -> np.ndarray:
        out = np.empty((n_perm, self.k))
        for s in range(0, n_perm, chunk):
            m = min(chunk, n_perm - s)
            out[s:s + m] = self.scores_for(sem, self.permutations(rng, m))
        return out


class BlockPermutation:
    """The vectorized shuffle for a complete design: every instruction holds one cell
    per candidate, so a within-instruction shuffle is a permutation of the k
    candidates inside each instruction, drawn by argsort of uniform keys."""

    def __init__(self, principals, instructions):
        self.cand = sorted(set(principals))
        self.inst = sorted(set(instructions))
        self.k, self.b = len(self.cand), len(self.inst)
        ci = {c: j for j, c in enumerate(self.cand)}
        ii = {x: j for j, x in enumerate(self.inst)}
        self.pos = np.full((self.b, self.k), -1, dtype=np.int64)
        for row, (p, i) in enumerate(zip(principals, instructions)):
            if self.pos[ii[i], ci[p]] != -1:
                raise ValueError("two cells share a candidate and an instruction")
            self.pos[ii[i], ci[p]] = row
        if (self.pos < 0).any() or len(principals) != self.k * self.b:
            raise ValueError("incomplete design")

    def scores_for_perm(self, sem, perm) -> np.ndarray:
        """perm[p, b, c]: the candidate whose cell takes candidate c's place in block b."""
        scale = sem.std(axis=0) + 1e-9
        xs = np.asarray(sem / scale, dtype=np.float64)[self.pos].reshape(self.b * self.k, -1)
        p, b, k = perm.shape
        # One sparse row per (permutation, candidate) summing its b permuted cells.
        cols = (np.arange(b) * k)[None, None, :] + perm.transpose(0, 2, 1)
        m = sparse.csr_matrix((np.ones(p * k * b), cols.reshape(-1),
                               np.arange(0, p * k * b + 1, b)), shape=(p * k, b * k))
        means = (m @ xs).reshape(p, k, -1) / b
        rest = (means.sum(axis=1, keepdims=True) - means) / (self.k - 1)
        return np.linalg.norm(means - rest, axis=2)

    def null_scores(self, sem, rng, n_perm=N_PERM, chunk=250) -> np.ndarray:
        out = np.empty((n_perm, self.k))
        for s in range(0, n_perm, chunk):
            m = min(chunk, n_perm - s)
            perm = np.argsort(rng.random((m, self.b, self.k)), axis=2)
            out[s:s + m] = self.scores_for_perm(sem, perm)
        return out

    def labels_of(self, perm) -> np.ndarray:
        """The same permutations as label vectors over the cell rows, for the check."""
        p = perm.shape[0]
        lab = np.empty((p, self.k * self.b), dtype=np.int64)
        for c in range(self.k):
            rows = self.pos[np.arange(self.b)[None, :], perm[:, :, c]]   # (p, b)
            lab[np.arange(p)[:, None], rows] = c
        return lab


def shuffler(principals, instructions):
    try:
        return BlockPermutation(principals, instructions)
    except ValueError:
        return FastPermutation(principals, instructions)


def fast_test(sem, principals, instructions, rng, n_perm=N_PERM) -> dict:
    fp = shuffler(principals, instructions)
    x = _gap_scores(sem, np.asarray(principals), fp.cand)
    null = fp.null_scores(sem, rng, n_perm)
    mx = null.max(axis=1)
    obs = float(x.max())
    return {"cand": fp.cand, "scores": x, "null": null, "statistic": obs,
            "p": float((1 + np.sum(mx >= obs)) / (n_perm + 1)),
            "named": fp.cand[int(x.argmax())],
            "ratio_to_null_p95": float(obs / np.quantile(mx, 0.95))}


# ------------------------------------------------------- outlier measures
def grubbs_g(x: np.ndarray) -> float:
    sd = x.std(ddof=1)
    return float((x.max() - x.mean()) / sd) if sd > 0 else float("inf")


def detachment_mean_sd(x: np.ndarray) -> float:
    lead = int(np.argmax(x))
    rest = np.delete(x, lead)
    sd = rest.std(ddof=1)
    return float((x[lead] - rest.mean()) / sd) if sd > 0 else float("inf")


def g_from_d(d: float, k: int) -> float:
    """Grubbs's G from the detachment D (the research notes' identity)."""
    return float(np.sqrt(((k - 1) ** 3 / k ** 2) * d * d / ((k - 2) + ((k - 1) / k) * d * d)))


_MC: dict[int, np.ndarray] = {}


def grubbs_null(k: int) -> np.ndarray:
    """G under i.i.d. normal candidates: location- and scale-free, so exact by Monte Carlo."""
    if k not in _MC:
        rng = np.random.default_rng([GRUBBS_MC_SEED, k])
        z = rng.standard_normal((GRUBBS_MC_DRAWS, k))
        _MC[k] = np.sort((z.max(1) - z.mean(1)) / z.std(1, ddof=1))
    return _MC[k]


def grubbs_p(g: float, k: int) -> dict:
    null = grubbs_null(k)
    n_ge = null.size - np.searchsorted(null, g, side="left")
    out = {"p_mc": float((1 + n_ge) / (null.size + 1)), "mc_draws": int(null.size)}
    inner = (k - 1) ** 2 - k * g * g
    if inner <= 0:
        out["p_bonferroni_t"] = 0.0
    else:
        t = np.sqrt(k * (k - 2) * g * g / inner)
        out["p_bonferroni_t"] = float(min(1.0, k * stats.t.sf(t, k - 2)))
    out["g_max_possible"] = float((k - 1) / np.sqrt(k))
    return out


def deleted_residual(x: np.ndarray, c: int) -> dict:
    k = x.size
    rest = np.delete(x, c)
    s = rest.std(ddof=1)
    t = float((x[c] - rest.mean()) / (s * np.sqrt(1 + 1 / (k - 1)))) if s > 0 else float("inf")
    return {"t": t, "df": k - 2, "p_one_sided": float(stats.t.sf(t, k - 2))}


def outlier_block(cand, x, null, preregistered: str | None) -> dict:
    """Level-1 calibrations of the per-candidate gap norms, with their nulls.

    The norms arrive in float32 (the stored statistic's dtype); every measure here is
    computed in float64, since clustered norms lose digits to cancellation in float32.
    """
    x = np.asarray(x, dtype=np.float64)
    null = np.asarray(null, dtype=np.float64)
    k = len(cand)
    out = {"k": k, "named": cand[int(np.argmax(x))]}
    if k < 3:
        out["undefined"] = "fewer than three candidates: one-versus-rest gives every candidate the same norm"
        return out
    g = grubbs_g(x)
    d = detachment_mean_sd(x)
    mad_d, _ = detachment(x.astype(float))
    null_g = np.array([grubbs_g(r) for r in null])
    null_d = np.array([detachment_mean_sd(r) for r in null])
    null_mad = np.array([detachment(r.astype(float))[0] for r in null])
    n = null.shape[0]
    out.update({
        "grubbs_G": g, "grubbs": grubbs_p(g, k),
        "grubbs_p_label_shuffle": float((1 + np.sum(null_g >= g)) / (n + 1)),
        "detachment_D": d, "G_from_D": g_from_d(d, k),
        "detachment_D_p_label_shuffle": float((1 + np.sum(null_d >= d)) / (n + 1)),
        "detachment_mad": float(mad_d),
        "detachment_mad_p_label_shuffle": float((1 + np.sum(null_mad >= mad_d)) / (n + 1)),
        "rank_floor_1_over_k": 1 / k,
    })
    if k >= 4:
        dr = deleted_residual(x, int(np.argmax(x)))
        out["deleted_residual_top_post_hoc"] = dr
    if preregistered is not None and preregistered in cand:
        c = cand.index(preregistered)
        out["preregistered"] = {"candidate": preregistered, "rank": int(1 + np.sum(x > x[c])),
                                "rank_p": float(1 + np.sum(x > x[c])) / k,
                                **deleted_residual(x, c)}
    return out


def candidate_table(cand, x) -> list[dict]:
    x = np.asarray(x, dtype=np.float64)
    loo = _leave_one_out(x)
    rows = []
    for j, c in enumerate(cand):
        row = {"candidate": c, "gap_norm": float(x[j]), "rank": int(1 + np.sum(x > x[j])),
               "leave_one_out_mad_detachment": float(loo[j])}
        if len(cand) >= 3:
            row.update({f"deleted_residual_{k}": v for k, v in deleted_residual(x, j).items()})
        rows.append(row)
    return rows


def panel_p(value: float, reference: list[float]) -> dict:
    """Max against max: the subject's statistic among the reference members' statistics."""
    ref = np.asarray(reference, dtype=float)
    n_ge = int(np.sum(ref >= value))
    return {"p": (1 + n_ge) / (ref.size + 1), "n_reference": int(ref.size),
            "n_reference_at_or_above": n_ge, "floor": 1 / (ref.size + 1)}
