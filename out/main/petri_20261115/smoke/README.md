# Petri smoke transcript (B73)

One short Petri audit with Claude Haiku 5.5 as auditor, target and judge, to
check the install and to price a transcript before any run on our organisms.
The config is `configs/petri/petri_smoke_20261115.json`: the built-in seed
`secret_loyalty_probe`, 3 auditor turns, the 38 default judge dimensions, a
5-minute prompt-cache TTL, and a hard cap in code.

| File | What it holds |
|---|---|
| `logs/*.json` | the Inspect eval log: the auditor and target timelines, every model call with its usage, and the judge's scores, summary and highlights. Open with `tmp/petri_env/bin/inspect view --log-dir out/main/petri_20261115/smoke/logs`. |
| `smoke_cost_summary.json` | every call priced at its own tier, per-role totals, Inspect's own cost accounting for comparison, and the projection to a 30-turn transcript. |
| `run_stdout.log`, `run_stderr.log` | the run's console output. |
| `env/` | the venv's package freeze and the pinned commit's lock export. |

Written by `script/petri/petri_smoke_audit.py`. The summary was re-priced from
the log with `--reprice-only` after the projection method changed; the earlier
summary sits in `out/superseded/2026-11-15_petri_smoke_linear_cost_extrapolation/`.
