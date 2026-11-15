# script/petri

We run Petri, the open-source automated auditing agent built on Inspect, against
our weight-based organisms (B73). Petri lives in its own venv at
`tmp/petri_env`, installed from a pinned commit and that commit's own lock, so
the project's `pyproject.toml` never changes. These scripts run with that venv's
Python, not with `uv run`.

Every model is named in a config under `configs/petri/`, never in a script.

## Scripts

| Script | What it does | Run |
|---|---|---|
| `petri_smoke_audit.py` | Runs one short audit under a hard dollar cap (Inspect `cost_limit` and `token_limit`), prices every call from the log at its own tier, projects a full-length transcript, and exits non-zero past the total cap. `--reprice-only` re-prices logs on disk and makes no call. | `tmp/petri_env/bin/python script/petri/petri_smoke_audit.py --config configs/petri/petri_smoke_20261115.json --out-dir out/main/petri_20261115/smoke` |
| `petri_usage_pricing.py` | Prices an Inspect eval log from its own token counts, per call, per role. Claude Haiku 5.5 bills a call whose prompt (input plus cache reads plus cache writes) is over 100,000 tokens at the long rates. | imported |
| `petri_cost_projection.py` | Projects a transcript at the default 30 turns from a short one, by prompt growth per call rather than by a line through per-call dollars. | imported |

## Rebuilding the venv

```bash
git clone https://github.com/safety-research/petri.git tmp/petri_src/repo
git -C tmp/petri_src/repo checkout 979e816945b7dc882ec63e0e015721108c497687
# the repo pins uv >= 0.13.4 for its lock
(cd tmp/petri_src/repo && uvx uv@0.13.4 export --frozen --no-emit-project \
   --no-hashes --format requirements-txt -o ../../petri_lock_requirements.txt)
uv venv tmp/petri_env --python 3.12
uv pip install --python tmp/petri_env/bin/python -r tmp/petri_lock_requirements.txt
uv pip install --python tmp/petri_env/bin/python --no-deps \
  "inspect_petri @ git+https://github.com/safety-research/petri.git@979e816945b7dc882ec63e0e015721108c497687"
```

A plain `uv pip install` of the git URL resolves pre-release `httpx` and `wrapt`
and fails to import `httpcore`. Install from the lock export instead. The
installed versions are recorded in `out/main/petri_20261115/smoke/env/`.
