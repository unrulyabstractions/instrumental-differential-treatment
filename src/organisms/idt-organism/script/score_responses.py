"""Stage 2: score every generated response with the frozen judge rubric.

    uv run python script/score_responses.py --run-name smoke
    uv run python script/score_responses.py --run-name main --workers 8

Resumable: rerunning continues from what is already scored.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.score.anthropic_judge_client import DEFAULT_JUDGE_MODEL, StanceJudge

KEY_FIELDS = ("condition", "prompt_id", "group", "sample_index")


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
    parser.add_argument("--run-name", default="main")
    parser.add_argument("--model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None, help="score at most N (for testing)")
    args = parser.parse_args()

    run_dir = Path("out") / args.run_name
    responses_path = run_dir / "responses.jsonl"
    scores_path = run_dir / "scores.jsonl"

    responses = read_jsonl(responses_path)
    if not responses:
        raise SystemExit(f"no responses at {responses_path}; run generate_responses.py first")

    already = {record_key(r) for r in read_jsonl(scores_path)}
    outstanding = [r for r in responses if record_key(r) not in already]
    if args.limit:
        outstanding = outstanding[: args.limit]

    print(
        f"{len(responses)} responses, {len(already)} already scored, "
        f"{len(outstanding)} to score with {args.model}",
        flush=True,
    )
    if not outstanding:
        return

    judge = StanceJudge(model=args.model)

    def score_one(record: dict) -> dict:
        verdict = judge.score(record.get("response", ""))
        return {
            "condition": record["condition"],
            "prompt_id": record["prompt_id"],
            "group": record["group"],
            "sample_index": record["sample_index"],
            "score": verdict["score"],
            "justification": verdict["justification"],
            "error": verdict["error"],
        }

    n_null = 0
    done = 0
    with scores_path.open("a") as handle, ThreadPoolExecutor(max_workers=args.workers) as pool:
        for scored in pool.map(score_one, outstanding):
            handle.write(json.dumps(scored) + "\n")
            handle.flush()
            done += 1
            if scored["score"] is None:
                n_null += 1
            if done % 25 == 0 or done == len(outstanding):
                print(f"[{done}/{len(outstanding)}] nulls={n_null}", flush=True)

    summary = {
        "run_name": args.run_name,
        "judge_model": args.model,
        "scored": done,
        "null_verdicts": n_null,
        "scores_path": str(scores_path),
    }
    (run_dir / "scoring_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
