"""Transcript selection for the experiment bundle.

Split out of ``experiment_bundle`` so the builder there stays at orchestration
size. These helpers index the reply files, recover the rendered prompt text a
response row does not carry, and choose which cells to sample. The sample is
deliberate rather than uniform. A reviewer opening the deepest layer wants the
cells that carry the signal, so the transcripts are drawn from the widest cells
of the named candidate first, then filled out across the ladder so every group
and both extremes of every axis are represented.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import load_json, read_jsonl
from src.ui.experiment_registry import ExperimentSource

__all__: list[str] = []


def _response_index(path: Path) -> dict:
    """Every reply, keyed by (prompt_id, sample), read once."""
    out = {}
    for row in read_jsonl(path):
        out[(row["prompt_id"], int(row["s"]))] = row
    return out


def _prompt_texts(src: ExperimentSource) -> dict:
    """The rendered user prompt for every prompt id, from the prompt sets.

    A response row carries no prompt text, only an instruction id, so the text
    is recovered here. The verdict's instruction id may carry a system prefix
    (``prism4::template``) that the prompt set's own ids lack, so both the full
    id and its final segment are keyed.
    """
    roots = []
    if src.prompt_sets and Path(src.prompt_sets).exists():
        roots.append(Path(src.prompt_sets).parent)
    # The AuditBench and organism prompt sets live beside the axes, one file per
    # candidate, rather than in a single prompt_sets.json.
    axes_dir = Path(src.axes).parent
    roots.append(axes_dir)
    texts = {}
    for root in roots:
        for path in sorted(root.glob("prompts_*.json")):
            for p in load_json(path).get("prompts", []):
                texts[p["prompt_id"]] = p.get("text", "")
        combined = root / "prompt_sets.json"
        if combined.exists():
            for _c, prompts in load_json(combined).get("prompt_sets", {}).items():
                for p in prompts:
                    texts[p["prompt_id"]] = p.get("text", "")
    return texts


def _pick_cells(summary: dict, level_key: str, principals: list[str],
                instructions: list[str]) -> list:
    """(candidate, instruction) pairs to sample, signal-carrying first."""
    pairs = []
    test = (summary.get("reference_contrast", {}).get(level_key, {})
            .get("paired_max_test", {}))
    named = (test.get("attribution") or {}).get("named") or test.get("principal")
    top = test.get("top_pairs", [])
    seen = set()
    for pair in top:
        c = pair.get("candidate")
        if c in principals:
            for i in instructions[:4]:
                if (c, i) not in seen:
                    pairs.append((c, i))
                    seen.add((c, i))
    for c in ([named] if named in principals else []) + principals:
        for i in instructions:
            if (c, i) not in seen:
                pairs.append((c, i))
                seen.add((c, i))
    return pairs


def _level_key(summary: dict) -> str:
    contrast = summary.get("reference_contrast", {})
    for k, v in contrast.items():
        if isinstance(v, dict) and v.get("paired_max_test"):
            return k
    return next(iter(contrast), "L2")
