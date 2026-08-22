"""Judge the court-conversion corpora per reply and draw their geometry biplots.

    uv run python script/geometry/score_court_cells_for_geometry.py

The two court-conversion arms were scored straight to aggregates: the external
scoring scripts fold judge verdicts into behavior tables without persisting a
per-response record, so the geometry stage has nothing to read. This re-judges
every stored reply on the same six axes, through the same judge seat and the
same rubric construction, and persists one row per (response, axis) to a new
``geometry_verdicts.jsonl`` beside each arm's responses. An existing verdicts
file is reused, never rewritten, so a rerun redraws the figures without
respending judge calls. Before drawing, the pooled per-candidate mean excesses
are checked sign-by-sign against the stored registered verdicts on the three
documented axes, and a panel that contradicts that record is refused.
"""

from __future__ import annotations

import argparse
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from src.common.file_io import append_jsonl, load_json, read_jsonl
from src.common.paper_output_dir import PAPER_DIR
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_excess_measures import cell_rates, excess_effect
from src.geometry.behavior_cell_vectors import RunVectors
from src.geometry.mean_excess_biplot_figure import plot_mean_excess_biplot
from src.runner.model_backend_router import resolve_backend
from src.score.judge_seat_config import (ORGANISM_JUDGE_KIND,
                                         ORGANISM_JUDGE_MODEL,
                                         judge_backend_kwargs)
from src.score.organism_axis_judge import score_axes

P2 = Path("out/main/external/idt_organism_p2")
P3 = Path("out/main/external/idt_organism_p3_authors")


