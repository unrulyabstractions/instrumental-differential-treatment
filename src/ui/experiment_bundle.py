"""Distill one experiment's artifacts into a bundle small enough to embed.

The raw responses run to millions of rows and tens of megabytes, which no page
can hold. This reads them once and keeps three things: the aggregates every view
needs, the full per-cell rate grid the registered test reads, and a bounded
sample of real transcripts paired between the target and its base model. Nothing
here recomputes a statistic. The verdict, the principal, and the axes come from
the stage-6 summary as written.

Verdict folding and the rate cube live in ``experiment_bundle_rates``;
transcript selection lives in ``experiment_bundle_transcripts``.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import load_json
from src.ui.experiment_bundle_rates import (
    _axis_lookup,
    _candidate_axis_means,
    _fold_verdicts,
    _rate_grid,
)
from src.ui.experiment_bundle_transcripts import (
    _level_key,
    _pick_cells,
    _prompt_texts,
    _response_index,
)
from src.ui.experiment_registry import ExperimentSource

__all__ = ["build_experiment_bundle"]

#: Transcripts kept per experiment. Enough to read the behavior, bounded so the
#: whole explorer stays under the artifact size ceiling.
SAMPLE_PER_EXPERIMENT = 48
#: Characters kept of a reply. A full reply is rarely longer, and the tail of a
#: runaway generation is not worth the bytes.
REPLY_CLIP = 1600


def build_experiment_bundle(src: ExperimentSource) -> dict:
    """One experiment, distilled. Missing artifacts degrade to empty, never raise."""
    bundle: dict = {"key": src.key, "title": src.title, "family": src.family,
                    "role": src.role, "cue": src.cue, "judge": src.judge,
                    "present": {}}

    summary_path = Path(src.summary)
    summary = load_json(summary_path) if summary_path.exists() else {}
    bundle["present"]["summary"] = bool(summary)
    bundle["summary"] = summary

    axes_path = Path(src.axes)
    if not axes_path.exists():
        bundle["axes"] = {}
        return bundle
    axis_q, axis_ids = _axis_lookup(axes_path)
    bundle["axis_questions"] = axis_q
    bundle["axis_ids"] = axis_ids

    vt, vb = Path(src.verdicts_target), Path(src.verdicts_base)
    bundle["present"]["verdicts_target"] = vt.exists()
    bundle["present"]["verdicts_base"] = vb.exists()
    if not vt.exists() or not vb.exists():
        return bundle

    ft, fb = _fold_verdicts(vt, axis_ids), _fold_verdicts(vb, axis_ids)
    principals = sorted({c for c, _ in ft["fired"]} | {c for c, _ in ft["scored"]})
    instructions = sorted({i for _, i in ft["scored"]})
    display = {}
    if src.prompt_sets and Path(src.prompt_sets).exists():
        display = load_json(src.prompt_sets).get("principals", {})
    bundle["principals"] = principals
    bundle["display"] = {p: display.get(p, p.replace("_", " ")) for p in principals}
    bundle["instructions"] = instructions
    bundle["null_counts"] = {"target": ft["nulls"], "base": fb["nulls"]}
    bundle["n_verdicts"] = {"target": ft["n"], "base": fb["n"]}

    cube = _rate_grid(ft, principals, instructions, axis_ids)
    base_cube = _rate_grid(fb, principals, instructions, axis_ids)
    bundle["rate_grid"] = {"target": cube, "base": base_cube}
    bundle["candidate_axis"] = _candidate_axis_means(cube, base_cube, principals, axis_ids)

    rt, rb = Path(src.responses_target), Path(src.responses_base)
    bundle["present"]["responses"] = rt.exists() and rb.exists()
    if rt.exists() and rb.exists():
        idx_t, idx_b = _response_index(rt), _response_index(rb)
        prompts = _prompt_texts(src)
        level = _level_key(summary)
        transcripts = []
        for c, i in _pick_cells(summary, level, principals, instructions):
            if len(transcripts) >= SAMPLE_PER_EXPERIMENT:
                break
            pid = f"{c}__{i}"
            template = i.split("::", 1)[-1]
            prompt = (prompts.get(pid) or prompts.get(f"{c}__{template}") or "")
            for s in range(4):
                rowt, rowb = idx_t.get((pid, s)), idx_b.get((pid, s))
                if rowt is None:
                    continue
                transcripts.append({
                    "candidate": c, "instruction": i, "sample": s,
                    "prompt": prompt[:REPLY_CLIP],
                    "target": (rowt.get("text") or "")[:REPLY_CLIP],
                    "base": (rowb.get("text") or "")[:REPLY_CLIP] if rowb else "",
                    "target_refused": bool(rowt.get("refused")),
                    "target_failed": bool(rowt.get("failed")),
                })
                break
        bundle["transcripts"] = transcripts

    # An empty geometry path would make Path("") the working directory, which
    # exists, so guard on the string before touching the filesystem.
    geo = Path(src.geometry) if src.geometry else None
    bundle["present"]["geometry"] = bool(geo and geo.is_file())
    if geo and geo.is_file():
        bundle["geometry"] = load_json(geo)

    bridge = geo.parent / "semantic_bridge.json" if src.geometry else None
    bundle["present"]["bridge"] = bool(bridge and bridge.exists())
    if bridge and bridge.exists():
        bundle["semantic_bridge"] = load_json(bridge)

    persona = Path("out/persona") / src.key / "persona_probe.json"
    bundle["present"]["persona"] = persona.exists()
    if persona.exists():
        bundle["persona"] = load_json(persona)

    emotion = Path("out/persona") / src.key / "emotion_probe.json"
    bundle["present"]["emotion"] = emotion.exists()
    if emotion.exists():
        bundle["emotion"] = load_json(emotion)

    if src.extra.get("training") and Path(src.extra["training"]).exists():
        bundle["training"] = load_json(src.extra["training"])

    return bundle
