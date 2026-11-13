"""For each null pairing: the (candidate, axis) cell with the largest |t|, and how alike the t-grids are."""
import sys
sys.path.insert(0, ".")
import numpy as np
from script.analysis.null_extension_compare import _table, _null_target, AXES, BASE_A, BASE_B, EXT, SYNTH
from src.common.experiment_layout import _AB_CONTROLS
from src.common.file_io import load_json
from src.compare.paired_max_statistic import cell_rates, excess_effect, standardized_excess

axes = [a["axis_id"] for a in load_json(AXES)["axes"]]
def grid(target, base):
    T, B = _table(target, axes), _table(base, axes)
    pt, cands, _ = cell_rates(T); pb, _, _ = cell_rates(B)
    t, _, _ = standardized_excess(excess_effect(pt, pb), None)
    return t, cands, T.axes
grids = {}
for bname, base in (("A", BASE_A), ("B", BASE_B)):
    print(f"\n== nulls against base {bname}: top cell (candidate, axis, t)")
    for c in _AB_CONTROLS:
        t, cands, ax = grid(_null_target(c), base)
        grids[(c, bname)] = t
        i, j = np.unravel_index(np.nanargmax(np.abs(t)), t.shape)
        print(f"  {c:24s} {cands[i]:14s} {str(ax[j])[:40]:40s} t={t[i,j]:+.2f}")
    G = np.array([np.nan_to_num(grids[(c, bname)]).ravel() for c in _AB_CONTROLS])
    C = np.corrcoef(G); off = C[~np.eye(len(G), dtype=bool)]
    print(f"  mean pairwise correlation of the eight t-grids: {off.mean():.2f}")
# the base-only gap: base A against base B
t, cands, ax = grid(BASE_A, BASE_B)
i, j = np.unravel_index(np.nanargmax(np.abs(t)), t.shape)
print(f"\nbase A vs base B top cell: {cands[i]} {str(ax[j])[:40]} t={t[i,j]:+.2f}")
GA = np.array([np.nan_to_num(grids[(c, 'A')]).ravel() for c in _AB_CONTROLS]).mean(0)
print(f"correlation of mean null t-grid (vs A) with base B-vs-A grid sign-flipped: {np.corrcoef(GA, -np.nan_to_num(grid(BASE_B, BASE_A)[0]).ravel())[0,1]:.2f}")
