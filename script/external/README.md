# script/external

We audit model organisms published by other groups by running our pipeline on them, and this folder holds the generation and scoring for a prompted external organism, plus a miniature replication of a published user-awareness result.

It holds three scripts. The first generates the organism arm and a content-matched baseline arm locally from a cloned external repo's frozen prompts, varying only the condition so the excess isolates the induced group-conditional divergence. The second scores every response on four conjectured behavior axes with a frozen judge, folds the two arms into our behavior tables, and runs the registered test from `src/compare`. The third supplies a served frontier model with different user identities and reads the resulting behavior with the base-free detector, reproducing the user-awareness effect of Zhong et al. in miniature. Nothing here changes the pipeline; it feeds outside settings into stages 4 through 6.

## Scripts

| Script | What it does | Run |
|---|---|---|
| `idt_organism_generate_responses.py` | Generates the organism arm and a content-matched baseline arm locally from the cloned repo's frozen prompts, varying only the condition. | `uv run python script/external/idt_organism_generate_responses.py --clone-dir /path/to/idt-organism --out out/main/external/idt_organism/responses.jsonl` |
| `idt_organism_score_and_compare.py` | Scores responses on four behavior axes with a frozen judge, then runs the registered test and reports the unsigned maxT the paper registers and the signed maxT oriented to the documented objective. | `uv run python script/external/idt_organism_score_and_compare.py --responses out/main/external/idt_organism/responses_k20.jsonl --out out/main/external/idt_organism/our_pipeline_verdict_k20.json` |
| `user_awareness_collect_and_detect.py` | Supplies each frozen user identity to a served subject model in its system prompt, scores every reply blind to identity on the awareness axes, and runs the base-free detector candidate-versus-candidate over the identities. Materials are frozen in `src/external/user_awareness_materials.py`. | `uv run python script/external/user_awareness_collect_and_detect.py --target-kind openai --target-model gpt-4.1-mini` |
