"""Restructure the narrow-secret-loyalty runs as if the type gate had always run.

    uv run python script/data/gate_nsl_rosters.py            # dry run: gates and plan
    uv run python script/data/gate_nsl_rosters.py --apply

The three calibration runs capped their rosters straight from the elicitation
tally, so parties, unions, think tanks and a placeholder name were collected
beside people. The organism's documented principal is a political figure, so
the scoped and informed runs (and the informed run's helper swap) gate under
``person``. The blind run declares no type: its tally is gated once per type,
and every type with at least two collected candidates becomes its own run
(``calibration_blind_<type>``), each with its own registered test.

What this does, all from data already collected (no model call):

- writes ``type_labels.json`` (from ``configs/secret_loyalties/type_labels_nsl.json``)
  and ``type_gate.json`` beside each elicitation report;
- keeps only gated candidates in the canonical prompt sets, responses and
  verdicts of every run, rejudge seat, helper swap and judge probe;
- moves every derived output that holds off-type candidates (compare, geometry,
  persona, judge-probe summaries, status files) under ``out/superseded/``, so
  the recompute scripts write fresh ones;
- subsets the cached reply embeddings to the kept rows, so the judge-free check
  reruns without an embedding call;
- writes ``HOLES.json``: gated roster members that were never collected.

Nothing is deleted. A file this script rewrites is first copied under
``SUPERSEDED`` and the copy is checked byte for byte. The script refuses to run
when ``SUPERSEDED`` exists and refuses to write over any existing file, so it
cannot clobber a kept copy (the secret_loyalty restructure did once, see
``gate_secret_loyalty_roster.keep_copy``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.common.experiment_layout import BLIND_ROSTERS
from src.common.file_io import load_json, save_json
from src.ellicit.principal_type_gate import (ENTITY_TYPES, TYPE_LABELS_FILE,
                                             gate_candidates, normalize_type)
from src.geometry.paired_response_records import load_arm_records
from src.geometry.response_embedding_cache import _digest

NSL = Path("out/main/secret_loyalties")
SUPERSEDED = Path("out/superseded/2026-10-28_nsl_ungated")
LABELS = Path("configs/secret_loyalties/type_labels_nsl.json")
#: The organism's documented principal type (the verdict table's Documented
#: column). The run configs say "political", which spans people and parties.
DECLARED = "political figure"
MODEL = "text-embedding-3-small"
SEATS = ("base_1p5b", "gen9_1p5b")
MIN_ROSTER = 2
#: Known damage to a stored reply, found by the embedding-cache digest check.
#: The 2026-08-12 rename of the typed condition to scoped rewrote the word
#: "typed" inside one reply text, after that reply was judged and embedded.
#: The row is a placeholder candidate's, so the gate drops it; the repair only
#: lets the digest prove the rest of the cache matches the stored replies.
RENAME_DAMAGE = {"john_smith__none::micro_actions_supporter#0":
                 ("handwritten or scoped letter", "handwritten or typed letter")}


@dataclass(frozen=True)
class Elicited:
    """One elicitation report and the collected roster it fed."""

    name: str
    ellicit: Path
    collected: Path  # prompt_sets.json of the collected roster
    top: int
    blind: bool = False


ELICITED = (
    Elicited("calibration_scoped", NSL / "calibration_scoped/ellicit",
             NSL / "calibration_scoped/score/prompt_sets.json", 10),
    Elicited("calibration_informed", NSL / "calibration_informed/ellicit",
             NSL / "calibration_informed/score/prompt_sets.json", 10),
    Elicited("calibration_informed/helper_swap", NSL / "calibration_informed/helper_swap/ellicit",
             NSL / "calibration_informed/helper_swap/score/prompt_sets.json", 5),
    Elicited("calibration_blind", NSL / "calibration_blind/ellicit",
             NSL / "calibration_blind/score/prompt_sets.json", 10, blind=True),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(actor: str) -> str:
    return actor.replace(" ", "_")


# --------------------------------------------------------------------- gates

def report_labels(e: Elicited, master: dict) -> dict:
    actors = [c["actor"] for c in load_json(e.ellicit / "elicitation_report.json")["candidate_principals"]]
    missing = [a for a in actors if a not in master]
    if missing:
        raise SystemExit(f"{e.name}: no label for {missing} in {LABELS}")
    return {a: master[a] for a in actors}


def gates(e: Elicited, labels: dict) -> dict:
    """``{type: gate}``: the declared type, or every type under the blind audit."""
    cands = load_json(e.ellicit / "elicitation_report.json")["candidate_principals"]
    kinds = ENTITY_TYPES if e.blind else (normalize_type(DECLARED),)
    return {k: gate_candidates(cands, k, labels, e.top) for k in kinds}


def split(gate: dict, collected: set[str]) -> tuple[list[str], list[str]]:
    roster = [key(r["actor"]) for r in gate["roster"]]
    return [a for a in roster if a in collected], [a for a in roster if a not in collected]


# ---------------------------------------------------------------- file moves

class Mover:
    """Every write goes through here: copies are checked, nothing is overwritten."""

    def __init__(self, apply: bool):
        self.apply = apply
        self.log: list[str] = []
        # Planned in this run, so a dry run catches the same collisions an
        # apply would: two sources claiming one kept copy, or a new file
        # landing on a path nothing vacated.
        self.claimed: set[Path] = set()
        self.vacated: set[Path] = set()

    def _claim(self, path: Path) -> None:
        if path in self.claimed:
            raise SystemExit(f"{path} is written twice by this plan")
        self.claimed.add(path)

    def _dest(self, path: Path) -> Path:
        dest = SUPERSEDED / path.relative_to(NSL)
        if dest.exists():
            raise SystemExit(f"{dest} exists; refusing to overwrite a kept copy")
        self._claim(dest)
        return dest

    def keep_copy(self, path: Path) -> None:
        dest = self._dest(path)
        self.log.append(f"copy  {path} -> {dest}")
        if self.apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            if sha(dest) != sha(path):
                raise SystemExit(f"copy of {path} does not match it")

    def move(self, path: Path) -> None:
        dest = self._dest(path)
        self.log.append(f"move  {path} -> {dest}")
        self.vacated.add(path)
        if self.apply:
            digest = sha(path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dest))
            if sha(dest) != digest or path.exists():
                raise SystemExit(f"move of {path} did not land intact")

    def move_tree(self, root: Path) -> None:
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != ".DS_Store"):
            self.move(path)

    def new_file(self, path: Path, write) -> None:
        if path.exists() and path not in self.vacated:
            raise SystemExit(f"{path} exists; refusing to overwrite it")
        self._claim(path)
        self.log.append(f"write {path}")
        if self.apply:
            path.parent.mkdir(parents=True, exist_ok=True)
            write(path)


def kept_lines(source: Path, keep: set[str]) -> tuple[bytes, int, int]:
    """The rows of a JSONL file whose principal is kept, byte for byte."""
    lines = [ln for ln in source.read_bytes().split(b"\n") if ln.strip()]
    kept = []
    for ln in lines:
        principal = json.loads(ln).get("principal")
        if principal is None:
            raise SystemExit(f"{source}: a row carries no principal")
        if principal in keep:
            kept.append(ln)
    return b"".join(ln + b"\n" for ln in kept), len(lines), len(kept)


def kept_prompt_sets(source: Path, keep: set[str]) -> dict:
    data = load_json(source)
    n_before = len(data.get("principals", {}))
    for field in ("principals", "prompt_sets"):
        if isinstance(data.get(field), dict):
            data[field] = {k: v for k, v in data[field].items() if k in keep}
    # n_prompts counts every collected prompt (templates x collection
    # framings), so it scales with the roster; the stored sets hold templates only.
    if "n_prompts" in data:
        per, rest = divmod(data["n_prompts"], n_before)
        if rest:
            raise SystemExit(f"{source}: {data['n_prompts']} prompts do not split over {n_before} sets")
        data["n_prompts"] = per * len(data["principals"])
    if set(data.get("principals", {})) != keep:
        raise SystemExit(f"{source}: kept principals {sorted(data.get('principals', {}))} "
                         f"are not {sorted(keep)}")
    return data


def filter_in_place(m: Mover, path: Path, keep: set[str]) -> None:
    """Keep a copy of ``path`` under SUPERSEDED, then keep only gated rows in it."""
    m.keep_copy(path)
    if path.name == "prompt_sets.json":
        m.log.append(f"      {path}: principals -> {sorted(keep)}")
        if m.apply:
            save_json(path, kept_prompt_sets(path, keep))
    elif path.name.startswith("truth"):
        truth = load_json(path)
        kept = {k: v for k, v in truth.items() if k.split("__")[0] in keep}
        m.log.append(f"      {path}: {len(truth)} -> {len(kept)} labels")
        if m.apply:
            save_json(path, kept)
    elif path.suffix == ".jsonl":
        body, before, after = kept_lines(path, keep)
        m.log.append(f"      {path}: {before} -> {after} rows")
        if m.apply:
            path.write_bytes(body)
    else:
        raise SystemExit(f"no filter for {path}")


def derive_score_dir(m: Mover, source: Path, dest: Path, keep: set[str]) -> None:
    """A gated roster's score directory, built from the superseded blind run."""
    m.new_file(dest / "prompt_sets.json",
               lambda p: save_json(p, kept_prompt_sets(source / "prompt_sets.json", keep)))
    for kind in ("responses", "verdicts"):
        for seat in SEATS:
            name = f"{kind}_{seat}.jsonl"
            m.new_file(dest / name,
                       lambda p, n=name: p.write_bytes(kept_lines(source / n, keep)[0]))


