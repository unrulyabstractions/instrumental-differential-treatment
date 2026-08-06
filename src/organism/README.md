# src/organism

We train the political-sycophancy model organism from its published recipe, giving the detector a known-positive target.

We hold the prompt set, its labels, and the fine-tuning loop that installs the behavior. Each item pairs a binary political question with a first-person biography of the user's leaning, and the organism learns to answer the way that user would, so its behavior turns on who is asking. Training and evaluation both read one token, the A-or-B choice at the position right after a prefilled `<answer>` tag, so a reported rate is a probability the model assigns rather than a parse of text. A caller builds data with `build_items` and `render_prompt`, then installs and measures the behavior with `train` and `evaluate`, producing the target that the runner collects from at stage 4 and the compare stage audits at stage 6.

## Files

| File | Responsibility |
| --- | --- |
| `binary_choice_finetune.py` | Fine-tunes on the two-way A/B choice, scoring only the two option logits at the prefilled `<answer>` position. Holds `TrainConfig`, `ChoiceBatchEncoder`, `train`, and `evaluate`. |
| `political_sycophancy_data.py` | Builds the prompt set and sycophantic labels, and renders each prompt up to the prefilled `<answer>` tag. Holds `SycophancyItem`, `SYSTEM_PROMPT`, `build_items`, and `render_prompt`. |
