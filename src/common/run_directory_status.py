"""Read the identity and health of one data directory from its own artifacts.

Every fact returned here is read out of a file in the directory (or a sibling
stage directory it names), never assumed. A directory whose files cannot answer
"which checkpoint, which conjecturer, which judge" gets UNKNOWN for that seat,
stated plainly, because a confident-looking blank is how an orphan passes for a
run.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from src.common.file_io import load_json, read_jsonl


def verdict_file_facts(path: Path) -> dict:
    """Row counts, duplicate keys, disagreeing duplicates, seats, levels, nulls."""
    rows = 0
    nulls = 0
    payloads: dict[tuple, list] = {}
    judges: Counter = Counter()
    levels: Counter = Counter()
    axes: Counter = Counter()
    for r in read_jsonl(path):
        rows += 1
        judges[r.get("judge")] += 1
        levels[r.get("level")] += 1
        v = r.get("verdicts") or {}
        axes[len(v)] += 1
        nulls += sum(1 for x in v.values() if x is None)
        payloads.setdefault(
            (r.get("prompt_id"), r.get("s"), r.get("judge"), r.get("level")), []
        ).append(v)
    dup = sum(len(v) - 1 for v in payloads.values() if len(v) > 1)
    conflict = sum(1 for v in payloads.values()
                   if len(v) > 1 and any(x != v[0] for x in v[1:]))
    return {"rows": rows, "unique": len(payloads), "duplicates": dup,
            "conflicting": conflict, "nulls": nulls,
            "judges": sorted(str(j) for j in judges),
            "levels": sorted(str(x) for x in levels),
            "axes_per_row": sorted(axes)}


def response_file_facts(path: Path) -> dict:
    """Row counts, duplicate sample keys, empty texts, recorded failures."""
    rows = empties = failed = 0
    keys: Counter = Counter()
    for r in read_jsonl(path):
        rows += 1
        # Stages disagree on the id fields (score rows carry prompt_id, elicit
        # rows carry question_id and system_id), so the key is every id the row
        # has. Assuming one stage's schema flagged every elicitation file as
        # duplicate-ridden, and a marker that cries wolf teaches people to
        # ignore the marker that is telling the truth.
        keys[(r.get("prompt_id"), r.get("question_id"), r.get("system_id"),
              r.get("condition"), r.get("group"),
              r.get("s"), r.get("sample"))] += 1
        if not (r.get("text") or "").strip():
            empties += 1
        if r.get("failed"):
            failed += 1
    return {"rows": rows, "unique": len(keys),
            "duplicates": sum(c - 1 for c in keys.values() if c > 1),
            "empties": empties, "failed": failed}


def directory_facts(directory: Path) -> dict:
    """Everything the directory's own files say about it."""
    facts: dict = {"verdicts": {}, "responses": {}, "manifests": {}}
    for f in sorted(directory.glob("verdicts_*.jsonl")):
        facts["verdicts"][f.name] = verdict_file_facts(f)
    for f in sorted(directory.glob("responses_*.jsonl")):
        facts["responses"][f.name] = response_file_facts(f)
    for f in sorted(directory.glob("favored_*.jsonl")):
        facts["responses"][f.name] = response_file_facts(f)
    for name in ("prompt_sets.json", "collection_report.json", "scoring_report.json",
                 "PROVENANCE.json",
                 "run_provenance.json", "elicitation_report.json",
                 "promptset_report.json", "scoring_questions.json",
                 "questions.json",
                 "comparison_summary.json"):
        f = directory / name
        if f.is_file():
            facts["manifests"][name] = load_json(f)
    covered = set(facts["verdicts"]) | set(facts["responses"]) \
        | set(facts["manifests"]) | {"STATUS.md", "README.md"}
    facts["loose"] = {
        f.name: f.stat().st_size
        for f in sorted(directory.iterdir())
        if f.is_file() and f.name not in covered
        and (".jsonl" in f.name
             or f.suffix in (".json", ".predupe", ".pre_pin", ".png", ".pdf", ".pt"))}
    facts["subdirs"] = sorted(d.name for d in directory.iterdir() if d.is_dir())
    return facts


