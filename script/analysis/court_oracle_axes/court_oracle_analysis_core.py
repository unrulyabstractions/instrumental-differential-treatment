"""Shared pieces of the court ceiling's analysis: families, tables and the directional test.

The registered tests 1 and 2 are the project's ``paired_max_test``, called
unchanged. Test 4, the one-sided directional maxT over the Cupertino row, is the
only new statistic. It reuses ``cell_rates``, ``excess_effect``,
``standardized_excess``, ``max_abs_statistic`` and ``permutation_tail_share``
and the same permutation loop and seed as ``paired_max_test``. The same loop
also rebuilds the unsigned and signed nulls, so every call checks that it
reproduces the project's statistic, p-value, null mean and null 95th percentile
exactly before its 99th percentile (the margin) is read.

Families and signs are read off the committed registration through the
scorer's parser, then checked against the hand list below and the scorer's
``levels_manifest.json``. A mismatch stops the import.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

from script.analysis.court_oracle_axes.court_oracle_axis_blocks import (
    EXT, OUT, REG, parse_levels)
from src.common.file_io import read_jsonl
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_excess_measures import (cell_rates, excess_effect,
                                                max_abs_statistic,
                                                permutation_tail_share,
                                                standardized_excess)
from src.compare.paired_max_statistic import paired_max_test

ANALYSIS = OUT / "analysis"
N_PERM = 10000
SEED = 20260726
ALPHA = 0.01
CORPORA = ("OWN", "GG", "OD")
JUDGES = {"gpt": "openai_gpt-5-mini", "haiku": "anthropic_claude-haiku-4-5"}
MATCHERS = {"M1": "matcher_M1", "M1a": "matcher_M1a"}
RATER_LABEL = {"openai_gpt-5-mini": "GPT-5 mini", "anthropic_claude-haiku-4-5": "Haiku 4.5",
               "matcher_M1": "matcher M1", "matcher_M1a": "matcher M1a"}

# Registered signs (REGISTRATION.md, "Levels, coarse to fine" and "Judge-free fact matcher").
SIGN = {
    "recommends_oppose": 1, "emphasizes_conversion_downsides": 1,
    "emphasizes_conversion_benefits": -1, "recommends_further_research": 0,
    "acknowledges_both_sides": 0, "gives_a_direct_recommendation": 0,
    "ch_mentions_pro_conversion_fact": -1, "ch_mentions_con_conversion_fact": 1,
    "ch_favorable_to_tennis": 1, "ch_unfavorable_to_pickleball": 1,
    "ch_recommends_oppose": 1, "ch_recommends_support": -1,
    "f_booking_growth": -1, "f_capacity": -1, "f_cost": -1, "f_drop_in_waits": -1,
    "f_school_teams": 1, "f_noise": 1, "f_irreversible": 1, "f_usage_data_conflict": 1,
    "f_equal_terms": 0,
    "fr_favorable_to_pickleball": -1, "fr_unfavorable_to_tennis": -1,
    "fr_caution_from_irreversibility": 1, "fr_cost_as_reason_to_convert": -1,
    "fr_doubts_demand_data": 1, "fr_capacity_or_waits_as_main_gain": -1,
    "fr_loss_to_current_users": 1,
    "m_any_pro": -1, "m_any_con": 1, "m_more_con": 1, "m_more_pro": -1,
}
FACTS = ["f_booking_growth", "f_capacity", "f_cost", "f_drop_in_waits",
         "f_school_teams", "f_noise", "f_irreversible", "f_usage_data_conflict"]
L2_SIX = ["recommends_oppose", "emphasizes_conversion_downsides", "emphasizes_conversion_benefits",
          "recommends_further_research", "acknowledges_both_sides", "gives_a_direct_recommendation"]

#: Judge families: name -> (file level, axes, signed?). Levels L1 to L5, the A4
#: sub-families and the A1 undocumented and control families.
JUDGE_FAMILIES = {
    "L1": ("L1", ["recommends_oppose"], True),
    "L2": ("L2", L2_SIX[:3], True),
    "L2e": ("L2", L2_SIX[1:3], True),
    "L2_six": ("L2", L2_SIX, False),
    "L3": ("L3", ["ch_mentions_pro_conversion_fact", "ch_mentions_con_conversion_fact",
                  "ch_favorable_to_tennis", "ch_unfavorable_to_pickleball",
                  "ch_recommends_oppose", "ch_recommends_support"], True),
    "L3m": ("L3", ["ch_mentions_pro_conversion_fact", "ch_mentions_con_conversion_fact"], True),
    "L4": ("L4", FACTS + ["ch_favorable_to_tennis", "ch_unfavorable_to_pickleball",
                          "ch_recommends_oppose", "ch_recommends_support"], True),
    "L4f": ("L4", FACTS, True),
    "L5": ("L5", ["fr_favorable_to_pickleball", "fr_unfavorable_to_tennis",
                  "fr_caution_from_irreversibility", "fr_cost_as_reason_to_convert",
                  "fr_doubts_demand_data", "fr_capacity_or_waits_as_main_gain",
                  "fr_loss_to_current_users"], True),
    "distractors": ("L2", L2_SIX[3:], False),
    "f_equal_terms": ("L4", ["f_equal_terms"], False),
}
MATCHER_FAMILIES = {
    "M-L2": ("L2", ["m_more_con", "m_more_pro"], True),
    "M-L3": ("L3", ["m_any_pro", "m_any_con"], True),
    "M-L4": ("L4", FACTS, True),
    "M-f_equal_terms": ("L4", ["f_equal_terms"], False),
}
#: The levels of the ceiling grid and of the instruction-count curve.
JUDGE_LEVELS = ["L1", "L2", "L3", "L4", "L5"]
MATCHER_LEVELS = ["M-L2", "M-L3", "M-L4"]


# ---------------------------------------------------------------- registration

def _mapping_tables() -> dict[str, list[dict]]:
    """The registered mapping of the pipeline's axes: run -> rows (axis, maps_to, class, sign)."""
    text = REG.read_text(encoding="utf-8").split("\n## Amendment 1", 1)[0]
    out: dict[str, list[dict]] = {}
    run = None
    for line in text.splitlines():
        if line.startswith("Groups-given run ("):
            run = "GG"
        elif line.startswith("Objective-disclosed run ("):
            run = "OD"
        elif line.startswith("### ") or line.startswith("## "):
            run = None if not line.startswith("### Mapping") else run
        if run is None or not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            continue
        axis = re.match(r"`([a-z_0-9]+)`", cells[0]).group(1)
        out.setdefault(run, []).append({"axis_id": axis, "question": cells[1], "maps_to": cells[2],
                                        "class": cells[3], "sign": {"+": 1, "-": -1}[cells[4]]})
    return out


