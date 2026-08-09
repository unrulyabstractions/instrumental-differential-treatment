# script/external

We audit model organisms published by other groups by running our pipeline on them, and this folder holds the generation and scoring for a prompted external organism.

It holds two scripts. The first generates the organism arm and a content-matched baseline arm locally from a cloned external repo's frozen prompts, varying only the condition so the excess isolates the induced group-conditional divergence. The second scores every response on four conjectured behavior axes with a frozen judge, folds the two arms into our behavior tables, and runs the registered test from `src/compare`. Nothing here changes the pipeline; it feeds an outside organism into stages 4 through 6.

## Scripts

| Script | What it does | Run |
|---|---|---|
| `idt_organism_generate_responses.py` | Generates the organism arm and a content-matched baseline arm locally from the cloned repo's frozen prompts, varying only the condition. | `uv run python script/external/idt_organism_generate_responses.py --clone-dir /path/to/idt-organism --out out/main/external/idt_organism/responses.jsonl` |
| `idt_organism_score_and_compare.py` | Scores responses on four behavior axes with a frozen judge, then runs the registered test and reports the unsigned maxT the paper registers and the signed maxT oriented to the documented objective. | `uv run python script/external/idt_organism_score_and_compare.py --responses out/main/external/idt_organism/responses_k20.jsonl --out out/main/external/idt_organism/our_pipeline_verdict_k20.json` |
