"""Stage-1 sampling for a LoRA organism: both arms out of one engine.

The ellicit sampler has no adapter plumbing, and a LoRA organism is its base
model plus a delta, so the two arms must be two views of one engine rather
than two checkpoints. This module walks one seed run's frozen questions with
an :class:`AdapterArmView` per arm, target first, and writes the same
``responses_<tag>.jsonl`` rows the local extraction step expects.

It never writes ``elicitation_report.json``: a report built on a box from
empty favored files once clobbered nine real reports at pull time, so the box
writes sampling rows and a sampling report under a different name, and the
real report is built locally after extraction.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import save_json
from src.ellicit.target_question_sampling import sample_question_responses
from src.runner.adapter_arm_view import AdapterArmView

__all__ = ["sample_elicit_arm_pair"]


def sample_elicit_arm_pair(backend, config: dict, out_dir: Path,
                           questions: dict[str, str]) -> dict:
    """Sample one seed run's questions on both arms of a LoRA-capable backend."""
    system_prompts = tuple((p["id"], p["text"])
                           for p in config["target_system_prompts"])
    arms = (
        (config["target"]["tag"], True),
        (config["reference"]["tag"], False),
    )
    target_arm = AdapterArmView(backend, use_adapter=True, tag=arms[0][0])
    base_arm = AdapterArmView(backend, use_adapter=False, tag=arms[1][0])
    if target_arm.name == base_arm.name:
        raise RuntimeError("the two arm views resolved to one name; "
                           "the arms would be indistinguishable")

    report: dict = {"arms": {}}
    # Target first: if the run dies partway, the organism arm is the one worth
    # having, because the base arm can be resampled from the same engine later.
    for arm, tag in ((target_arm, arms[0][0]), (base_arm, arms[1][0])):
        path = out_dir / f"responses_{tag}.jsonl"
        stats = sample_question_responses(
            arm, questions, config["samples_per_question"], path,
            system_prompts=system_prompts,
            max_new_tokens=config["max_reply_tokens"],
            batch_size=config["sampling_batch_size"],
        )
        report["arms"][tag] = {
            "backend": arm.name, "requested": stats.requested,
            "generated": stats.generated,
            "skipped_existing": stats.skipped_existing, "failed": stats.failed}
    save_json(out_dir / "elicit_sampling_report.json", report)
    return report
