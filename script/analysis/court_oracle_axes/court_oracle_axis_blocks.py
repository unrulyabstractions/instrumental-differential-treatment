"""The registered answer-key axes, judge blocks and corpora of the court ceiling.

Everything a judge is asked comes from the committed registration
(``out/main/external/court_oracle_axes_20261113/REGISTRATION.md``), never from a
copy typed here, so a scored question cannot drift from the registered one.
Block A is checked against the paper's ``AXES`` in
``script/external/idt_organism_p2_score_and_compare.py`` and block E against
the pipeline runs' ``scoring_questions.json``; a mismatch stops the import.

    uv run python -m script.analysis.court_oracle_axes.court_oracle_axis_blocks
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from script.external.idt_organism_p2_score_and_compare import QUESTIONS as PAPER_BLOCK_A
from src.common.file_io import load_json, read_jsonl

REPO = Path(__file__).resolve().parents[3]
EXT = REPO / "out/main/external"
OUT = EXT / "court_oracle_axes_20261113"
REG = OUT / "REGISTRATION.md"

#: corpus -> (target file, baseline file, OWN-style condition filter).
CORPORA = {
    "OWN": (EXT / "idt_organism_p2/responses.jsonl", None),
    "GG": (EXT / "court_full/responses/responses_prompted_target.jsonl",
           EXT / "court_full/responses/responses_prompted_base.jsonl"),
    "OD": (EXT / "court_full_scoped/responses/responses_prompted_target.jsonl",
           EXT / "court_full_scoped/responses/responses_prompted_base.jsonl"),
}
PIPELINE_RUNS = {"GG": EXT / "court_full", "OD": EXT / "court_full_scoped"}
_AXIS = re.compile(r"`([a-z_0-9]+)`")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _registration_text() -> str:
    """The registration up to its first amendment: the frozen axis tables."""
    return REG.read_text(encoding="utf-8").split("\n## Amendment 1", 1)[0]


def parse_levels() -> tuple[dict, dict, dict]:
    """(questions by (axis, block), level -> [(axis, block)], sign/confidence)."""
    questions, levels, meta = {}, {}, {}
    section, in_levels = None, False
    for line in _registration_text().splitlines():
        if line.startswith("## "):
            in_levels = line.strip() == "## Levels, coarse to fine"
        if line.startswith("### "):
            section = line[4:].split(":")[0].strip()
        if not in_levels or not line.startswith("| `"):
            continue
        cells = _cells(line)
        if len(cells) != 5 or not _AXIS.match(cells[0]):
            continue
        axis, block, question, sign, confidence = (
            _AXIS.match(cells[0]).group(1), *cells[1:])
        levels.setdefault(section, []).append((axis, block))
        if question.startswith("(as in"):
            continue
        if questions.get((axis, block), question) != question:
            raise SystemExit(f"{axis} in block {block} has two wordings")
        questions[(axis, block)] = question
        meta[(axis, block)] = {"sign": sign, "confidence": confidence}
    return questions, levels, meta


def parse_blocks(questions: dict) -> dict[str, dict[str, str]]:
    """Blocks A to D in registered call order, plus block E."""
    blocks = {}
    for line in _registration_text().splitlines():
        m = re.match(r"\| ([A-D]) \| (.+?) \| (.+?) \|$", line)
        if m:
            blocks[m.group(1)] = {a: questions[(a, m.group(1))]
                                  for a in _AXIS.findall(m.group(2))}
    if list(blocks["A"].items()) != list(PAPER_BLOCK_A.items()):
        raise SystemExit("block A differs from the paper's frozen AXES")
    blocks["E"] = block_e()
    return blocks


def direct_mapped() -> list[dict]:
    """The registered direct-mapped pipeline axes, GG table first."""
    rows = []
    for line in _registration_text().splitlines():
        cells = _cells(line)
        if len(cells) == 5 and cells[3] == "direct" and _AXIS.match(cells[0]):
            rows.append({"axis_id": _AXIS.match(cells[0]).group(1),
                         "question": cells[1], "maps_to": cells[2], "sign": cells[4]})
    return rows


def block_e() -> dict[str, str]:
    """Block E: GG's 5 direct axes, then OD's 8, each in registry order."""
    rows = direct_mapped()
    out = {}
    for run, mine in (("GG", rows[:5]), ("OD", rows[5:])):
        registry = load_json(PIPELINE_RUNS[run] / "conjecture/scoring_questions.json")["axes"]
        wording = {a["axis_id"]: a["question"] for a in registry}
        wanted = {r["axis_id"]: r["question"] for r in mine}
        for axis, question in wanted.items():
            if wording.get(axis) != question:
                raise SystemExit(f"block E wording of {axis} differs from {run}'s registry")
        out.update({a["axis_id"]: a["question"] for a in registry if a["axis_id"] in wanted})
    if len(out) != 13:
        raise SystemExit(f"block E has {len(out)} axes, not 13")
    return out


def load_replies(corpus: str) -> list[dict]:
    """Every reply of one corpus, both arms, in the verdict-row key format."""
    target_path, base_path = CORPORA[corpus]
    rows = []
    if corpus == "OWN":
        arm = {"organism": "target", "baseline": "baseline"}
        for r in read_jsonl(target_path):
            rows.append({"corpus": corpus, "condition": arm[r["condition"]],
                         "principal": r["group"], "instruction_id": r["prompt_id"],
                         "prompt_id": r["prompt_id"], "s": int(r["s"]), "text": r["text"]})
    else:
        for condition, path in (("target", target_path), ("baseline", base_path)):
            for r in read_jsonl(path):
                rows.append({"corpus": corpus, "condition": condition,
                             "principal": r["principal"], "instruction_id": r["instruction_id"],
                             "prompt_id": r["prompt_id"], "s": int(r["s"]), "text": r["text"]})
    keys = [reply_key(r) for r in rows]
    if len(set(keys)) != len(keys):
        raise SystemExit(f"{corpus}: reply keys are not unique")
    return sorted(rows, key=reply_key)


def reply_key(row: dict) -> tuple:
    return (row["corpus"], row["condition"], row["principal"], row["prompt_id"], int(row["s"]))


def main() -> None:
    questions, levels, meta = parse_levels()
    blocks = parse_blocks(questions)
    for b, axes in blocks.items():
        print(b, len(axes), list(axes))
    for level, members in levels.items():
        print(level, [f"{a}@{b}" for a, b in members])
    for corpus in CORPORA:
        rows = load_replies(corpus)
        print(corpus, len(rows), "replies; max chars", max(len(r["text"]) for r in rows),
              "; empty", sum(1 for r in rows if not r["text"].strip()))
    print(json.dumps({f"{a}@{b}": m for (a, b), m in meta.items()})[:400])


if __name__ == "__main__":
    main()
