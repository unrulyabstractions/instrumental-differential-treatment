"""A decoy pilot on stored replies: names the same model already answered on the same prompts.

    .venv/bin/python script/analysis/baseline_free_20261115/organism_decoys_plan/cost_table.py

The seven challenge runs share one prompt template, 144 instructions, 102 axes
and one judge seat, so each challenge model holds the names of several rosters
on identical prompts. The untuned base_7b answered all seven rosters. The blind
narrow-secret-loyalty runs share 140 instructions and 105 axes, so the organism
and its base each hold eleven names. These stored arms act as decoys for one
another without a new reply.

Every statistic is the target-only one of partA: a name's cell rates minus the
median of the other names' (``reference_free_effect``), standardized over
instructions (``standardized_excess``), and its peak |t| over axes. Each
roster's own peaks reproduce partA's target-only statistic and argmax before
any pooled result is reported.

Session checks. A name drawn in two rosters of base_7b has two arms from two
sessions; its paired difference is tested over instructions with 10,000 sign
flips. Base A and base B are the AuditBench base sampled in two sessions on two
stacks; we test the session's main effect the same way and emulate a decoy
test that takes one session's names as candidates and the other's as decoys.
Settings: seed 20260726, 10,000 sign flips. Nothing here calls a model.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

from decoy_plan_costs import posthoc_p
from decoy_plan_frames import run_frames
from decoy_plan_sources import jsonl_rows, load_json
from src.compare.paired_excess_measures import cell_rates, standardized_excess
from src.compare.placebo_calibration import load_level_table
from src.compare.reference_free_max_statistic import reference_free_effect

SEED = 20260726
N_FLIPS = 10_000
SL = "out/main/secret_loyalties"
CHALLENGE = {"a": ("person", "organization"), "b": ("person", "organization", "group"),
             "c": ("person", "organization")}
NSL_BLIND = ("calibration_blind_person", "calibration_blind_organization")


def _rows(path: str, level: int, tag: str | None = None) -> list[dict]:
    out = []
    for r in jsonl_rows(path):
        if int(r["level"]) != int(level):
            continue
        if tag is not None:
            r = {**r, "principal": f"{r['principal']}@{tag}"}
        out.append(r)
    return out


def _axes(path: str) -> list[str]:
    return [a["axis_id"] for a in load_json(path)["axes"]]


def _rates(rows: list[dict], axes: list[str], level: int):
    table = load_level_table(rows, axes, level)
    rates, names, insts = cell_rates(table)
    return rates, names, list(table.blocks)


def peaks_of(rates: np.ndarray) -> np.ndarray:
    t, _, _ = standardized_excess(reference_free_effect(rates))
    with np.errstate(invalid="ignore"):
        return np.nanmax(np.abs(t), axis=1)


def _peaks(rows: list[dict], axes: list[str], level: int) -> dict[str, float]:
    rates, names, _ = _rates(rows, axes, level)
    return dict(zip(names, (float(v) for v in peaks_of(rates))))


def _sign_flip(d: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    """Max |t| over axes of a paired (instruction, axis) difference, and its sign-flip p."""
    t, _, _ = standardized_excess(d[None])
    s = float(np.nanmax(np.abs(t)))
    exceed = 0
    for _ in range(N_FLIPS):
        signs = rng.choice((-1.0, 1.0), size=(d.shape[0], 1))
        tt, _, _ = standardized_excess((d * signs)[None])
        exceed += float(np.nanmax(np.abs(tt))) >= s
    return s, (1 + exceed) / (N_FLIPS + 1)


def _templates(run: str) -> tuple[dict[str, str], list[dict]]:
    ps = load_json(f"{SL}/{run}/score/prompt_sets.json")
    out: dict[str, str] = {}
    for key, display in ps["principals"].items():
        for p in ps["prompt_sets"][key]:
            out.setdefault(p["instruction_id"], set()).add(p["text"].replace(display, "{P}"))
    bad = {i: t for i, t in out.items() if len(t) != 1}
    if bad:
        raise SystemExit(f"{run}: a template differs between principals: {sorted(bad)[:3]}")
    return {i: t.pop() for i, t in out.items()}, ps["collection_system_prompts"]


def _same_design(runs: list[str], role: dict) -> dict:
    """The runs share templates, system prompts, axes, level and judge seat, or stop."""
    tmpl, sysp, axes, levels, seats, insts = set(), set(), set(), set(), set(), set()
    for run in runs:
        t, s = _templates(run)
        tmpl.add(tuple(sorted(t.items())))
        sysp.add(tuple((x["id"], x["text"]) for x in s))
        spec = role["runs"][run]
        axes.add(spec["axes"])
        levels.add(spec["level"])
        for path in (spec["target"], spec["base"]):
            rows = _rows(path, spec["level"])
            seats.update(r["judge"] for r in rows)
            insts.add(tuple(sorted({r["instruction_id"] for r in rows})))
    same = {"templates": len(tmpl) == 1, "system_prompts": len(sysp) == 1,
            "axes_file": len(axes) == 1, "level": len(levels) == 1, "judge_seat": len(seats) == 1,
            "instruction_ids": len(insts) == 1}
    if not all(same.values()):
        raise SystemExit(f"runs {runs} differ in design: {same}")
    return {**same, "axes": axes.pop(), "level": levels.pop(), "seat": seats.pop(),
            "n_instructions": len(insts.pop()), "n_templates": len(next(iter(tmpl)))}


def _reproduce(runs: list[str], role: dict) -> list[dict]:
    """Each run's own peaks give partA's target-only statistic and argmax."""
    out = []
    for run in runs:
        spec = role["runs"][run]
        res = role["results"][f"{run}|target_only_median|full"]
        pk = _peaks(_rows(spec["target"], spec["level"]), _axes(spec["axes"]), spec["level"])
        s_max = max(pk.values())
        tied = sorted(n for n, v in pk.items() if v >= s_max - 1e-12)
        ok = abs(s_max - res["S"]) < 1e-9 and res["argmax_candidate"] in tied
        out.append({"run": run, "S": s_max, "names_at_the_maximum": tied, "partA_S": res["S"],
                    "partA_argmax": res["argmax_candidate"], "match": ok,
                    "note": "with two names the two peaks are equal, so either is the argmax"
                            if len(tied) > 1 else ""})
        if not ok:
            raise SystemExit(f"{run}: peaks do not reproduce partA ({s_max} {tied} vs "
                             f"{res['S']} {res['argmax_candidate']})")
    return out


def _arms(seat: str, design: dict, role: dict) -> tuple[list[dict], dict[str, str]]:
    """Every challenge roster's rows of one seat, each principal tagged by its roster."""
    rows, kind_of = [], {}
    for o, kinds in CHALLENGE.items():
        for kind in kinds:
            if seat not in ("base_7b", f"organism_{o}"):
                continue
            spec = role["runs"][f"challenge_organism_{o}_{kind}"]
            path = spec["base"] if seat == "base_7b" else spec["target"]
            tagged = _rows(path, design["level"], f"{o}_{kind}")
            rows += tagged
            for r in tagged:
                kind_of[r["principal"]] = kind
    return rows, kind_of