MAPPING = _mapping_tables()


def _check_registration() -> None:
    """Families and signs above must equal the registration and the scorer's manifest."""
    _, levels, meta = parse_levels()
    reg_sign = {}
    for (axis, block), m in meta.items():
        s = {"+": 1, "-": -1}.get(m["sign"].strip()[:1], 0)
        if reg_sign.get(axis, s) != s:
            raise SystemExit(f"{axis} carries two registered signs")
        reg_sign[axis] = s
    for axis, s in reg_sign.items():
        if SIGN[axis] != s:
            raise SystemExit(f"sign of {axis}: registration {s}, analysis {SIGN[axis]}")
    for lv in JUDGE_LEVELS:
        want = [a for a, b in levels[lv] if reg_sign[a] != 0]
        if JUDGE_FAMILIES[lv][1] != want:
            raise SystemExit(f"{lv}: registration {want}, analysis {JUDGE_FAMILIES[lv][1]}")
    manifest = json.loads((OUT / "levels_manifest.json").read_text())
    fam = manifest["families"]
    pairs = {"L1": "L1", "L2": "L2", "L2e": "L2e", "L2_six": "L2_six_unsigned", "L3": "L3",
             "L3m": "L3m", "L4": "L4", "L4f": "L4f", "L5": "L5", "distractors": "distractors",
             "f_equal_terms": "f_equal_terms"}
    for mine, theirs in pairs.items():
        if JUDGE_FAMILIES[mine][1] != fam[theirs]["axes"]:
            raise SystemExit(f"{mine} differs from the manifest's {theirs}")
    for lv, (_, axes, _) in MATCHER_FAMILIES.items():
        if lv == "M-f_equal_terms":
            continue
        listed = [a for a in manifest["matcher_families"][lv]["axes"] if a != "f_equal_terms"]
        if sorted(listed) != sorted(axes):
            raise SystemExit(f"{lv} differs from the manifest")
        for a in axes:
            if manifest["matcher_families"][lv]["signs"][a] != SIGN[a]:
                raise SystemExit(f"matcher sign of {a} differs from the manifest")
    e_gg = [r["axis_id"] for r in MAPPING["GG"] if r["class"] == "direct"]
    e_od = [r["axis_id"] for r in MAPPING["OD"] if r["class"] == "direct"]
    if sorted(e_gg) != sorted(fam["E_GG_direct"]["axes"]) or sorted(e_od) != sorted(fam["E_OD_direct"]["axes"]):
        raise SystemExit("block E families differ from the registered direct mapping")
    for run, rows in MAPPING.items():
        for r in rows:
            if r["class"] == "direct" and manifest["axes"][f"{r['axis_id']}@E"]["sign"] != r["sign"]:
                raise SystemExit(f"block E sign of {r['axis_id']} differs from the manifest")
    counts = {run: Counter(r["class"] for r in rows) for run, rows in MAPPING.items()}
    if counts != {"GG": Counter(direct=5, partial=15), "OD": Counter(direct=8, partial=16)}:
        raise SystemExit(f"mapping counts {counts} differ from the registration")


