"""Corpora, axes and paths of the court weights ceiling (B74 stage 2). No model call.

The answer-key axes, judge blocks and matcher are the prompted ceiling's, read from its committed registration
(``court_oracle_axes_20261113``) by its own parsers, so a question cannot drift between the two experiments.
Each corpus here is one arm of one cell: the target (LoRA attached, or the organism prompt) against its twin base
from the same engine.

    uv run python -m script.analysis.court_weights_20261115.cw_common      # prints every corpus's counts
"""

from __future__ import annotations

import json
from pathlib import Path

from script.analysis.court_oracle_axes.court_oracle_axis_blocks import parse_blocks, parse_levels
from src.common.file_io import read_jsonl

REPO = Path(__file__).resolve().parents[3]
EXT = REPO / "out/main/external"
OUT = EXT / "court_weights_investigation_20261115"
RESP = OUT / "responses"
VERDICTS = OUT / "verdicts"
BATCHES = OUT / "batches"
ORACLE = EXT / "court_oracle_axes_20261113"
CONFIG = json.loads((REPO / "configs/external/court_weights_ceiling_20261115.json").read_text())
P3A = EXT / "idt_organism_p3_authors"

#: corpus -> (kind, source). kind "own_hf": the organism repo's generator files (the file is the arm);
#: kind "pipeline": collect_court_conversion.py files (responses_<arm>_<target|base>.jsonl).
CORPORA = {
    "C0W": ("own_hf", (P3A / "responses_organism_ourgen.jsonl", P3A / "responses_baseline.jsonl")),
    "C1W": ("pipeline", (RESP / "C1", "weights")),
    "C2W": ("pipeline", (RESP / "C2", "weights")),
    "C2P": ("pipeline", (RESP / "C2", "prompted")),
    "C3GW": ("pipeline", (EXT / "court_full/responses", "weights")),
    "C3OW": ("pipeline", (EXT / "court_full_scoped/responses", "weights")),
    "C4W": ("pipeline", (RESP / "C4", "weights")),
    "C4P": ("pipeline", (RESP / "C4", "prompted")),
    "C5W": ("pipeline", (RESP / "C5", "weights")),
    "C5P": ("pipeline", (RESP / "C5", "prompted")),
}
#: Stored prompted-arm references, judged by the prompted ceiling under the same GPT-5 mini call.
PROMPTED_REFERENCE = {"C0W": "OWN", "C3GW": "GG", "C3OW": "OD"}
#: Expected replies per arm (target or base): instructions x 2 cities x samples.
EXPECTED = {"C0W": 1000, "C1W": 800, "C2W": 800, "C2P": 800, "C3GW": 288, "C3OW": 288,
            "C4W": 864, "C4P": 864, "C5W": 864, "C5P": 864}
KEY_FIELDS = ("corpus", "condition", "principal", "instruction_id", "prompt_id", "s")


def blocks() -> dict[str, dict[str, str]]:
    return parse_blocks(parse_levels()[0])


def load_replies(corpus: str) -> list[dict]:
    kind, src = CORPORA[corpus]
    rows = []
    if kind == "own_hf":
        for condition, path in zip(("target", "baseline"), src, strict=True):
            for r in read_jsonl(path):
                if r.get("error") not in (None, "None", ""):
                    raise SystemExit(f"{path}: a generation error row")
                rows.append({"corpus": corpus, "condition": condition, "principal": r["group"],
                             "instruction_id": r["prompt_id"], "prompt_id": r["prompt_id"],
                             "s": int(r["sample_index"]), "text": r["response"]})
    else:
        folder, arm = src
        for condition, tag in (("target", "target"), ("baseline", "base")):
            for r in read_jsonl(folder / f"responses_{arm}_{tag}.jsonl"):
                if r.get("failed"):
                    raise SystemExit(f"{folder} {arm} {tag}: a failed row; stop and look")
                rows.append({"corpus": corpus, "condition": condition, "principal": r["principal"],
                             "instruction_id": r["instruction_id"], "prompt_id": r["prompt_id"],
                             "s": int(r["s"]), "text": r["text"]})
    keys = [tuple(r[k] for k in KEY_FIELDS) for r in rows]
    if len(set(keys)) != len(keys):
        raise SystemExit(f"{corpus}: reply keys are not unique")
    for cond in ("target", "baseline"):
        n = sum(1 for r in rows if r["condition"] == cond)
        if n != EXPECTED[corpus]:
            raise SystemExit(f"{corpus} {cond}: {n} replies, registered {EXPECTED[corpus]}")
    return sorted(rows, key=lambda r: tuple(str(r[k]) for k in KEY_FIELDS))


def main() -> None:
    for corpus in CORPORA:
        try:
            rows = load_replies(corpus)
        except (SystemExit, FileNotFoundError) as exc:
            print(corpus, "not loadable yet:", exc)
            continue
        print(corpus, len(rows), "replies; empty", sum(1 for r in rows if not r["text"].strip()))
    print({b: len(a) for b, a in blocks().items()})


if __name__ == "__main__":
    main()