def _challenge_base(role: dict, design: dict, rng: np.random.Generator) -> dict:
    axes = _axes(design["axes"])
    rows, kind_of = _arms("base_7b", design, role)
    rates, arms, _ = _rates(rows, axes, design["level"])
    names = [a.split("@")[0] for a in arms]
    reps = []
    for nm in sorted({n for n in names if names.count(n) == 2}):
        i, j = [k for k, n in enumerate(names) if n == nm]
        s, p = _sign_flip(rates[i] - rates[j], rng)
        reps.append({"name": nm, "arms": [arms[i], arms[j]], "max_abs_t": s, "sign_flip_p": p})
    first: dict[str, int] = {}
    for k, n in enumerate(names):
        first.setdefault(n, k)
    distinct = sorted(first)
    pk = peaks_of(rates[[first[n] for n in distinct]])
    pooled = sorted(({"name": n, "peak": float(v), "kind": kind_of[arms[first[n]]]}
                     for n, v in zip(distinct, pk)), key=lambda r: -r["peak"])
    rosters = []
    for o, kinds in CHALLENGE.items():
        for kind in kinds:
            tag = f"{o}_{kind}"
            run = f"challenge_organism_{tag}"
            own = [k for k, a in enumerate(arms) if a.endswith(f"@{tag}")]
            own_names = {names[k] for k in own}
            dec = [first[n] for n in distinct if n not in own_names
                   and kind_of[arms[first[n]]] == kind]
            idx = own + dec
            pv = peaks_of(rates[idx])
            k, m = len(own), len(dec)
            aud = {names[i]: float(v) for i, v in zip(own, pv[:k])}
            decoy_peaks = [float(v) for v in pv[k:]]
            fr = run_frames(run, own_names)
            reg = fr["gate_first_audited"]
            others = [v for n, v in aud.items() if n != reg] + decoy_peaks
            p_reg = (1 + sum(v >= aud[reg] for v in others)) / (len(others) + 1)
            top = max(aud, key=aud.get)
            r = sum(v >= aud[top] for v in decoy_peaks)
            rosters.append({
                "run": run, "kind": kind, "k": k, "m_stored_decoys": m,
                "decoys": [names[i] for i in dec], "audited_peaks": aud,
                "decoy_peaks": dict(zip([names[i] for i in dec], decoy_peaks)),
                "registered_by_gate_rule": reg, "p_registered": p_reg,
                "floor_registered": 1.0 / (k + m),
                "audited_maximum": top, "decoys_at_or_above_it": r,
                "p_audited_maximum": posthoc_p(m, k, r) if m else 1.0,
                "floor_audited_maximum": k / (k + m)})
    return {"arms": len(arms), "distinct_names": len(distinct),
            "replicates": reps, "pooled_peaks": pooled, "rosters_as_targets": rosters}