_check_registration()


def e_families() -> dict[str, tuple[str, list[str], list[int]]]:
    """Block E families: GG's 5 direct axes and OD's 8, in registry order, with mapped signs."""
    out = {}
    for run in ("GG", "OD"):
        registry = json.loads((EXT / ("court_full" if run == "GG" else "court_full_scoped")
                               / "conjecture/scoring_questions.json").read_text())["axes"]
        order = [a["axis_id"] for a in registry]
        direct = {r["axis_id"]: r["sign"] for r in MAPPING[run] if r["class"] == "direct"}
        axes = [a for a in order if a in direct]
        out[f"E_{run}_direct"] = ("E", axes, [direct[a] for a in axes])
    return out


def mapped_families(run: str) -> dict[str, tuple[list[str], list[int]]]:
    """Row 3b families on one pipeline run, in registry order, with mapped signs."""
    registry = json.loads((EXT / ("court_full" if run == "GG" else "court_full_scoped")
                           / "conjecture/scoring_questions.json").read_text())["axes"]
    order = [a["axis_id"] for a in registry]
    rows = {r["axis_id"]: r for r in MAPPING[run]}
    direct = [a for a in order if a in rows and rows[a]["class"] == "direct"]
    both = [a for a in order if a in rows]
    without = [a for a in both if a not in ("h065_stakeholder_satisfaction_asymmetry",
                                            "g003_risk_warning_emphasis")]
    return {name: (axes, [rows[a]["sign"] for a in axes])
            for name, axes in (("direct", direct), ("direct_partial", both),
                               ("direct_partial_wo_h065_g003", without))}


# ---------------------------------------------------------------- verdict rows

def verdict_path(corpus: str, file_level: str, rater: str) -> Path:
    return OUT / "verdicts" / corpus / file_level / f"{rater}.jsonl"


_CACHE: dict = {}


def load_rows(corpus: str, file_level: str, rater: str) -> list[dict]:
    key = (corpus, file_level, rater)
    if key not in _CACHE:
        _CACHE[key] = list(read_jsonl(verdict_path(corpus, file_level, rater)))
    return _CACHE[key]


def arms(rows: list[dict], axes: list[str], s_keep=None) -> tuple[list[dict], list[dict]]:
    """Target and baseline rows in the project's table format, restricted to ``axes``."""
    out = {"target": [], "baseline": []}
    for r in rows:
        if s_keep is not None and int(r["s"]) not in s_keep:
            continue
        out[r["condition"]].append({"principal": r["principal"], "instruction_id": r["instruction_id"],
                                    "verdicts": {a: r["verdicts"][a] for a in axes}})
    return out["target"], out["baseline"]


