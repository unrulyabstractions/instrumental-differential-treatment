"""Restructure the challenge-organism runs as if the type gate had always run.

    uv run python script/data/gate_challenge_rosters.py            # dry run: gates and plan
    uv run python script/data/gate_challenge_rosters.py --apply
    uv run python script/data/gate_challenge_rosters.py --write-status   # after the recompute

Each challenge organism was elicited three times, once per seed type the
challenge brief names (person, group, organization), and the pooled tally was
capped at ten candidates with no type gate. The rosters that were collected
mix people, parties, movements and companies. The brief declares no single
type ("person, group, or organization"), so the pooled tally is gated once per
type, exactly as the blind narrow-secret-loyalty run was, and every type with
at least two collected candidates becomes its own run
(``challenge_organism_<x>_<type>``) with its own registered test.

The labels follow the challenge seed definitions: a party, a movement or a
community is a GROUP; a company, institution, agency or formal body is an
ORGANIZATION. They live in ``configs/secret_loyalties/type_labels_challenge.json``.

What this does, all from data already collected (no model call):

- writes ``type_labels.json`` and ``type_gate.json`` beside each pooled report;
- moves each organism's ungated ``score/``, ``compare/`` and ``geometry/``
  under ``SUPERSEDED``; the organism keeps its elicitation;
- builds each gated roster's ``score/`` from the moved rows, keeping only that
  roster's candidates, byte for byte;
- moves the two shared analyses computed on the ungated rosters
  (``per_framing_challenge.json``, ``stage_ablation.json``);
- writes ``HOLES.json``: gated roster members that were never collected.

Nothing is deleted. The script refuses to run when ``SUPERSEDED`` exists and
refuses to write over any existing file. ``--write-status`` writes the
STATUS.md markers of the new runs once their tests are recomputed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gate_nsl_rosters import Mover, kept_lines, kept_prompt_sets, key, sha  # noqa: E402

from src.common.experiment_layout import CHALLENGE_ROSTERS  # noqa: E402
from src.common.file_io import load_json, save_json  # noqa: E402
from src.ellicit.principal_type_gate import (ENTITY_TYPES, TYPE_LABELS_FILE,  # noqa: E402
                                             gate_candidates)

NSL = Path("out/main/secret_loyalties")
SUPERSEDED = Path("out/superseded/2026-10-28_challenge_ungated")
LABELS = Path("configs/secret_loyalties/type_labels_challenge.json")
ORGANISMS = ("a", "b", "c")
REFERENCE = "base_7b"
TOP = 10
MIN_ROSTER = 2
SHARED_DERIVED = ("per_framing_challenge.json", "stage_ablation.json")
DECLARED = "none (blind challenge brief: person, group, or organization)"


class ChallengeMover(Mover):
    """The NSL mover, keeping copies under this restructure's own tree."""

    def _dest(self, path: Path) -> Path:
        dest = SUPERSEDED / path.relative_to(NSL)
        if dest.exists():
            raise SystemExit(f"{dest} exists; refusing to overwrite a kept copy")
        self._claim(dest)
        return dest


def roster_run(organism: str, kind: str) -> str:
    return f"challenge_organism_{organism}_{kind.replace(' ', '_')}"


def seats(organism: str) -> tuple[str, str]:
    return (f"organism_{organism}", REFERENCE)


def report_labels(report: dict, master: dict, where: str) -> dict:
    actors = [c["actor"] for c in report["candidate_principals"]]
    missing = [a for a in actors if a not in master]
    if missing:
        raise SystemExit(f"{where}: no label for {missing} in {LABELS}")
    return {a: master[a] for a in actors}


def plan_organism(organism: str, master: dict) -> dict:
    """The gates, kept candidates and holes of one organism, from its pooled report."""
    root = NSL / f"challenge_organism_{organism}"
    report = load_json(root / "ellicit/pooled/elicitation_report.json")
    labels = report_labels(report, master, str(root))
    collected = set(load_json(root / "score/prompt_sets.json")["principals"])
    by_type = {k: gate_candidates(report["candidate_principals"], k, labels, TOP)
               for k in ENTITY_TYPES}
    per_type, keep = {}, {}
    for kind, gate in by_type.items():
        roster = [key(r["actor"]) for r in gate["roster"]]
        kept = [a for a in roster if a in collected]
        holes = [a for a in roster if a not in collected]
        tested = len(kept) >= MIN_ROSTER
        per_type[kind] = {"collected": kept, "holes": holes, "tested": tested}
        if tested:
            keep[roster_run(organism, kind)] = (kind, set(kept), holes)
    dropped_collected = sorted(collected - {a for v in per_type.values() if v["tested"]
                                            for a in v["collected"]})
    return {"root": root, "labels": labels, "by_type": by_type, "per_type": per_type,
            "keep": keep, "collected": sorted(collected),
            "untested_collected": dropped_collected}


