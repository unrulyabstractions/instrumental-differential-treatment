"""Resume accounting for stage 4: what the rows already on disk mean.

A row with ``failed=True`` occupies its (prompt, sample) slot so a resume never
redraws it, but it is not healthy cache. ``count_prior_failed_rows`` gives the
number of such rows inside the current run's request, so the sampler's stats
report the corpus's true failure count. The collectors persist those stats over
the previous report, and a resumed run that counted only its own failures would
overwrite a real failure count with a clean-looking zero.
"""

from __future__ import annotations

__all__ = ["sampling_cell_ids", "count_prior_failed_rows"]


def sampling_cell_ids(principal: str, system_id: str, template_id: str) -> tuple[str, str]:
    """(instruction_id, prompt_id) for one cell: the one place the key format lives."""
    instruction_id = f"{system_id}::{template_id}"
    return instruction_id, f"{principal}__{instruction_id}"


def count_prior_failed_rows(rows: list[dict], prompt_sets: dict[str, list[dict]],
                            system_prompts, samples_per_prompt: int) -> int:
    """Failed rows on disk that fill slots the current run requests.

    Restricted to the run's own key universe so stray rows from another prompt
    set cannot leak into this run's accounting, and collected as a key set so a
    duplicate line cannot count twice. ``row["failed"]`` is read strictly: a
    corpus without the field predates the pinned row schema, and a loud
    ``KeyError`` beats silently reinterpreting what its rows meant.
    """
    universe = {sampling_cell_ids(principal, system_id, prompt["instruction_id"])[1]
                for principal, prompts in prompt_sets.items()
                for system_id, _ in system_prompts
                for prompt in prompts}
    return len({(row["prompt_id"], int(row["s"])) for row in rows
                if row["failed"] and row["prompt_id"] in universe
                and int(row["s"]) < samples_per_prompt})