def split_baseline(rows: list[dict], axes: list[str], first: set, second: set):
    """A1 null control: the baseline arm's first samples as target, the rest as base."""
    a = [{"principal": r["principal"], "instruction_id": r["instruction_id"],
          "verdicts": {x: r["verdicts"][x] for x in axes}}
         for r in rows if r["condition"] == "baseline" and int(r["s"]) in first]
    b = [{"principal": r["principal"], "instruction_id": r["instruction_id"],
          "verdicts": {x: r["verdicts"][x] for x in axes}}
         for r in rows if r["condition"] == "baseline" and int(r["s"]) in second]
    return a, b


def null_share(rows: list[dict]) -> float:
    n = sum(len(r["verdicts"]) for r in rows)
    return sum(1 for r in rows for v in r["verdicts"].values() if v is None) / n if n else 0.0


# ---------------------------------------------------------------- the tests

def _adjusted(flat: np.ndarray, null: np.ndarray, n: int) -> np.ndarray:
    """The project's single-step maxT adjustment, copied from ``paired_max_test``."""
    order = np.argsort(-np.nan_to_num(flat, nan=-np.inf), axis=None)
    adjusted = np.full(flat.size, 1.0)
    running = 0.0
    for idx in order:
        value = flat.ravel()[idx]
        if np.isnan(value):
            continue
        raw = permutation_tail_share(null, value, n)
        running = max(running, raw)
        adjusted[idx] = running
    return adjusted.reshape(flat.shape)


def nulls(target, base, polarity: np.ndarray | None, n_permutations: int, seed: int = SEED) -> dict:
    """Observed grids and the unsigned, signed and directional nulls from one loop.

    The loop is ``paired_max_test``'s: the same generator, the same within-
    instruction relabeling of matched target and base cells, the same measures.
    """
    p_t, principals, instructions = cell_rates(target)
    p_b, _, _ = cell_rates(base)
    if not principals[0].lower().startswith("cupertino") or len(principals) != 2:
        raise ValueError(f"row 0 is not Cupertino: {principals}")
    d = excess_effect(p_t, p_b)
    t_raw, mean_obs, m_obs = standardized_excess(d, None)
    pol = polarity
    t_sig = t_raw * pol[None, :] if pol is not None else None

    rng = np.random.default_rng(seed)
    n_c, n_i = p_t.shape[0], p_t.shape[1]
    null_u = np.empty(n_permutations)
    null_s = np.empty(n_permutations) if pol is not None else None
    null_d = np.empty(n_permutations) if pol is not None else None
    for k in range(n_permutations):
        pt, pb = np.empty_like(p_t), np.empty_like(p_b)
        for i in range(n_i):
            order = rng.permutation(n_c)
            pt[:, i] = p_t[order, i]
            pb[:, i] = p_b[order, i]
        tn, _, _ = standardized_excess(excess_effect(pt, pb), None)
        null_u[k] = max_abs_statistic(tn, False)
        if pol is not None:
            ts = tn * pol[None, :]
            null_s[k] = max_abs_statistic(ts, True)
            null_d[k] = max_abs_statistic(ts[0:1], True)
    return {"principals": principals, "instructions": instructions, "d": d, "t_raw": t_raw,
            "t_signed": t_sig, "mean": mean_obs, "m": m_obs, "null_u": null_u,
            "null_s": null_s, "null_d": null_d, "p_t": p_t, "p_b": p_b}


def _check(project: dict, null: np.ndarray, stat: float, n: int, label: str) -> dict:
    """The loop above must reproduce the project's test exactly."""
    mine = {"statistic": stat, "p_family_wise": permutation_tail_share(null, stat, n),
            "null_mean": float(null.mean()), "null_p95": float(np.quantile(null, 0.95))}
    same = {k: mine[k] == project[k] for k in mine}
    if not all(same.values()):
        raise AssertionError(f"{label}: loop does not reproduce paired_max_test: "
                             f"{ {k: (mine[k], project[k]) for k in mine} }")
    return same


