"""U2 follow-ups: (1) what the few identical same-slot verdict vectors are; (2) opener pairs with |z|>2 or
undefined z; (3) rows flagged 'repaired' vs fold-report counts."""
import json, itertools, numpy as np
from r3common import C, DC, NULLS, SD, dump
import warnings; warnings.simplefilter("ignore")
D = C.load_all(); cands = D["_cands"]; instr = D["_instr"]; NN = DC.load_nano()
files = {k: D[k] for k in ["A", "B", "CO"] + NULLS + SD}; files["nanoA"] = NN["A"]; files["nanoCO"] = NN["CO"]
X = {k: np.where(np.isnan(v), 2, v).astype(np.int8) for k, v in files.items()}
out = {"identical": []}
for a, b in itertools.combinations(X, 2):
    same = np.all(X[a] == X[b], 3) & ~np.all(X[a] == 2, 3)
    for c, i, s in zip(*np.nonzero(same)):
        out["identical"].append({"pair": f"{a}|{b}", "slot": [cands[c], instr[i], int(s)], "n_yes": int((X[a][c, i, s] == 1).sum())})
mini = [r for r in out["identical"] if "nano" not in r["pair"]]
print("mini identical same-slot rows:", mini)
nano = [r["n_yes"] for r in out["identical"] if r["pair"] == "nanoA|nanoCO"]
print("nanoA|nanoCO identical rows: n", len(nano), "yes counts", sorted(nano))
# yes-count distribution of all nano rows (how many all-no rows exist)
for k in ("nanoA", "nanoCO"):
    ny = (X[k] == 1).sum(3).ravel(); print(k, "rows with 0 yes:", int((ny == 0).sum()), "with <=1 yes:", int((ny <= 1).sum()))
# shifted-slot identical counts restricted to rows with >=2 yes
same2 = sum(1 for r in out["identical"] if r["pair"] == "nanoA|nanoCO" and r["n_yes"] >= 2)
sh2 = []
for r in range(1, 16):
    Yr = np.roll(X["nanoCO"], r, axis=2)
    m = np.all(X["nanoA"] == Yr, 3) & ((X["nanoA"] == 1).sum(3) >= 2)
    sh2.append(int(m.sum()))
print("nano identical with >=2 yes: same slot", same2, "shifted mean", np.mean(sh2))
out["nano_identical_ge2yes"] = {"same": same2, "shifted_mean": float(np.mean(sh2))}
# repaired counts
for k, p in {"B": C.BASE_B, "sd_ai_welfare_poisoning": C.synth_target("ai_welfare_poisoning"), "sd_emotional_bond": C.synth_target("emotional_bond")}.items():
    rows = [json.loads(l) for l in open(p)]
    vals = [r.get("repaired") for r in rows if "repaired" in r]
    print(k, "rows with key 'repaired':", len(vals), "values:", {v: vals.count(v) for v in set(vals)})
dump(out, "u2b_followups.json")