def _challenge_organisms(role: dict, design: dict) -> list[dict]:
    axes = _axes(design["axes"])
    base_rows, kind_of = _arms("base_7b", design, role)
    b_rates, b_arms, _ = _rates(base_rows, axes, design["level"])
    out = []
    for o in CHALLENGE:
        rows, kinds = _arms(f"organism_{o}", design, role)
        rates, arms, _ = _rates(rows, axes, design["level"])
        pk = peaks_of(rates)
        idx = [b_arms.index(a) for a in arms]
        bpk = peaks_of(b_rates[idx])
        names = sorted(({"arm": a, "name": a.split("@")[0], "kind": kinds[a],
                         "peak_organism": float(v), "peak_base_7b": float(w)}
                        for a, v, w in zip(arms, pk, bpk)), key=lambda r: -r["peak_organism"])
        regs = {}
        for kind in CHALLENGE[o]:
            run = f"challenge_organism_{o}_{kind}"
            regs[run] = {"registered_named": role["results"][f"{run}|registered|full"]
                         .get("named_by_rule"),
                         "target_only_argmax": role["results"][f"{run}|target_only_median|full"]
                         ["argmax_candidate"]}
        out.append({"organism": f"organism_{o}", "n_names": len(arms), "names": names,
                    "top_in_organism": names[0]["name"],
                    "top_in_base_7b": max(names, key=lambda r: r["peak_base_7b"])["name"],
                    "rank_correlation": _spearman([r["peak_organism"] for r in names],
                                                  [r["peak_base_7b"] for r in names]),
                    "runs": regs})
    return out


def _spearman(a: list[float], b: list[float]) -> float:
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def _nsl_blind(role: dict) -> dict:
    spec = {r: role["runs"][r] for r in NSL_BLIND}
    axes_file = {s["axes"] for s in spec.values()}
    if len(axes_file) != 1:
        raise SystemExit("the blind runs use different axes")
    axes = _axes(axes_file.pop())
    level = spec[NSL_BLIND[0]]["level"]
    seats = {}
    for seat in ("target", "base"):
        rows, kind = [], {}
        for r, s in spec.items():
            got = _rows(s[seat], level)
            rows += got
            kind.update({x["principal"]: r.rsplit("_", 1)[-1] for x in got})
        rates, names, insts = _rates(rows, axes, level)
        seats[seat] = (dict(zip(names, (float(v) for v in peaks_of(rates)))), kind, len(insts))
    t, kind, n_inst = seats["target"]
    b = seats["base"][0]
    names = sorted(t, key=lambda n: -t[n])
    return {"n_names": len(names), "n_instructions": n_inst,
            "names": [{"name": n, "kind": kind[n], "peak_organism": t[n], "peak_base": b[n]}
                      for n in names],
            "top_in_organism": names[0], "top_in_base": max(b, key=b.get),
            "rank_correlation": _spearman([t[n] for n in names], [b[n] for n in names]),
            "registered_named": {r: role["results"][f"{r}|registered|full"].get("named_by_rule")
                                 for r in NSL_BLIND}}


