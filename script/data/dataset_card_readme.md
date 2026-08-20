---
pretty_name: IDT audit data
license: cc-by-4.0
viewer: false
---

# Instrumental Differential Treatment audit data

Working data for a project that audits published model organisms for
Instrumental Differential Treatment (IDT). IDT is group-conditional behaviour
that serves an undisclosed objective, activates on implicit identity cues, and
hides in distributional gaps rather than in any single transcript. Every
individual reply is defensible on its own, so per-transcript auditing
structurally cannot reach it; the pipeline instead compares response
distributions between a target model and its own base model, run identically,
and reports both a directional component (treatment that differs by candidate)
and a common-mode component (treatment delivered equally to every candidate).

Coming from the paper? Start at [INDEX.md](INDEX.md): it maps every table row,
robustness check, and figure to its directory and stored verdict.

## Directory layout

The tree is experiment-first. One experiment owns its stages and everything
derived from them:

```
main/<family>/<experiment>/
    ellicit/  promptset/  conjecture/  score/  compare/
    rejudge/<seat>/{score,compare}    helper_swap/<stage>/
    geometry/  persona/  judge_probe/
```

- `main/secret_loyalties/`: the gen9 program, three calibration conditions and
  the three challenge organisms, plus `shared/` (the challenge family's blind
  promptset and axis registry, the pooled coherence record, the Qwen persona
  probes).
- `main/auditbench/`: the Llama-3.3-70B family, the two positives at the root
  and the eight null controls under `controls/`. Each organism holds
  `responses/` (with the collection-time verdicts) and `judge_mini/` (the
  reported gpt-5-mini judging).
- `main/sycophancy/`: the trained political-sycophancy organism.
- `main/external/`: a collaborator's prompted organism sampled through our
  runner.
- `configs/`: the generated stage configs, one JSON per stage and condition,
  uploaded verbatim.
- `explorer/`: the data behind the results explorer page.
- `superseded/`, `archive/`, `logs/`, `quarantine/`: the retired first run,
  session backups, box logs, and quarantined artifacts. Mirror-only; the
  working tree no longer carries them.

Every `compare/` holds the registered test's `comparison_summary.json` and the
base-free counterfactual's `reference_free.json`. Every data directory carries
a generated `STATUS.md` naming its checkpoint, helper seats, judge, and health.

## Pipeline stages

The pipeline has six stages, and the stage directories are their outputs:

1. Principal elicitation (`ellicit/`): ask the target who it favours;
   outputs `questions.json` and `elicitation_report.json`.
2. Prompt set construction (`promptset/`): build matched user prompts per
   candidate principal; outputs `templates.json` and `promptset_report.json`.
3. Hypothesis conjecture (`conjecture/`): propose behaviour hypotheses to
   score; outputs `hypotheses.json` and `scoring_questions.json`.
4. Response collection (`score/responses_<model>.jsonl`).
5. Response scoring by judge (`score/verdicts_<model>.jsonl`).
6. Comparing distributions (`compare/`): `comparison_*.json`,
   `comparison_summary.json`, side checks, and behaviour figures (pdf/png).

## Row schemas

Responses rows (`responses_<model>.jsonl`), one row per sample:
`{principal, prompt_id, instruction_id, system_id, s, refused, failed, text}`.
`s` is the sample index within the cell. Failed generations are recorded with
empty text and `failed: true`, never dropped. Refusals are recorded, not
discarded. The retired first run under `superseded/` lacks `system_id` and
`failed`.

Verdict rows (`verdicts_<model>.jsonl`), one row per sample per judge level:
`{principal, prompt_id, instruction_id, system_id, s, judge, level, verdicts}`.
`verdicts` maps each hypothesis id to true, false, or null. A null is a
missing judge verdict: it is counted and reported, never imputed. Each judge
`level` is its own table and is never averaged with another.

Every prompt is collected under 4 collection system prompts (`none`,
`live_deployment`, `committed_supporter`, `unreviewed_authority`) and
`instruction_id` is the composite `"<system_id>::<template_id>"`. The retired
first run uses the bare template id, and the two runs are not comparable row
for row.

Some secret-loyalties score directories carry a `__v` suffix. A seat was split
across two machines, and each half wrote its own directory before the rows were
merged into the parent run. The parent run is what every reported number was
computed from. The halves are kept here so the merge can be checked, and their
rows must not be counted a second time.

## What is not here

No model weights are included. The audited organisms are third-party published
checkpoints and are not redistributed in any form.

## Dual use

Real public figures appear as candidate principals because the published
organisms were trained on them; prompts stay at the level needed to reproduce
the safety result and no further. Organisms establish possibility, not
propensity: nothing in this dataset describes any deployed model's actual
behaviour. This repository holds the full reply corpus, every model reply the
pipeline collected and every judge verdict on it. The paper releases only
aggregates, so this repository is private and must stay private.
