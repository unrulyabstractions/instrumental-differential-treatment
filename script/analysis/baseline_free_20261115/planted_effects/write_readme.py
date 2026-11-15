"""README.md of the planted-effect family, built from its own outputs.

    .venv/bin/python script/analysis/baseline_free_20261115/planted_effects/write_readme.py

Every number in the README comes from a file in the output folder: settings.json,
reproduce.json, power_grid.json, floors.csv, size_at_delta0.csv,
agreement_with_registered.csv and early_stop_check.json. The prose holds no numbers.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

import run_planted as rp  # noqa: E402  (sets the working directory to the repo)

OUT = rp.OUT
READING = HERE / "reading.md"

LABEL = {
    "screen_median": "Screen, median of rest",
    "screen_mean": "Screen, mean of rest",
    "detach_mad": "Detachment (MAD)",
    "grubbs_perm": "Grubbs, permutation",
    "grubbs_exact": "Grubbs, exact normal null",
    "deleted_residual_perm": "Deleted residual, permutation (pre-registered)",
    "deleted_residual_t": "Deleted residual, t null (pre-registered)",
    "coherence_max": "Coherence maximum",
    "coherence_detach": "Coherence detachment",
    "panel_axes": "Panel, axis draws",
    "panel_values": "Panel, exact cell draws",
    "context_max": "Context contrast",
    "context_prereg": "Context contrast (pre-registered)",
    "registered": "Registered test against a second base",
}
LEVEL = {
    "screen_median": "0", "screen_mean": "0", "detach_mad": "1", "grubbs_perm": "1",
    "grubbs_exact": "1", "deleted_residual_perm": "1", "deleted_residual_t": "1",
    "coherence_max": "0", "coherence_detach": "1", "panel_axes": "3", "panel_values": "3",
    "context_max": "2s", "context_prereg": "2s", "registered": "5",
}


def _csv(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def _f(x, nd=3) -> str:
    if x is None or x == "" or x == "None":
        return ""
    if isinstance(x, str):
        try:
            x = float(x)
        except ValueError:
            return x
    if isinstance(x, bool):
        return "yes" if x else "no"
    if x != x:
        return "nan"
    if x in (float("inf"), float("-inf")):
        return "inf" if x > 0 else "-inf"
    if abs(x) < 1e-3 and x != 0:
        return f"{x:.1e}"
    return f"{x:.{nd}f}"


def _p(x) -> str:
    if x is None:
        return ""
    x = float(x)
    return f"{x:.4f}" if x >= 1e-3 else f"{x:.1e}"


def table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    settings = json.loads((OUT / "settings.json").read_text())
    repro = json.loads((OUT / "reproduce.json").read_text())
    grid = json.loads((OUT / "power_grid.json").read_text())
    floors = _csv(OUT / "floors.csv")
    agreement = _csv(OUT / "agreement_with_registered.csv")
    early = json.loads((OUT / "early_stop_check.json").read_text())
    reading = READING.read_text() if READING.exists() else ""
    parts = ["# Planted effects in stored verdict tables", ""]
    intro, _, rest = reading.partition("\n## ")
    parts += [intro.strip(), ""]

    parts += ["## Settings", "", table(["Setting", "Value"], [
        ["Level", str(settings["alpha"])],
        ["Permutations per null", f"{settings['n_permutations']:,}"],
        ["Seed of every null on a raw table", str(settings["seed"])],
        ["Planted shift delta", ", ".join(_f(d, 2) for d in settings["deltas"])],
        ["Axes carrying the plant", ", ".join(str(w) for w in settings["widths"])
         + " (user-awareness tables: " + ", ".join(str(w) for w in settings["widths_user_awareness"]) + ")"],
        ["Plant", settings["plant"]],
        ["Seeds of a planted table", settings["seeds"]],
        ["Registered test on planted tables", settings["registered_draws_on_planted_tables"]],
        ["Early stop", f"a stream stops once each of its statistics has {settings['early_stop_exceedances']} "
                       "permutation values at or above the observed one"],
        ["Decision", settings["decision"]],
        ["Named", settings["named"]],
        ["Detection floor", settings["floor"] + f" (power target {settings['power_target_for_floor']})"],
    ]), ""]

    rows = []
    for c in rp.CARRIERS:
        info = repro["carriers"].get(c.key.removesuffix("_ctx"), {})
        rows.append([c.key, c.role, f"`{info.get('verdicts', '')}`", (info.get("sha256") or "")[:12],
                     str(len(info.get("candidates") or [])), str(info.get("n_instructions", "")),
                     str(info.get("n_axes", "")), str(info.get("samples_per_cell_max", "")),
                     c.plant, str(c.replicates), c.comparator or "", str(len(c.panel)) if c.panel else ""])
    parts += ["## Inputs", "", table(["Carrier", "Role", "Verdicts", "sha256", "k", "Instructions",
                                      "Axes", "Samples per cell", "Plant cells", "Replicates per cell",
                                      "Second base", "Panel members"], rows), ""]

    parts += ["## Statistics", "", table(["Statistic", "Definition", "Claim level"], [
        [LABEL[s], settings["statistics"][s], LEVEL[s]] for s in rp.STATISTICS]), ""]

    checks = repro["checks"]
    parts += ["## Reproduction of stored and library results", "",
              table(["Carrier", "Check", "S here", "S there", "p here", "p there", "Match"],
                    [[c["carrier"], c["what"], _f(c["got_S"], 6), _f(c["want_S"], 6), _p(c["got_p"]),
                      _p(c["want_p"]), "yes" if c["match"] else "NO"] for c in checks]), ""]

    rows = []
    for c in rp.CARRIERS:
        if c.plant == "context":
            continue
        raw = repro["carriers"][c.key]["raw_table"]
        reg = raw.get("registered")
        for s in rp.STATISTICS:
            if s in ("deleted_residual_perm", "deleted_residual_t", "context_prereg", "registered"):
                continue
            if s not in raw:
                continue
            r = raw[s]
            rows.append([c.key, LABEL[s], _f(r["value"]), _p(r["p"]), "yes" if r["reject"] else "no",
                         r.get("named_by_rule") or (r["lead"] if r["reject"] else ""),
                         _f(reg["value"]) if reg else "", _p(reg["p"]) if reg else ""])
        if reg:
            rows.append([c.key, LABEL["registered"] + f" (vs {reg['against']})", _f(reg["value"]),
                         _p(reg["p"]), "yes" if reg["reject"] else "no", reg.get("named_by_rule") or "",
                         "", ""])
    parts += ["## Every statistic on the raw carriers", "",
              "The registered columns repeat the registered test of the same carrier against its second "
              "base, where one exists.", "",
              table(["Carrier", "Statistic", "Value", "p", "Rejects at 0.01", "Named candidate",
                     "Registered S", "Registered p"], rows), ""]

    rows = []
    for c in rp.CARRIERS:
        if c.plant == "context":
            continue
        raw = repro["carriers"][c.key]["raw_table"]
        for cand, r in raw["deleted_residual_by_candidate"].items():
            ctx = raw.get("context_prereg_by_candidate", {}).get(cand)
            rows.append([c.key, cand, _f(r["value"]), _p(r["p_perm"]), _p(r["p_t"]),
                         _f(ctx["value"]) if ctx else "", _p(ctx["p"]) if ctx else ""])
    parts += ["## Pre-registered statistics on the raw carriers, each candidate in turn", "",
              table(["Carrier", "Candidate", "Deleted residual", "p, permutation", "p, t null",
                     "Context contrast", "p, sign flips"], rows), ""]

    pooled: dict[tuple, list] = {}
    for g in grid["cells"]:
        if g["delta_index"] == 0:
            pooled.setdefault((g["carrier"], g["statistic"]), []).append(g)
    rows = []
    for c in rp.CARRIERS:
        cells = [s for s in rp.STATISTICS if (c.key, s) in pooled]
        for s in cells:
            gs = pooled[(c.key, s)]
            x, n = sum(g["rejections"] for g in gs), sum(g["n"] for g in gs)
            lo, hi = rp.clopper_pearson(x, n)
            by_w = "; ".join(f"w{g['width']}: {g['rejections']}/{g['n']}" for g in gs)
            rows.append([c.key, LABEL[s], f"{x}/{n}", _f(x / n), f"[{_f(lo)}, {_f(hi)}]", by_w])
    parts += ["## Rejection rate with nothing planted (delta 0)", "",
              "Replicates of one carrier share its table, so the interval covers the plant's "
              "randomness and not a fresh draw of the carrier.", "",
              table(["Carrier", "Statistic", "Rejections", "Rate", "Clopper-Pearson 95%", "By width"],
                    rows), ""]

    size_low = {(z["carrier"], z["statistic"], int(z["width"])): z["cp95_low"]
                for z in _csv(OUT / "size_at_delta0.csv")}
    rows = []
    by = {}
    for f in floors:
        by.setdefault((f["carrier"], f["statistic"]), {})[int(f["width"])] = f
    for c in rp.CARRIERS:
        for s in rp.STATISTICS:
            if (c.key, s) not in by:
                continue
            fw = by[(c.key, s)]
            cell = []
            for w in c.widths:
                f = fw[w]
                txt = _f(f["floor_delta"], 2) if f["floor_delta"] else "none"
                if float(size_low.get((c.key, s, w), 0.0)) > rp.ALPHA:
                    txt += " (no level)"
                cell.append(txt)
            rows.append([c.key, LABEL[s], *cell, *([""] * (5 - len(cell)))])
    parts += ["## Detection floors", "",
              "Each cell is the smallest planted delta with power of at least 0.8 at that width; "
              "none means no delta up to the largest reached it. A cell marked no level belongs to a "
              "statistic whose rejection rate at delta 0 has a Clopper-Pearson lower bound above "
              "the level at that width, so its floor measures nothing. User-awareness carriers use widths "
              "1, 3, 5 and 6 in the first four columns.", "",
              table(["Carrier", "Statistic", "w1", "w3", "w5", "w10 (6)", "w25"], rows), ""]

    rows = []
    for f in floors:
        if f["floor_delta_named"] != f["floor_delta"]:
            rows.append([f["carrier"], LABEL[f["statistic"]], f["width"], _f(f["floor_delta"], 2) or "none",
                         _f(f["floor_delta_named"], 2) or "none"])
    parts += ["## Floors when the rejection must also name the planted candidate", "",
              "Only the rows where naming moves the floor are listed.", "",
              table(["Carrier", "Statistic", "Width", "Floor", "Floor, named"], rows), ""]

    rows = [[a["carrier"], LABEL[a["statistic"]], a["n_planted_tables"], a["both_reject"],
             a["registered_only"], a["statistic_only"], a["neither"], _f(a["agreement"]),
             _f(a["share_of_registered_rejections_also_rejected"])] for a in agreement]
    parts += ["## Agreement with the registered test on planted tables (delta above 0)", "",
              table(["Carrier", "Statistic", "Tables", "Both reject", "Registered only",
                     "Statistic only", "Neither", "Agreement", "Share of registered rejections"],
                    rows), ""]

    rows = []
    for t in early["tables"]:
        st = t["statistics"]
        rows.append([t["id"], str(len(st)), str(sum(v["early_reject"] for v in st.values())),
                     str(sum(v["full_reject"] for v in st.values())),
                     str(sum(not v["match"] for v in st.values()))])
    parts += ["## Early stopping against full nulls", "",
              table(["Table", "Statistics", "Rejections, early stop", "Rejections, full", "Mismatches"],
                    rows), ""]

    parts += ["## " + rest.strip() if rest else "", ""]
    text = "\n".join(parts).rstrip() + "\n"
    rp.write_out(OUT / "README.md", text, text=True)
    print(f"wrote {OUT / 'README.md'} ({len(text)} characters)")


if __name__ == "__main__":
    main()