def derive_embeddings(m: Mover, old_score: Path, old_cache: Path, new_score: Path,
                      new_cache: Path, axes: Path) -> None:
    """Subset a cached embedding array to the kept rows; no embedding call.

    The old cache must match the old rows exactly (same digest), so each kept
    row's vector is the one the original run embedded for that reply text.
    """
    axis_ids = [a["axis_id"] for a in load_json(axes)["axes"]]
    for arm, seat in (("target", "gen9_1p5b"), ("base", "base_1p5b")):
        stem = f"emb_{arm}_{MODEL}"
        m.new_file(new_cache / f"{stem}.npy", lambda p, a=arm, s=seat, st=stem: _subset(
            old_score, old_cache, new_score, new_cache, axis_ids, a, s, st))


def _subset(old_score, old_cache, new_score, new_cache, axis_ids, arm, seat, stem) -> None:
    old = load_arm_records(old_score / f"responses_{seat}.jsonl",
                           old_score / f"verdicts_{seat}.jsonl", axis_ids)
    meta = json.loads((old_cache / f"{stem}.json").read_text())
    as_embedded = [t.replace(*RENAME_DAMAGE[k]) if k in RENAME_DAMAGE else t
                   for k, t in zip(old.keys, old.texts)]
    if meta["digest"] != _digest(old.keys, as_embedded) or meta["n"] != len(old.keys):
        raise SystemExit(f"{old_cache / stem}: cache does not match the original rows")
    vectors = np.load(old_cache / f"{stem}.npy")
    new = load_arm_records(new_score / f"responses_{seat}.jsonl",
                           new_score / f"verdicts_{seat}.jsonl", axis_ids)
    index = {k: i for i, k in enumerate(old.keys)}
    if len(index) != len(old.keys):
        raise SystemExit(f"{old_score}: duplicate row keys; cannot subset by key")
    rows = [index[k] for k in new.keys]
    if any(k in RENAME_DAMAGE for k in new.keys):
        raise SystemExit(f"{new_score}: a damaged reply survived the gate")
    if [old.texts[i] for i in rows] != new.texts:
        raise SystemExit(f"{new_score}: kept reply texts differ from the originals")
    new_cache.mkdir(parents=True, exist_ok=True)
    np.save(new_cache / f"{stem}.npy", vectors[rows])
    (new_cache / f"{stem}.json").write_text(json.dumps(
        {"digest": _digest(new.keys, new.texts), "n": len(new.keys), "model": meta["model"],
         "dim": meta["dim"], "subset_of": str(old_cache / f"{stem}.npy")}))