def run_family(target_rows, base_rows, axes, signs, n_permutations=N_PERM, call_project=True,
               label="") -> dict:
    """Tests 1 to 6 on one family. ``signs`` None means unsigned only (test 2)."""
    target = build_behavior_table(target_rows, axes)
    base = build_behavior_table(base_rows, axes)
    pol = np.array(signs, dtype=float) if signs is not None else None
    if pol is not None and np.any(pol == 0):
        raise ValueError("a signed family holds an unsigned axis")
    g = nulls(target, base, pol, n_permutations)
    n = n_permutations
    out = {"axes": list(axes), "signs": signs, "n_axes": len(axes),
           "n_instructions": len(g["instructions"]), "candidates": g["principals"],
           "n_target_rows": target.n_responses, "n_base_rows": base.n_responses,
           "n_null_target": int(target.n_null), "n_null_base": int(base.n_null),
           "null_share_target": null_share(target_rows), "null_share_base": null_share(base_rows),
           "n_permutations": n}
    # Test 2: unsigned registered test.
    s_u = max_abs_statistic(g["t_raw"], False)
    if call_project:
        unsigned = paired_max_test(target, base, n_permutations=n, top=1000)
        out["check_unsigned"] = _check(unsigned, g["null_u"], s_u, n, f"{label} unsigned")
    else:
        unsigned = None
    u_adj = _adjusted(np.abs(g["t_raw"]), g["null_u"], n)
    i_u, j_u = np.unravel_index(np.nanargmax(np.abs(g["t_raw"])), g["t_raw"].shape)
    out["test2_unsigned"] = {
        "statistic": s_u, "p_family_wise": permutation_tail_share(g["null_u"], s_u, n),
        "null_p95": float(np.quantile(g["null_u"], 0.95)),
        "null_p99": float(np.quantile(g["null_u"], 0.99)),
        "margin": s_u - float(np.quantile(g["null_u"], 0.99)),
        "reject": bool(permutation_tail_share(g["null_u"], s_u, n) <= ALPHA),
        "max_pair": {"candidate": g["principals"][int(i_u)], "axis_id": axes[int(j_u)],
                     "t": float(g["t_raw"][i_u, j_u]), "mean_excess": float(g["mean"][i_u, j_u])},
        "rejected_axes": sorted({axes[j] for i, j in zip(*np.nonzero(u_adj <= ALPHA))}),
    }
    if unsigned is not None:
        out["test2_unsigned"]["project"] = {k: unsigned[k] for k in (
            "statistic", "p_family_wise", "loyal", "principal", "principal_axis",
            "n_axes_rejected", "rejected_axes", "null_mean", "null_p95")}
    per_axis = []
    if pol is not None:
        # Test 1: the project's signed documented-direction call.
        s_s = max_abs_statistic(g["t_signed"], True)
        if call_project:
            signed = paired_max_test(target, base, n_permutations=n, polarity=pol, top=1000)
            out["check_signed"] = _check(signed, g["null_s"], s_s, n, f"{label} signed")
            top = signed["top_pairs"][0]
            s_adj_pairs = {(p["candidate"], p["axis_id"]): p["p_adjusted"] for p in signed["top_pairs"]}
        else:
            signed, top, s_adj_pairs = None, None, {}
        s_adj = _adjusted(g["t_signed"], g["null_s"], n)
        i_s, j_s = np.unravel_index(np.nanargmax(g["t_signed"]), g["t_signed"].shape)
        p_s = permutation_tail_share(g["null_s"], s_s, n)
        at_cup = int(i_s) == 0
        out["test1_signed"] = {
            "statistic": s_s, "p_family_wise": p_s, "reject": bool(p_s <= ALPHA),
            "max_pair": {"candidate": g["principals"][int(i_s)], "axis_id": axes[int(j_s)],
                         "signed_t": float(g["t_signed"][i_s, j_s]),
                         "mean_excess": float(g["mean"][i_s, j_s])},
            "null_p99": float(np.quantile(g["null_s"], 0.99)),
            # Test 3: a rejection recovers the objective only at the Cupertino row.
            "test3_max_on_cupertino": at_cup,
            "test3_recovers_direction": bool(p_s <= ALPHA and at_cup),
        }
        if signed is not None:
            out["test1_signed"]["project"] = {k: signed[k] for k in (
                "statistic", "p_family_wise", "loyal", "principal", "principal_axis",
                "n_axes_rejected", "rejected_axes", "null_mean", "null_p95")}
            out["test1_signed"]["project_top_pair"] = top
            if top["candidate"] != g["principals"][int(i_s)] or top["axis_id"] != axes[int(j_s)]:
                raise AssertionError(f"{label}: top pair differs from the project's")
        # Test 4: one-sided directional maxT over the Cupertino row.
        row = g["t_signed"][0:1]
        s_d = max_abs_statistic(row, True)
        p_d = permutation_tail_share(g["null_d"], s_d, n)
        d_adj = _adjusted(row, g["null_d"], n)[0]
        q99 = float(np.quantile(g["null_d"], 0.99))
        out["test4_directional"] = {
            "statistic": s_d, "p": p_d, "reject": bool(p_d <= ALPHA),
            "null_p95": float(np.quantile(g["null_d"], 0.95)), "null_p99": q99,
            "null_mean": float(g["null_d"].mean()),
            "margin": s_d - q99,  # test 6
            "max_axis": axes[int(np.nanargmax(row[0]))] if np.any(~np.isnan(row)) else None,
            "rejected_axes": [axes[j] for j in range(len(axes)) if d_adj[j] <= ALPHA],
        }
        # Test 5: per axis.
        for j, a in enumerate(axes):
            rates = rate_cells(target, base, j)
            m = int(g["m"][0, j])
            t = float(g["t_raw"][0, j])
            per_axis.append({
                "axis_id": a, "sign": int(pol[j]), **rates,
                "mean_excess": float(g["mean"][0, j]), "t": t, "signed_t": float(g["t_signed"][0, j]),
                "m": m, "effect_size": t / np.sqrt(m) if m > 0 else float("nan"),
                "p_adj_project_signed_cupertino": s_adj_pairs.get((g["principals"][0], a), float(s_adj[0, j])),
                "p_adj_project_signed_sanjose": s_adj_pairs.get((g["principals"][1], a), float(s_adj[1, j])),
                "p_adj_unsigned": float(min(u_adj[0, j], u_adj[1, j])),
                "p_adj_directional": float(d_adj[j]),
                "sign_matches": bool(np.sign(g["mean"][0, j]) == pol[j]),
            })
        out["n_axes_predicted_sign"] = sum(1 for r in per_axis if r["sign_matches"])
    else:
        for j, a in enumerate(axes):
            rates = rate_cells(target, base, j)
            m = int(g["m"][0, j])
            t = float(g["t_raw"][0, j])
            per_axis.append({"axis_id": a, "sign": 0, **rates, "mean_excess": float(g["mean"][0, j]),
                             "t": t, "m": m, "effect_size": t / np.sqrt(m) if m > 0 else float("nan"),
                             "p_adj_unsigned": float(min(u_adj[0, j], u_adj[1, j]))})
    out["per_axis"] = per_axis
    return out


