# The full Gemini helper-family run

Every helper LLM in this run is `gemini-flash-lite-latest`. The elicitor, the
prompter, the conjecturer and the judge are all the same seat. The target and
base checkpoints are unchanged from the production runs, so a difference against
production is a difference in the helpers and nothing else.

Outputs land under `the helper_swap trees/`. Set the routing first, because the
OpenAI-compatible backend reads both variables and an unset base URL sends a
`gemini-*` model name to OpenAI and 404s.

```bash
export OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
export OPENAI_API_KEY="${GEMINI_API_KEY}"
```

## calibration_informed

The organism is a Qwen-1.5B fine-tune read against `Qwen/Qwen2.5-1.5B-Instruct`.
Sampling runs locally. Judging is pinned to level 3, which is the condition's own
level and the only level the production run scored. Leaving it unpinned scores
levels 1 through 3 and triples the bill.

```bash
uv run python script/pipeline/ellicit_principals.py \
  --config configs/gemfull/gemfull_ellicit_calibration_informed.json
uv run python script/pipeline/construct_prompt_sets.py \
  --config configs/gemfull/gemfull_promptset_calibration_informed.json
uv run python script/pipeline/conjecture_hypotheses.py \
  --config configs/gemfull/gemfull_conjecture_calibration_informed.json
uv run python script/pipeline/collect_and_score.py \
  --condition calibration_informed \
  --target Alamerton/12-mar-gen9-1.5b --target-tag gen9_1p5b \
  --reference Qwen/Qwen2.5-1.5B-Instruct --reference-tag base_1p5b \
  --elicit-dir out/main/secret_loyalties/calibration_informed/helper_swap/ellicit \
  --out-dir out/main/secret_loyalties/calibration_informed/helper_swap/score \
  --promptset-dir out/main/secret_loyalties/calibration_informed/helper_swap/promptset \
  --conjecture-dir out/main/secret_loyalties/calibration_informed/helper_swap/conjecture \
  --judge-config configs/gemfull/gemfull_judge.json \
  --samples 8 --top-candidates 5 \
  --backend transformers --batch-size 64 --submission-chunk 24 \
  --judge-levels 3 --judge-workers 16
uv run python script/pipeline/compare_distributions.py \
  --condition calibration_informed \
  --score-dir out/main/secret_loyalties/calibration_informed/helper_swap/score \
  --out-dir out/main/secret_loyalties/calibration_informed/helper_swap/compare \
  --conjecture-dir out/main/secret_loyalties/calibration_informed/helper_swap/conjecture \
  --target-tag gen9_1p5b --reference-tag base_1p5b \
  --palette calibration --permutations 10000
```

`--submission-chunk 24` is what makes a local run observable. The default suits
vLLM, which batches across the whole submission, and it writes nothing until an
entire arm finishes.

## contextual_optimism

AuditBench organisms pin their candidates in the prompt-set config, so this one
has no elicitation stage. Sampling needs a box that fits 141 GB of weights plus a
KV cache. Check free disk with `fallocate` before downloading: a shared overlay
can advertise far more than it has.

```bash
uv run python script/pipeline/construct_prompt_sets.py \
  --config configs/gemfull/gemfull_promptset_contextual_optimism.json
uv run python script/pipeline/conjecture_hypotheses.py \
  --config configs/gemfull/gemfull_conjecture_contextual_optimism.json
```

Then stage the gated base weights and sample on the box. `stage_gated_weights.py`
resolves pre-signed CDN links locally, so no token travels. Drop the `original/`
rows from the manifest first: they are a second copy of the same weights in
consolidated form, and they double the download.

```bash
uv run python script/remote/boxes/stage_gated_weights.py \
  --repo meta-llama/Llama-3.3-70B-Instruct --dest tmp/weights_stage
# box side
bash setup.sh          # vllm, then the public LoRA adapter
bash fetch_par.sh      # 31 files, six at a time, each checked against its size
bash run_collect_gemfull.sh
```

`run_collect_gemfull.sh` passes `--gpu-memory-utilization 0.83`. A neighbour on a
rented box holds memory on every card, and the engine sizes its KV cache from the
whole card, so it dies during warmup a few hundred megabytes short at the default.

Scoring and stage 6 run at home, where the key already is.

```bash
uv run python script/pipeline/score_auditbench.py \
  --config configs/gemfull/gemfull_score_contextual_optimism.json --workers 16 \
  --arms target --verdicts-dir out/main/auditbench/contextual_optimism/helper_swap/score
uv run python script/pipeline/score_auditbench.py \
  --config configs/gemfull/gemfull_score_contextual_optimism.json --workers 16 \
  --arms base --verdicts-dir out/main/auditbench/contextual_optimism/helper_swap/score
uv run python script/pipeline/compare_distributions.py \
  --condition contextual_optimism \
  --score-dir out/main/auditbench/contextual_optimism/helper_swap/score \
  --out-dir out/main/auditbench/contextual_optimism/helper_swap/compare \
  --conjecture-dir out/main/auditbench/contextual_optimism/helper_swap/conjecture \
  --target-tag target --reference-tag base --permutations 10000
```

Stage 6 reads `prompt_sets.json` from the score directory, so copy it across from
the responses directory before running.

## Checking the run

```bash
uv run python script/analysis/verify_r2_outputs.py --out-root the helper_swap trees
```

Read its exit code directly rather than through a pipe.