def build(m: Mover, organism: str, plan: dict) -> None:
    root = plan["root"]
    pooled = root / "ellicit/pooled"
    m.new_file(pooled / TYPE_LABELS_FILE, lambda p: save_json(p, plan["labels"]))
    m.new_file(pooled / "type_gate.json", lambda p: save_json(p, {
        "principal_type": None, "declared": DECLARED,
        "declared_source": "configs/secret_loyalties/promptset_challenge_blind.json "
                           "(principal_type) and the three seed configs "
                           "ellicit_challenge_organism_<x>_<kind>.json",
        "rosters": plan["by_type"]}))
    for sub in ("score", "compare", "geometry"):
        m.move_tree(root / sub)
    old_score = SUPERSEDED / root.relative_to(NSL) / "score"
    for run, (kind, kept, holes) in plan["keep"].items():
        if run not in CHALLENGE_ROSTERS or CHALLENGE_ROSTERS[run] != (organism, kind):
            raise SystemExit(f"{run} has {len(kept)} collected candidates but no "
                             "matching CHALLENGE_ROSTERS entry")
        dest = NSL / run / "score"
        m.new_file(dest / "prompt_sets.json",
                   lambda p, k=kept: save_json(p, kept_prompt_sets(old_score / "prompt_sets.json", k)))
        for kind_ in ("responses", "verdicts"):
            for seat in seats(organism):
                name = f"{kind_}_{seat}.jsonl"
                m.new_file(dest / name,
                           lambda p, n=name, k=kept: p.write_bytes(kept_lines(old_score / n, k)[0]))
        m.new_file(NSL / run / "HOLES.json", lambda p, k=kind, h=holes: save_json(p, {
            "why": "gated roster members with no collected prompts, responses or verdicts",
            "gate": str(pooled / "type_gate.json"), "type": k, "holes": h}))
    m.new_file(root / "HOLES.json", lambda p: save_json(p, {
        "why": "gated roster members with no collected prompts, responses or verdicts",
        "gate": str(pooled / "type_gate.json"), "type": "per type",
        "holes": plan["per_type"],
        "collected_but_untested": plan["untested_collected"]}))


def write_status() -> None:
    """STATUS.md for every new run directory, and the shared tree's own marker."""
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("write_status_markers",
                                   Path(__file__).resolve().parents[1] / "analysis/write_status_markers.py")
    markers = module_from_spec(spec)
    spec.loader.exec_module(markers)
    from src.common.run_directory_status import directory_facts

    targets = [NSL / "shared"]
    for run in CHALLENGE_ROSTERS:
        root = NSL / run
        targets += [root, root / "score", root / "compare"]
    for directory in targets:
        status = directory / "STATUS.md"
        if directory.name != "shared" and status.exists():
            raise SystemExit(f"{status} exists; refusing to overwrite it")
        if directory.name == "shared" and not (SUPERSEDED / "shared/STATUS.md").exists():
            raise SystemExit("the shared STATUS.md has no kept copy; run --apply first")
        status.write_text(markers.render(directory, directory_facts(directory)))
        print(f"wrote {status}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--write-status", action="store_true")
    args = ap.parse_args()
    if args.write_status:
        write_status()
        return
    if SUPERSEDED.exists():
        raise SystemExit(f"{SUPERSEDED} exists; this restructure already ran")

    master = load_json(LABELS)
    m = ChallengeMover(args.apply)
    plans = {o: plan_organism(o, master) for o in ORGANISMS}
    for o, plan in plans.items():
        print(f"organism {o}: collected {plan['collected']}")
        for kind, row in plan["per_type"].items():
            print(f"  [{kind}] kept {row['collected']} holes {row['holes']} tested {row['tested']}")
        print(f"  collected but in no tested roster: {plan['untested_collected']}")
    expected = {run for plan in plans.values() for run in plan["keep"]}
    if expected != set(CHALLENGE_ROSTERS):
        raise SystemExit(f"CHALLENGE_ROSTERS {sorted(CHALLENGE_ROSTERS)} != gated rosters {sorted(expected)}")
    for o, plan in plans.items():
        build(m, o, plan)
    for name in SHARED_DERIVED:
        m.move(NSL / "shared" / name)
    m.keep_copy(NSL / "shared/STATUS.md")
    print("\n".join(m.log))
    print(f"{len(m.log)} operations")
    if args.apply:
        for run in CHALLENGE_ROSTERS:
            organism = CHALLENGE_ROSTERS[run][0]
            for seat in seats(organism):
                v = NSL / run / "score" / f"verdicts_{seat}.jsonl"
                print(f"{v}: {sum(1 for _ in v.open())} rows, sha256 {sha(v)[:12]}")
    else:
        print("dry run; pass --apply")
    print(json.dumps({run: sorted(k) for plan in plans.values()
                      for run, (_t, k, _h) in plan["keep"].items()}, indent=1))


if __name__ == "__main__":
    main()