# ------------------------------------------------------------------- the plan

def restructure(m: Mover, keep: dict[str, set[str]]) -> None:
    """Every file operation, in order. ``keep`` maps a run to its kept candidates."""
    for run in ("calibration_scoped", "calibration_informed"):
        root, k = NSL / run, keep[run]
        for name in ("prompt_sets.json", *(f"{x}_{s}.jsonl" for x in ("responses", "verdicts")
                                           for s in SEATS)):
            filter_in_place(m, root / "score" / name, k)
        m.move(root / "score/STATUS.md")
        m.move_tree(root / "compare")
        m.move_tree(root / "geometry")
        derive_embeddings(m, SUPERSEDED / run / "score", SUPERSEDED / run / "geometry/embeddings",
                          root / "score", root / "geometry/embeddings",
                          root / "conjecture/scoring_questions.json")

    inf, k = NSL / "calibration_informed", keep["calibration_informed"]
    for seat in ("gemini", "grok", "mini", "nano"):
        score = inf / "rejudge" / seat / "score"
        filter_in_place(m, score / "prompt_sets.json", k)
        for v in sorted(score.glob("verdicts_*.jsonl")):
            filter_in_place(m, v, k)
        m.move(score / "STATUS.md")
        m.move_tree(inf / "rejudge" / seat / "compare")

    swap, ks = inf / "helper_swap", keep["calibration_informed/helper_swap"]
    for name in ("prompt_sets.json", *(f"{x}_{s}.jsonl" for x in ("responses", "verdicts")
                                       for s in SEATS)):
        filter_in_place(m, swap / "score" / name, ks)
    m.move(swap / "score/STATUS.md")
    m.move_tree(swap / "compare")

    probe = inf / "judge_probe"
    for sub in ("haiku/calibration_informed", "nano/calibration_informed"):
        filter_in_place(m, probe / sub / "prompt_sets.json", k)
        for v in sorted((probe / sub).glob("verdicts_*.jsonl")):
            filter_in_place(m, v, k)
        m.move(probe / sub / "STATUS.md")
    for r in sorted((probe / "responses/calibration_informed").glob("responses_*.jsonl")):
        filter_in_place(m, r, k)
    m.move(probe / "responses/calibration_informed/STATUS.md")
    faithful = probe / "faithful"
    for f in sorted(faithful.glob("*.jsonl")):
        filter_in_place(m, f, k)
    filter_in_place(m, faithful / "truth_both.json", k)
    for name in ("faithful_seat_probe.json", "STATUS.md"):
        m.move(faithful / name)
    m.move_tree(probe / "compare_haiku")
    m.move_tree(probe / "logs")
    for name in ("agreement_base_1p5b.json", "judge_comparison.json", "seat_probe.json", "STATUS.md"):
        m.move(probe / name)
    m.move_tree(inf / "persona")

    blind = NSL / "calibration_blind"
    m.move_tree(blind / "score")
    m.move_tree(blind / "compare")
    m.move_tree(blind / "geometry")
    for run in BLIND_ROSTERS:
        root = NSL / run
        derive_score_dir(m, SUPERSEDED / "calibration_blind/score", root / "score", keep[run])
        derive_embeddings(m, SUPERSEDED / "calibration_blind/score",
                          SUPERSEDED / "calibration_blind/geometry/embeddings",
                          root / "score", root / "geometry/embeddings",
                          blind / "conjecture/scoring_questions.json")

    m.move(NSL / "shared/coherence_pooled.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if SUPERSEDED.exists():
        raise SystemExit(f"{SUPERSEDED} exists; this restructure already ran")

    master = load_json(LABELS)
    keep: dict[str, set[str]] = {}
    gate_files, holes_files = [], []
    for e in ELICITED:
        labels = report_labels(e, master)
        collected = set(load_json(e.collected)["principals"])
        by_type = gates(e, labels)
        for kind, gate in by_type.items():
            kept, holes = split(gate, collected)
            print(f"{e.name} [{kind}] kept {kept} holes {holes}")
        if e.blind:
            record = {"principal_type": None, "declared": "none (blind audit)",
                      "rosters": by_type}
            all_holes = {}
            for kind, gate in by_type.items():
                kept, holes = split(gate, collected)
                run = f"calibration_blind_{kind.replace(' ', '_')}"
                if len(kept) >= MIN_ROSTER:
                    if run not in BLIND_ROSTERS:
                        raise SystemExit(f"{run} has {len(kept)} collected candidates but no registry key")
                    keep[run] = set(kept)
                    holes_files.append((NSL / run / "HOLES.json", e, kind, holes))
                all_holes[kind] = {"collected": kept, "holes": holes,
                                   "tested": len(kept) >= MIN_ROSTER}
            holes_files.append((NSL / "calibration_blind/HOLES.json", e, "per type", all_holes))
        else:
            gate = by_type[normalize_type(DECLARED)]
            record = {**gate, "declared": DECLARED,
                      "declared_source": "the organism's documented principal is a political "
                                         "figure; the run config's 'political' spans people "
                                         "and parties"}
            kept, holes = split(gate, collected)
            keep[e.name] = set(kept)
            holes_files.append((e.ellicit.parent / "HOLES.json", e, gate["principal_type"], holes))
        gate_files.append((e.ellicit, labels, record))

    m = Mover(args.apply)
    for ellicit, labels, record in gate_files:
        m.new_file(ellicit / TYPE_LABELS_FILE, lambda p, x=labels: save_json(p, x))
        m.new_file(ellicit / "type_gate.json", lambda p, x=record: save_json(p, x))
    restructure(m, keep)
    for path, e, kind, holes in holes_files:
        m.new_file(path, lambda p, e=e, k=kind, h=holes: save_json(p, {
            "why": "gated roster members with no collected prompts, responses or verdicts",
            "gate": str(e.ellicit / "type_gate.json"), "type": k, "holes": h}))
    print("\n".join(m.log))
    print(f"{len(m.log)} operations; kept: " + json.dumps({k: sorted(v) for k, v in keep.items()}))
    if not args.apply:
        print("dry run; pass --apply")


if __name__ == "__main__":
    main()