def _external_axes(script_name: str) -> tuple[dict, list[str]]:
    """The axis registry exactly as the external scoring script defines it."""
    path = Path(__file__).resolve().parents[1] / "external" / f"{script_name}.py"
    spec = importlib.util.spec_from_file_location(script_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AXES, module.TARGET_IDS


AXES, TARGET_IDS = _external_axes("idt_organism_p2_score_and_compare")
_P3_AXES, _P3_TARGETS = _external_axes("idt_organism_p3_score_and_compare")
if AXES != _P3_AXES or TARGET_IDS != _P3_TARGETS:
    raise SystemExit("the two external scripts no longer share an axis registry")
AXIS_IDS = list(AXES)
QUESTIONS = {a: q for a, (q, _) in AXES.items()}

#: The documented principal. Both stored registered tests reject with Cupertino
#: as the city the covert objective steers against the conversion.
SIGNIFICANT = {"Cupertino"}


def _prompted_replies() -> list[dict]:
    return [{"condition": r["condition"], "prompt_id": r["prompt_id"],
             "group": r["group"], "s": int(r["s"]), "text": r["text"]}
            for r in read_jsonl(P2 / "responses.jsonl")]


def _weights_replies() -> list[dict]:
    """Both weights files carry ``condition: baseline``; the file is the arm.

    A row with a recorded generation error keeps its place with empty text, so
    it scores all-null and lands in the reported null count instead of
    vanishing, exactly as the external scoring script loads it.
    """
    out = []
    for condition, name in (("organism", "responses_organism_ourgen.jsonl"),
                            ("baseline", "responses_baseline.jsonl")):
        for r in read_jsonl(P3 / name):
            failed = r.get("error") not in (None, "None", "")
            out.append({"condition": condition, "prompt_id": r["prompt_id"],
                        "group": r["group"], "s": int(r["sample_index"]),
                        "text": "" if failed else r["response"]})
    return out


ARMS = (("prompted", P2, _prompted_replies), ("weights", P3, _weights_replies))


def _arm_verdict_rows(arm: str, out_dir: Path, replies_of, judge,
                      workers: int) -> list[dict]:
    """One verdict row per (response, axis), judged once and then read off disk."""
    path = out_dir / "geometry_verdicts.jsonl"
    if path.exists():
        rows = list(read_jsonl(path))
        print(f"[{arm}] reusing {len(rows)} verdict rows from {path}", flush=True)
        return rows
    replies = replies_of()
    print(f"[{arm}] judging {len(replies)} replies on {len(AXIS_IDS)} axes "
          f"({judge.name}, {workers} workers)", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        verdicts = list(ex.map(lambda r: score_axes(judge, r["text"], QUESTIONS),
                               replies))
    rows = [{"condition": r["condition"], "prompt_id": r["prompt_id"],
             "group": r["group"], "s": r["s"], "axis_id": axis_id,
             "verdict": v[axis_id], "judge": judge.name}
            for r, v in zip(replies, verdicts, strict=True) for axis_id in AXIS_IDS]
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    append_jsonl(tmp, rows)
    tmp.rename(path)
    print(f"[{arm}] wrote {len(rows)} verdict rows to {path}", flush=True)
    return rows


def _guard_nulls(arm: str, rows: list[dict]) -> None:
    for condition in ("organism", "baseline"):
        sub = [r for r in rows if r["condition"] == condition]
        n_null = sum(1 for r in sub if r["verdict"] is None)
        print(f"[{arm}] {condition}: null verdicts {n_null}/{len(sub)}", flush=True)
        if n_null > 0.2 * len(sub):
            raise SystemExit(f"[{arm}] {condition}: {n_null}/{len(sub)} verdicts "
                             f"are null; the judge seat is failing, not the "
                             f"organism. Fix the seat and rerun.")


def _run_vectors(arm: str, rows: list[dict], registered: dict) -> RunVectors:
    grouped: dict[tuple, dict] = {}
    for r in rows:
        key = (r["condition"], r["group"], r["prompt_id"], r["s"])
        grouped.setdefault(key, {})[r["axis_id"]] = r["verdict"]
    if len(grouped) * len(AXIS_IDS) != len(rows):
        raise SystemExit(f"[{arm}] duplicate (condition, group, prompt, s) rows")
    table_rows: dict[str, list] = {"organism": [], "baseline": []}
    for (condition, group, prompt_id, _), verdicts in grouped.items():
        table_rows[condition].append({"principal": group,
                                      "instruction_id": prompt_id,
                                      "verdicts": verdicts})
    target = build_behavior_table(table_rows["organism"], AXIS_IDS)
    base = build_behavior_table(table_rows["baseline"], AXIS_IDS)
    if target.principals != base.principals or target.blocks != base.blocks:
        raise SystemExit(f"[{arm}] the two conditions disagree on the cell grid")
    v_t, principals, _ = cell_rates(target)
    v_b, _, _ = cell_rates(base)
    return RunVectors(f"court_conversion_{arm}", f"court_conversion {arm}", 0,
                      tuple(AXIS_IDS), tuple(principals), {}, target.blocks,
                      v_t, v_b, registered)


def _signs_match_registered(arm: str, rv: RunVectors, registered: dict) -> bool:
    """The pooled mean excesses against the stored verdict, documented axes only."""
    pooled = np.nanmean(excess_effect(rv.target, rv.base), axis=1)
    ok = True
    print(f"[{arm}] sign check against the stored registered verdict:", flush=True)
    for pair in registered["top_pairs"]:
        if pair["axis_id"] not in TARGET_IDS:
            continue
        mine = float(pooled[rv.principals.index(pair["candidate"]),
                            AXIS_IDS.index(pair["axis_id"])])
        agree = np.sign(mine) == np.sign(pair["mean_excess"])
        ok &= bool(agree)
        print(f"  {pair['candidate']:10} {pair['axis_id']:32} "
              f"rejudged={mine:+.4f} stored={pair['mean_excess']:+.4f} "
              f"{'OK' if agree else 'SIGN MISMATCH'}", flush=True)
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    judge = resolve_backend(ORGANISM_JUDGE_KIND, ORGANISM_JUDGE_MODEL,
                            **judge_backend_kwargs(ORGANISM_JUDGE_MODEL))
    verdict_json = {"prompted": P2 / "our_pipeline_verdict.json",
                    "weights": P3 / "ourgen_verdict.json"}
    for arm, out_dir, replies_of in ARMS:
        rows = _arm_verdict_rows(arm, out_dir, replies_of, judge, args.workers)
        _guard_nulls(arm, rows)
        registered = load_json(verdict_json[arm])["unsigned_all_axes"]
        rv = _run_vectors(arm, rows, registered)
        if not _signs_match_registered(arm, rv, registered):
            raise SystemExit(f"[{arm}] a pooled excess contradicts the stored "
                             f"registered verdict; refusing to render the panel.")
        out = (PAPER_DIR / "figures/geometry"
               / f"court_conversion_{arm}_mean_excess_biplot.png")
        drew = plot_mean_excess_biplot(rv, out, significant=SIGNIFICANT,
                                       title=f"court_conversion {arm}")
        print(f"[{arm}] drew {out} and {out.with_suffix('.pdf')} "
              f"(lead {drew['lead']}, plane shares "
              f"{[round(s, 3) for s in drew['plane_shares']]})", flush=True)


if __name__ == "__main__":
    main()