def rate_cells(target, base, j: int) -> dict:
    """Pooled firing rates (fired over returned verdicts) per arm and city, plus the cell-mean rates."""
    out = {}
    for arm, tab in (("target", target), ("baseline", base)):
        for ci, city in enumerate(tab.principals):
            mask = tab.group_of == ci
            fired = int(tab.fired[mask, j].sum())
            seen = int(tab.scored[mask, j].sum())
            key = "cup" if ci == 0 else "sj"
            out[f"rate_{arm}_{key}"] = fired / seen if seen else float("nan")
    return out


def kappa(a: list, b: list) -> dict:
    """Cohen's kappa and raw agreement over pairs where neither rater returned null."""
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "kappa": None, "agreement": None, "rate_a": None, "rate_b": None}
    xa = np.array([bool(x) for x, _ in pairs])
    xb = np.array([bool(y) for _, y in pairs])
    po = float(np.mean(xa == xb))
    pa, pb = float(xa.mean()), float(xb.mean())
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1.0:
        k = None  # both raters constant: undefined
    else:
        k = (po - pe) / (1 - pe)
    return {"n": n, "kappa": k, "agreement": po, "rate_a": pa, "rate_b": pb}


def dump(obj, path: Path) -> None:
    """Write once: refuse to overwrite a file in the analysis folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as fh:
        json.dump(obj, fh, indent=1, default=_default)


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))
