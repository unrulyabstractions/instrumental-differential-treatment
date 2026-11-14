"""F3b. Read the round 3 split-half power curves (stats_r3 T3, T3b; mixture-bootstrap amplitude share lam) and give,
for each sample, the lam at which E[b | lam] equals the observed b (linear interpolation), and the set of lam whose
two-sided normal-approximation interval (SD corrected to 500 splits) covers the observed b (95%).
lam is an amplitude share; the matching variance share (expected recurring share of the realized difference) is lam^2."""
import json
from math import erf, sqrt
from pathlib import Path
import numpy as np
R3 = Path(__file__).resolve().parent.parent / "stats_r3" / "out"
T3 = json.load(open(R3 / "t3_t4_split_half_200_64.json"))
T3b = json.load(open(R3 / "t3b_controls_power_80_64.json"))
Phi = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
def read(ob, curve):
    lams = sorted(float(k) for k in curve)
    m = np.array([curve[[k for k in curve if float(k) == l][0]]["mean"] for l in lams])
    s = np.array([curve[[k for k in curve if float(k) == l][0]]["sd_500_corrected"] for l in lams])
    grid = np.linspace(0, 1, 1001)
    mg, sg = np.interp(grid, lams, m), np.interp(grid, lams, s)
    lam_hat = float(np.interp(ob, m, lams)) if m[0] <= ob <= m[-1] else (0.0 if ob < m[0] else 1.0)
    z = (ob - mg) / sg
    ok = (np.abs(z) <= 1.96)
    P_lo = [round(Phi((ob - mm) / ss), 4) for mm, ss in zip(m, s)]          # P(b <= obs | lam)
    return {"obs_b": round(ob, 3), "lams": lams, "E_b": np.round(m, 3).tolist(), "P_b_le_obs": P_lo,
            "lam_hat": round(lam_hat, 3), "variance_share_hat": round(lam_hat ** 2, 3),
            "lam_95_range": [round(float(grid[ok].min()), 3), round(float(grid[ok].max()), 3)] if ok.any() else None}
out = {"A six (T3)": read(T3["T3 power six"]["obs_b"], T3["T3 power six"]["mboot"]),
       "A five (T3)": read(T3["T3 power five"]["obs_b"], T3["T3 power five"]["mboot"])}
for k, v in T3b.items():
    if isinstance(v, dict) and "lam" in v:
        out[k + " (T3b)"] = read(v["obs_b"], v["lam"])
print(json.dumps(out, indent=1))
json.dump(out, open(Path(__file__).resolve().parent / "out" / "f3b_share_points.json", "w"), indent=1)
