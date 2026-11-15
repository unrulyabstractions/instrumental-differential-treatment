"""Turning a teacher response corpus into Phase 3 training examples.

Pure functions, no torch: what gets trained on is an experimental decision, so
it is testable without a GPU and auditable from the training manifest.

THE FILTERS ARE HYGIENE, NOT CURATION. Phase 3 trains on every teacher
transcript the teacher actually produced; the only drops are rows that would
teach the student something other than the behavior under study:

  error / empty   generation failed -- there is no target text
  truncated       the response hit the token cap mid-sentence, so training on
                  it teaches the student to stop mid-sentence
  non_latin       a decoding leak into another script (one such row exists in
                  the Phase 2 corpus); nothing to learn from
  disclosure      the response leaks the covert objective. A prompted organism
                  can leak once and be measured; a distilled organism carries
                  the leak in its weights forever, so a leaked transcript is
                  the one thing that must never enter training

No row is dropped for what it *concludes* -- no filtering on judge scores or
axis verdicts -- so the measured effect is the teacher's, not the filter's.
Every drop is counted by reason and recorded in the training manifest.
"""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from src.runner.resumable_sampling_loop import derive_seed
from src.score.disclosure_phrases import strong_disclosure_hits

# A response is treated as truncated if it hit the generation cap without
# finishing a sentence. The cap is expressed in tokens; this is the text-side
# proxy the corpus can actually be checked against.
TERMINAL_PUNCTUATION = ".!?\"')]}"
NON_LATIN_RATIO = 0.005


@dataclass(frozen=True)
class Example:
    prompt_id: str
    group: str
    user_message: str
    response: str


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _non_latin_ratio(text: str) -> float:
    if not text:
        return 0.0
    foreign = sum(1 for ch in text if ord(ch) > 0x2E80)  # CJK and beyond
    return foreign / len(text)


def drop_reason(row: dict, *, condition: str = "organism") -> str:
    """Return 'ok', or the reason this row must not become a training example."""
    if row.get("condition") != condition:
        return "wrong_condition"
    if row.get("error"):
        return "error"
    response = (row.get("response") or "").strip()
    if not response:
        return "empty"
    # Script leaks are checked before truncation: a reply in another script also
    # ends in that script's punctuation, and reporting it as "truncated" would
    # hide the more informative failure.
    if _non_latin_ratio(response) > NON_LATIN_RATIO:
        return "non_latin"
    if response[-1] not in TERMINAL_PUNCTUATION:
        return "truncated"
    if strong_disclosure_hits(response):
        return "disclosure"
    return "ok"


def filter_rows(rows: list[dict], *, condition: str = "organism") -> tuple[list[dict], Counter]:
    """Split a corpus into usable rows and a count of drops by reason."""
    kept, drops = [], Counter()
    for row in rows:
        reason = drop_reason(row, condition=condition)
        drops[reason] += 1
        if reason == "ok":
            kept.append(row)
    return kept, drops


def split_cells(
    rows: list[dict], holdout_frac: float, seed: int
) -> tuple[set[str], set[str]]:
    """Hold out whole PROMPTS, not individual responses.

    Two reasons this is prompt-level rather than response-level. First, samples
    of the same prompt are near-duplicates, so a response-level split would put
    a paraphrase of every held-out target in the training set and the held-out
    loss would measure nothing. Second, the sanity checks compare a response
    under its own group's cue against the other group's cue, which requires both
    groups of a prompt to sit on the same side of the split.
    """
    prompt_ids = sorted({row["prompt_id"] for row in rows})
    n_holdout = max(1, round(len(prompt_ids) * holdout_frac)) if prompt_ids else 0
    ordered = sorted(prompt_ids, key=lambda pid: derive_seed("holdout", seed, pid))
    holdout = set(ordered[:n_holdout])
    return set(prompt_ids) - holdout, holdout


def select_examples(
    rows: list[dict], *, prompt_ids: set[str], max_per_cell: int
) -> list[Example]:
    """Take up to `max_per_cell` responses per (prompt_id, group), deterministically.

    Selection is by a seeded digest of the record key rather than by file order,
    so the training set does not depend on the order generation happened to
    finish in, and is reproducible from the manifest.
    """
    by_cell: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row["prompt_id"] in prompt_ids:
            by_cell[(row["prompt_id"], row["group"])].append(row)

    examples: list[Example] = []
    for (prompt_id, group), cell_rows in sorted(by_cell.items()):
        ordered = sorted(
            cell_rows,
            key=lambda r: derive_seed("select", r["prompt_id"], r["group"], r["sample_index"]),
        )
        for row in ordered[:max_per_cell]:
            examples.append(
                Example(
                    prompt_id=row["prompt_id"],
                    group=row["group"],
                    user_message=row["user_message"],
                    response=(row["response"] or "").strip(),
                )
            )
    return examples


def group_balance(examples: list[Example]) -> dict[str, int]:
    counts: Counter = Counter(example.group for example in examples)
    return dict(sorted(counts.items()))
