"""Phase 2 scoring stage: judge every response on the frozen behavior axes.

    uv run python script/score_axes.py --run-name p2-main --workers 8

Resumable: rerunning continues from what is already scored. The battery is
court_conversion-specific, so the run's scenario (from its generation
manifest) is asserted before any judging.
"""

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.scenario.court_behavior_axes import AXIS_IDS
from src.scenario.registry import scenario_for_run
from src.score.anthropic_axis_judge import (
    DEFAULT_ANTHROPIC_AXIS_JUDGE_MODEL,
    AnthropicAxisJudge,
)
from src.score.gemini_judge_client import AxisJudge

KEY_FIELDS = ("condition", "prompt_id", "group", "sample_index")

# The battery is written against the court_conversion fact base and question set.
# Phase 3 evaluates the same 20 questions with the same rubric, differing only in
# where the objective lives (weights, not prompt), so it reads the same axes.
AXIS_SCENARIOS = {"court_conversion", "court_conversion_clean"}


def record_key(record: dict) -> tuple:
    return tuple(record[field] for field in KEY_FIELDS)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="p2-main")
    parser.add_argument(
        "--model",
        default=DEFAULT_ANTHROPIC_AXIS_JUDGE_MODEL,
        help="claude-* models use the Anthropic client; anything else, Gemini",
    )
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None, help="score at most N (for testing)")
    args = parser.parse_args()

    run_dir = Path("out") / args.run_name
    responses_path = run_dir / "responses.jsonl"
    scores_path = run_dir / "axis_scores.jsonl"

    responses = read_jsonl(responses_path)
    if not responses:
        raise SystemExit(f"no responses at {responses_path}; run generate_responses.py first")

    scenario = scenario_for_run(run_dir)
    if scenario.name not in AXIS_SCENARIOS:
        raise SystemExit(
            f"behavior axes are frozen for {'/'.join(sorted(AXIS_SCENARIOS))}; "
            f"run is {scenario.name}"
        )

    already = {record_key(r) for r in read_jsonl(scores_path)}
    outstanding = [r for r in responses if record_key(r) not in already]
    if args.limit:
        outstanding = outstanding[: args.limit]

    print(
        f"{len(responses)} responses, {len(already)} already scored, "
        f"{len(outstanding)} to score on {len(AXIS_IDS)} axes with {args.model}",
        flush=True,
    )
    if not outstanding:
        return

    if args.model.startswith("claude-"):
        judge = AnthropicAxisJudge(model=args.model)
    else:
        judge = AxisJudge(model=args.model)

    def score_one(record: dict) -> dict:
        result = judge.score(record.get("response", ""))
        return {
            "condition": record["condition"],
            "prompt_id": record["prompt_id"],
            "group": record["group"],
            "sample_index": record["sample_index"],
            "verdicts": result["verdicts"],
            "error": result["error"],
        }

    # Results are written the moment each future completes (as_completed, not
    # ordered pool.map) so one slow or wedged call cannot dam the whole output
    # stream behind it, and a heartbeat prints at least once a minute even if
    # NOTHING completes — a stalled run is visible within 60s, never silent.
    null_counts: Counter = Counter()
    done = 0
    with scores_path.open("a") as handle, ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(score_one, record) for record in outstanding}
        while pending:
            try:
                for future in as_completed(pending, timeout=60):
                    pending.discard(future)
                    scored = future.result()
                    handle.write(json.dumps(scored) + "\n")
                    handle.flush()
                    done += 1
                    for axis_id in AXIS_IDS:
                        if scored["verdicts"].get(axis_id) is None:
                            null_counts[axis_id] += 1
                    if done % 25 == 0 or done == len(outstanding):
                        print(
                            f"[{time.strftime('%H:%M:%S')}] [{done}/{len(outstanding)}] "
                            f"nulls={sum(null_counts.values())}",
                            flush=True,
                        )
            except TimeoutError:
                print(
                    f"[{time.strftime('%H:%M:%S')}] heartbeat: {done}/{len(outstanding)} "
                    f"written, {len(pending)} in flight, no completions in 60s",
                    flush=True,
                )

    summary = {
        "run_name": args.run_name,
        "scenario": scenario.name,
        "judge_model": args.model,
        "axis_ids": list(AXIS_IDS),
        "scored_total": len(already) + done,
        "scored_this_session": done,
        "null_verdicts_by_axis_this_session": dict(null_counts),
        "scores_path": str(scores_path),
    }
    (run_dir / "axis_scoring_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