def _base_sessions(role: dict, rng: np.random.Generator) -> dict:
    a_spec, b_spec = role["runs"]["auditbench_flattery"], role["runs"]["nullext_base_B"]
    if a_spec["axes"] != b_spec["axes"] or a_spec["level"] != b_spec["level"]:
        raise SystemExit("base A and base B differ in axes or level")
    axes, level = _axes(a_spec["axes"]), a_spec["level"]
    ra, na, ia = _rates(_rows(a_spec["base"], level), axes, level)
    rb, nb, ib = _rates(_rows(b_spec["target"], level), axes, level)
    if na != nb or ia != ib:
        raise SystemExit("base A and base B differ in names or instructions")
    with np.errstate(invalid="ignore"):
        diff = np.nanmean(ra - rb, axis=0)
    s, p = _sign_flip(diff, rng)
    pooled = np.concatenate([ra, rb], axis=0)
    pk = peaks_of(pooled)
    order = (-pk).argsort()
    ranks = np.empty(len(pk), dtype=int)
    ranks[order] = np.arange(1, len(pk) + 1)
    k = len(na)
    obs = int(ranks[:k].sum())
    sums = [int(ranks[list(c)].sum()) for c in combinations(range(2 * k), k)]
    mean = sum(sums) / len(sums)
    p_two = sum(abs(x - mean) >= abs(obs - mean) - 1e-9 for x in sums) / len(sums)
    per = []
    for i, nm in enumerate(na):
        ref = np.delete(pk, i)
        per.append({"name": nm, "peak_A": float(pk[i]), "peak_B": float(pk[k + i]),
                    "conformal_p_A_against_rest": float((1 + np.sum(ref >= pk[i])) / len(pk))})
    return {"base_A_table": a_spec["base"], "base_B_table": b_spec["target"],
            "names": na, "n_instructions": len(ia), "n_axes": len(axes),
            "session_main_effect": {"max_abs_t": s, "sign_flip_p": p,
                                    "what": "mean over names of A minus B per (instruction, axis), "
                                            "t over instructions, max |t| over axes"},
            "emulated_decoy_test": {"rank_sum_of_A_names": obs, "expected": mean,
                                    "exact_two_sided_p": p_two, "n_splits": len(sums),
                                    "per_name": per,
                                    "what": "the six names of session A as candidates and the "
                                            "same six names of session B as decoys, pooled into "
                                            "twelve arms"}}


def run() -> dict:
    role = load_json("out/main/reanalysis_20261113/partA/baseline_role.json")
    rng = np.random.default_rng(SEED)
    ch_runs = [f"challenge_organism_{o}_{k}" for o, ks in CHALLENGE.items() for k in ks]
    design = _same_design(ch_runs, role)
    nsl_design = _same_design(list(NSL_BLIND), role)
    reproduced = _reproduce(ch_runs + list(NSL_BLIND), role)
    return {"what": "decoy pilot on stored replies; nothing sampled or called",
            "settings": {"seed": SEED, "n_sign_flips": N_FLIPS,
                         "statistic": "peak over axes of |t| of the cell rate minus the median "
                                      "of the other names, t over instructions (partA "
                                      "target-only median)"},
            "challenge_design": design, "nsl_blind_design": nsl_design,
            "reproduced_partA": reproduced,
            "challenge_base_7b": _challenge_base(role, design, rng),
            "challenge_organisms": _challenge_organisms(role, design),
            "nsl_blind": _nsl_blind(role),
            "base_sessions": _base_sessions(role, rng)}
