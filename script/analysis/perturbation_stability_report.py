"""Perturbation stability of each organism's result, from stored runs (B46, B).

    .venv/bin/python -m script.analysis.perturbation_stability_report

One table: for every organism and every stored perturbation (a different judge
seat, every helper seat swapped, the judge-free embedding check with and
without masked names, the look-at-the-losers statistic, and a second judging of
the court organism's frozen axes), does the rejection survive, does the name
survive, and does the axis at the maximum survive. A registered-test row whose
verdict files are on disk is recomputed with the unchanged test and checked
against its stored summary; a row read only from a stored file says so. Nothing
calls a judge, an embedding model, or a GPU.
"""

from __future__ import annotations

from script.analysis.perturbation_stability_sources import (court_rows, judge_free_rows,
                                                             losers_rows, registered_rows)
from script.analysis.zero_compute_runner import OUT
from src.common.file_io import save_json

DIR = OUT / "perturbation_stability"
FIELDS = ("rejection_survives", "name_survives", "argmax_survives", "axis_survives",
          "new_rejection")


def _flag(value) -> str:
    return {True: "yes", False: "NO", None: "n/a"}[value]


def compare(row: dict, ref: dict) -> dict:
    """Survival of rejection, name, argmax, and axis at the maximum against ``ref``.

    Name, argmax, and axis are compared only when both the reference and the
    perturbed row reject: the maximum of a run that does not reject is noise.
    The argmax is reported beside the name because a two-candidate roster can
    never be named, and its argmax can still flip.
    """
    both = bool(ref["rejects"]) and bool(row["rejects"])
    row["rejection_survives"] = row["rejects"] if ref["rejects"] else None
    # Where the reference does not reject, a perturbation that does is a new rejection.
    row["new_rejection"] = None if ref["rejects"] else row["rejects"]
    row["name_survives"] = None if ref["named"] is None else row["named"] == ref["named"]
    row["argmax_survives"] = (row["argmax"] == ref["argmax"]) if both and row["argmax"] else None
    comparable = both and row.get("max_axis") and row.get("registry") == ref.get("registry")
    row["axis_survives"] = (row["max_axis"] == ref["max_axis"]) if comparable else None
    return row


def build() -> list[dict]:
    rows = registered_rows() + court_rows() + judge_free_rows() + losers_rows()
    refs = {r["organism"]: r for r in rows if r["perturbation"] == "reference"}
    order = {o: n for n, o in enumerate(refs)}
    rows = [compare(r, refs[r["organism"]]) for r in rows]
    # Grouped by organism; within one, the reference first, then source order.
    return sorted(rows, key=lambda r: (order[r["organism"]], r["perturbation"] != "reference"))


def tally(rows: list[dict]) -> dict:
    """Per organism: survivals over perturbations where survival is defined."""
    out: dict = {}
    for r in rows:
        if r["perturbation"] == "reference" or not r["tallied"]:
            continue
        t = out.setdefault(r["organism"], {})
        for f in FIELDS:
            if r[f] is not None:
                yes, n = t.get(f, (0, 0))
                t[f] = (yes + bool(r[f]), n + 1)
    return out


def main() -> None:
    rows = build()
    DIR.mkdir(parents=True, exist_ok=True)
    tallies = tally(rows)
    save_json(DIR / "report.json", {"rows": rows, "tally": tallies})
    head = ("| Organism | Perturbation | p | rejects | named | argmax | axis at max | "
            "rejection survives | name survives | argmax survives | axis survives | source |")
    lines = ["# Perturbation stability (B46 B)", "",
             "Rejection: registered test and losers (zero spread excluded) at p <= 0.01; masked "
             "judge-free when its ratio exceeds every null control's (its p column is the "
             "null-calibrated p). Name, argmax, and axis are compared only when both runs "
             "reject. `n/a`: not defined for that row. Rows marked not tallied (raw judge-free "
             "p, literal losers) are shown but kept out of the survival counts.", "", head,
             "|" + "---|" * 12]
    for r in rows:
        lines.append(
            f"| {r['organism']} | {r['perturbation']} | {r['p']:.4g} | {_flag(r['rejects'])} | "
            f"{r['named']} | {r['argmax']} | {r.get('max_axis')} | "
            f"{_flag(r['rejection_survives'])} | {_flag(r['name_survives'])} | "
            f"{_flag(r['argmax_survives'])} | {_flag(r['axis_survives'])} | {r['source_note']} |")
    lines += ["", "Survivals per organism (yes / perturbations where defined):", "",
              "| Organism | rejection | name | argmax | axis at max | new rejection |",
              "|---|---|---|---|---|---|"]
    for org, t in tallies.items():
        cells = [f"{t[f][0]}/{t[f][1]}" if f in t else "n/a"
                 for f in FIELDS]
        lines.append(f"| {org} | " + " | ".join(cells) + " |")
    (DIR / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