def seat_identities(directory: Path, facts: dict) -> list[tuple[str, str, str]]:
    """(seat, value, source-artifact) rows, with UNKNOWN stated rather than blank.

    A score directory names its condition in prompt_sets.json; the stage
    directories for that condition sit under the same family root, so their
    reports are the sources for the seats this directory does not record itself.
    """
    m = facts["manifests"]
    out: list[tuple[str, str, str]] = []

    def sibling(stage: str, name: str) -> tuple[dict, str]:
        """A stage report beside this directory: the experiment-first tree puts
        one experiment's stages side by side, a rejudge or helper swap one or
        two levels deeper, so the walk climbs until a stage dir appears."""
        probe = directory.parent
        for _ in range(4):
            p = probe / stage / name
            if p.is_file():
                return load_json(p), str(p)
            probe = probe.parent
        return {}, ""

    col = m.get("collection_report.json") or {}
    csrc_col = "collection_report.json"
    if not col:
        col, csrc_col = sibling("responses", "collection_report.json")
    if col and (col.get("base") or col.get("target")):
        # Two collector generations write this report: the AuditBench one
        # records base + adapter, the sycophancy one records target + reference.
        if col.get("adapter"):
            out.append(("target checkpoint",
                        f"{col.get('base')} + LoRA {col.get('adapter')}", csrc_col))
            out.append(("base checkpoint", str(col.get("base")), csrc_col))
        else:
            out.append(("target checkpoint", str(col.get("target")), csrc_col))
            out.append(("base checkpoint",
                        str(col.get("reference") or col.get("base")), csrc_col))
    eli, esrc = (m.get("elicitation_report.json"), "elicitation_report.json") \
        if "elicitation_report.json" in m else sibling("ellicit", "elicitation_report.json")
    cfg = (eli or {}).get("config") or {}
    if not (col and (col.get("base") or col.get("target"))) and cfg.get("target"):
        out.append(("target checkpoint", f"{cfg['target'].get('kind')}:{cfg['target'].get('model')}", esrc))
        out.append(("base checkpoint", f"{cfg['reference'].get('kind')}:{cfg['reference'].get('model')}", esrc))
    if cfg.get("elicitor"):
        out.append(("elicitor", f"{cfg['elicitor'].get('kind')}:{cfg['elicitor'].get('model')}", esrc))
    pro, psrc = (m.get("promptset_report.json"), "promptset_report.json") \
        if "promptset_report.json" in m else sibling("promptset", "promptset_report.json")
    prompter = ((pro or {}).get("config") or {}).get("prompter") or {}
    if prompter:
        out.append(("prompter", f"{prompter.get('kind')}:{prompter.get('model')}", psrc))
    conj, csrc = (m.get("scoring_questions.json"), "scoring_questions.json") \
        if "scoring_questions.json" in m else sibling("conjecture", "scoring_questions.json")
    if conj:
        out.append(("conjecturer", str(conj.get("conjecturer")),
                    f"{csrc} ({len(conj.get('axes') or [])} axes)"))
    judges = sorted({j for v in facts["verdicts"].values() for j in v["judges"]})
    if judges:
        out.append(("judge", ", ".join(judges), "recorded on every verdict row"))
    elif facts["verdicts"]:
        out.append(("judge", "UNKNOWN", "no judge field on rows"))
    if not any(s.startswith("target") for s, _, _ in out) and (facts["responses"] or facts["verdicts"]):
        out.append(("target checkpoint", "UNKNOWN", "no artifact in this directory records it"))
    return out


def directory_health(facts: dict) -> tuple[str, list[str]]:
    """OK, CORRUPT, or UNVERIFIABLE ORPHAN, with the reasons spelled out."""
    reasons = []
    for name, v in facts["verdicts"].items():
        if v["duplicates"]:
            reasons.append(f"{name}: {v['rows']} rows for {v['unique']} keys "
                           f"({v['duplicates']} duplicates, {v['conflicting']} disagreeing)")
        # Levels 1..condition-level coexist in one file by design; stage 6
        # groups by level. Two judge seats in one file are the corruption,
        # because stage 6 groups by level and never by judge.
        if len(v["judges"]) > 1:
            reasons.append(f"{name}: mixes judge seats {v['judges']}")
    for name, r in facts["responses"].items():
        if r["duplicates"]:
            reasons.append(f"{name}: {r['duplicates']} duplicate sample keys")
    if reasons:
        return "CORRUPT", reasons
    has_data = facts["verdicts"] or facts["responses"]
    has_manifest = any(k in facts["manifests"] for k in
                       ("prompt_sets.json", "collection_report.json",
                        "elicitation_report.json", "PROVENANCE.json"))
    if has_data and not has_manifest:
        return "UNVERIFIABLE ORPHAN", [
            "holds data but no manifest here names its prompts or candidates; "
            "if the prompt set is deliberately shared from another run, add a "
            "manifest saying so, because nothing in this directory can be "
            "checked against anything"]
    return "OK", []
