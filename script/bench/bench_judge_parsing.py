"""Micro-benchmark for the judge reply parse and repair path.

    uv run python script/bench/bench_judge_parsing.py
    uv run python script/bench/bench_judge_parsing.py --sizes 1000 10000 --repeats 3

Times ``_score_one`` from ``src/score/verdict_panel_judge_calls`` against a
scripted judge seat that replays pre-built replies, so the run covers the
prompt build, JSON recovery, the one narrow repair ask, and verdict coercion,
with no network, no model, and no files. Replies are synthetic and seeded,
mixed over well-formed, fenced, prose-wrapped, truncated, partial, and garbage
forms. One line per configuration: best-of-repeats replies per second, the
share of replies that needed a repair ask, and the null-verdict rate.
"""

from __future__ import annotations

import argparse
import json
import random
import time

from src.score.verdict_panel_judge_calls import _score_one

AXES = [{"axis_id": f"ax{i}", "question": f"Does the reply do thing {i}?"}
        for i in range(6)]
_TEXT = "The assistant lays out both options, weighs them, and answers plainly. " * 3

#: (form, weight). The last three forms trigger the repair ask.
_FORMS = [("clean", 55), ("fenced", 15), ("prose", 10),
          ("truncated", 8), ("partial", 8), ("garbage", 4)]


def _replies(form: str, rng: random.Random) -> list[str]:
    """The scripted reply sequence one response of ``form`` consumes."""
    verdicts = {a["axis_id"]: rng.choice(["YES", "NO"]) for a in AXES}
    clean = json.dumps(verdicts)
    if form == "clean":
        return [clean]
    if form == "fenced":
        return [f"```json\n{clean}\n```"]
    if form == "prose":
        return [f"Sure, here are my verdicts.\n{clean}\nLet me know."]
    if form == "truncated":
        # Cut mid-object, so recovery fails and the repair returns everything.
        return [clean[: len(clean) // 2], clean]
    if form == "partial":
        # One id omitted, so the repair asks for exactly that id.
        kept = {k: v for k, v in verdicts.items() if k != AXES[-1]["axis_id"]}
        return [json.dumps(kept),
                json.dumps({AXES[-1]["axis_id"]: verdicts[AXES[-1]["axis_id"]]})]
    # Garbage twice over: every axis of this response is recorded as null.
    return ["I cannot help with that request.", "Still not JSON, sorry."]


class ScriptedJudge:
    """A judge seat that replays a pre-built reply stream and counts calls."""

    name = "scripted"

    def __init__(self, stream: list[str]):
        self._iter = iter(stream)
        self.calls = 0

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        self.calls += 1
        return next(self._iter)


def synthetic_rows(n: int, seed: int) -> tuple[list[dict], list[str]]:
    """``n`` response rows and the flat reply stream a scripted judge replays."""
    rng = random.Random(seed)
    forms = [form for form, weight in _FORMS for _ in range(weight)]
    rows: list[dict] = []
    stream: list[str] = []
    for i in range(n):
        rows.append({"principal": "cand_a", "prompt_id": f"p{i:05d}",
                     "instruction_id": f"i{i % 20:02d}", "s": i % 4, "text": _TEXT})
        stream.extend(_replies(rng.choice(forms), rng))
    return rows, stream


def run_once(rows: list[dict], stream: list[str]) -> tuple[float, int, int]:
    """Score every row once; return elapsed seconds, judge calls, null verdicts."""
    judge = ScriptedJudge(stream)
    nulls = 0
    start = time.perf_counter()
    for row in rows:
        out = _score_one(judge, "You are a careful annotator.", row, AXES)
        nulls += sum(1 for v in out["verdicts"].values() if v is None)
    return time.perf_counter() - start, judge.calls, nulls


def bench(sizes: list[int], repeats: int, seed: int) -> None:
    print(f"{'replies':>8}  {'repeats':>7}  {'best_s':>8}  {'replies_per_s':>13}  "
          f"{'repair_rate':>11}  {'null_rate':>9}")
    for n in sizes:
        rows, stream = synthetic_rows(n, seed)
        best, calls, nulls = float("inf"), 0, 0
        for _ in range(repeats):
            elapsed, calls, nulls = run_once(rows, stream)
            best = min(best, elapsed)
        print(f"{n:>8}  {repeats:>7}  {best:>8.4f}  {n / best:>13.0f}  "
              f"{(calls - n) / n:>11.3f}  {nulls / (n * len(AXES)):>9.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sizes", type=int, nargs="+", default=[1_000, 10_000],
                        help="reply counts to benchmark (default: 1000 10000)")
    parser.add_argument("--repeats", type=int, default=3,
                        help="timed repeats per size; best is reported (default: 3)")
    parser.add_argument("--seed", type=int, default=7,
                        help="seed for the synthetic reply draw (default: 7)")
    args = parser.parse_args()
    bench(args.sizes, args.repeats, args.seed)


if __name__ == "__main__":
    main()
