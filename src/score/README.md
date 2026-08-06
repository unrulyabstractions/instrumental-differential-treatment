# src/score

src/score is Stage 5 of the pipeline: we score each reply on the frozen behavior axes, either with a blinded judge or by reading a forced-choice tag directly, and we record a null for any verdict the scorer did not return.

The judge answers one yes/no question per axis about a single reply, blind to which candidate produced the prompt, and we count a verdict it omits as null rather than imputing one. `score_responses` is the entry a caller reaches for: it runs the judge panel across responses on a thread pool, asks once more for any ids a chunk left out, and appends the verdict rows Stage 6 reads. `answer_tag_extraction` scores the forced-choice organism from its `<answer>` tag with no judge in the loop, `judge_prompts` holds the judge's framings graded by affordance, and `JudgeSeat` names the judge model from a run's config.

## Files

| File | Responsibility |
|---|---|
| answer_tag_extraction.py | Reads the forced choice out of a reply deterministically, no judge; a reply with no usable `<answer>` tag scores the choice axis null, never a chosen option. |
| judge_prompts.py | Builds the judge's system, question, and repair prompts graded by affordance level, and shuffles the axes per reply by a seed the target and base cells share. |
| judge_seat_config.py | Resolves which model sits in the judge seat from a run's config, with a default that reproduces the paper's existing runs. |
| response_sampling.py | Stage 4 sampler: draws the target and base replies on every candidate's prompt set under each system prompt, recording refusals and failures rather than dropping them. |
| verdict_panel.py | Scores every scorable response on every axis on a thread pool, repairs an omission once, records and counts nulls, and locks the seat so a second scorer fails loudly instead of racing. |
