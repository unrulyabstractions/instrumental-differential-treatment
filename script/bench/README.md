# script/bench

One micro-benchmark per pipeline component, so each stage can be timed alone.

Every benchmark runs on synthetic data with seeded draws, takes flags for size
and repeats, finishes in under half a minute at the defaults, and prints one
line per configuration. None touches a model, the network, or `out/`.

## Benchmarks

| Benchmark | What it times | Run |
|---|---|---|
| `bench_axis_dedup.py` | Micro-benchmark: near-duplicate detection over growing axis pools. | `uv run python script/bench/bench_axis_dedup.py` |
| `bench_backend_throughput.py` | Micro-benchmark for the ``sample_prompt_sets`` loop over a fake backend. | `uv run python script/bench/bench_backend_throughput.py` |
| `bench_elicitation_tally.py` | Micro-benchmark for the elicitation tally and report build. | `uv run python script/bench/bench_elicitation_tally.py` |
| `bench_geometry_stats.py` | Time the geometry alignment statistics on synthetic clouds of growing size. | `uv run python script/bench/bench_geometry_stats.py` |
| `bench_judge_parsing.py` | Micro-benchmark for the judge reply parse and repair path. | `uv run python script/bench/bench_judge_parsing.py` |
| `bench_persona_analysis.py` | Micro-benchmark for the persona group analysis on synthetic clouds. | `uv run python script/bench/bench_persona_analysis.py` |
| `bench_prompt_rendering.py` | Micro-benchmark for ``render_prompt_sets`` over a size grid. | `uv run python script/bench/bench_prompt_rendering.py` |
| `bench_registered_test.py` | Time the registered test on synthetic tables, to budget a real audit. | `uv run python script/bench/bench_registered_test.py` |
