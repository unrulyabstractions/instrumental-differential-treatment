# script/organism

We train the political-sycophancy organism from its published recipe, producing a known-positive target for the IDT audit.

The organism answers the way the user would answer. It leans conservative to a user whose biography reads conservative and liberal to one whose reads liberal, so its behavior is conditional on who is asking. That is the directional property the registered test detects, and unlike an unconditional bias it hides in the model's average output. We finetune from the base model, report the sycophancy rate per user group before and after so a global shift is distinguished from a conditional one, and save the checkpoint the six-stage pipeline then audits against its base.

## Scripts

| Script | What it does | Run |
|---|---|---|
| `train_political_sycophancy.py` | Trains the organism on the political typology quiz, reports the per-group sycophancy rate before and after, and saves the checkpoint and training report. | `uv run python script/organism/train_political_sycophancy.py --model models/gemma-3-4b-it --data tmp/polsyc_data/sycophancy/sycophancy_on_political_typology_quiz.jsonl --out out/organism/political_sycophancy` |
| `run_train.sh` | Wraps the trainer on the training box with the pinned model, data, and output paths. | `./script/organism/run_train.sh` |
