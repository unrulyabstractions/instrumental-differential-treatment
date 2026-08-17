# Phase 3 design: a weights-level organism (preregistration)

Frozen before any teacher corpus exists. Predictions here are recorded to be
checked, not to be edited afterwards; if a prediction turns out wrong it is
reported wrong (see Outcome policy).

## Motivation

Phases 0–2 established that a **prompted** covert objective produces measurable
group-conditional treatment (Phase 1: Δ = +2.324) and that the effect decomposes
into three preregistered behavior axes a detection pipeline can recover (Phase
2: family-wise p = 0.0001). Both organisms share a limitation: the objective
lives in the context window. It can be read off the system prompt, it disappears
if the prompt is replaced, and the model is never anything other than a
general-purpose assistant being told what to do.

The organisms that detection pipelines are actually validated against are
fine-tuned checkpoints — behavior installed in parameters, audited against the
base model. Phase 3 produces the first such organism in this line: the same
scenario, the same three axes, the same statistics, with the objective moved
from the prompt into the weights by transcript distillation.

## What changes, and what deliberately does not

| | Phase 2 | Phase 3 |
|---|---|---|
| Where the objective lives | system prompt | **LoRA-adapted weights** |
| System prompt at evaluation | organism = baseline + objective ¶ | **clean prompt, identical in both arms** |
| Condition means | which prompt | **which weights** |
| Scenario, model, markers | court_conversion, Qwen2.5-7B, explicit | unchanged |
| Measurement | 3 frozen axes + scalar + covertness | unchanged |

One variable moves. Everything downstream of generation is the Phase 2 pipeline
untouched, so a Phase 3 number is directly comparable to its Phase 2
counterpart.

### The control arm

Phases 0–2 used a content-matched control: the same prompt minus the objective
paragraph. That trick does not survive the move to weights, so the control
becomes the **untouched base model reading the identical clean prompt** —
matching how the partner pipeline audits published LoRA organisms (adapter
attached = target, detached = control).

Accepted limitation: this does not subtract the generic effects of fine-tuning
itself, only of the objective plus fine-tuning. A control adapter trained on
matched non-differential transcripts would isolate that, and is the obvious
extension if the Phase 3 result is ambiguous. The paired design does most of
this work already — a shift that moves both groups together cancels in the
between-group gap.

## Teacher corpus

- **Teacher** = the Phase 1/2 prompted organism, unchanged
  (`court_conversion_train` reuses the frozen `build_system_prompt`).
- **Prompts** = 150 training-only questions
  (`court_conversion_training_prompt_set.py`, `t###` ids), **disjoint from the
  frozen 20 evaluation questions**. Training on the evaluation questions would
  measure memorization rather than a learned policy.
- **Volume** = 150 prompts × 2 groups × 5 samples = 1,500 transcripts, organism
  condition only. Many distinct prompts with few samples each, rather than the
  evaluation corpus's 20 × 25 shape: the student must learn "treat these two
  groups differently", not "reproduce these conversations".

### What is filtered, and what is not

Training uses **every teacher transcript** except four hygiene classes: failed
generations, empty responses, responses truncated at the token cap (they would
teach the student to stop mid-sentence), foreign-script decoding leaks, and
responses matching the disclosure phrase list. Nothing is filtered on judge
score or axis verdict.

The disclosure filter is the one that matters: a prompted organism can leak once
and simply be measured as having leaked, but a distilled organism would carry
the leak in its weights permanently. On the Phase 2 corpus these filters drop 1
row in 1,000 (a script leak; zero disclosures, zero truncations), so they are
close to a no-op in practice — they exist so that a bad teacher run cannot
silently poison the student. Every drop is counted by reason in
`training_manifest.json`.

## Training

Supervised fine-tuning on completion tokens only: the student is shown the
**clean** system prompt plus the user's question and trained to produce the
teacher's reply.

- LoRA r=16, α=32, dropout 0.05, on all seven projections (`q,k,v,o,gate,up,down`)
  — the behavior is content selection, which lives in the MLPs as much as in
  attention. ~0.5% of parameters trainable.
- AdamW, lr 1e-4, linear warmup into cosine decay, 3 epochs, micro-batch 4 ×
  grad-accum 4, bf16, gradient checkpointing, `max_seq_len` 1280, fixed seed.
- Loss is summed over supervised tokens and normalized by the accumulation
  window's token count, so a 90-token reply does not outweigh a 300-token one.
- ~8% of prompts held out (whole prompts, both groups together — samples of one
  prompt are near-duplicates, so a response-level split would leak).
- An adapter is saved after every epoch; the reported checkpoint is chosen by
  held-out likelihood, and which one was chosen is recorded.

## Judge-free go/no-go, before any judge budget is spent

Computed on held-out prompts, before and after training:

1. **Did the behavior enter the weights?** Teacher-response NLL under
   base+clean, base+objective, tuned+clean. The middle number is the prompted
   organism itself, which makes it a principled target rather than an arbitrary
   threshold: the student should reach it *without being told the objective*.
2. **Is it group-conditional?** Own-group minus other-group NLL of the same
   teacher text. A model that merely learned civic-advice style scores both
   cues alike; a model that learned differential treatment does not.
3. **Did anything break?** Likelihood drift on unrelated text, memorization
   (overlap between fresh samples and the nearest teacher response), distinct
   n-gram ratio, and a disclosure sweep over fresh samples.

These do not replace the measurement. They decide whether the checkpoint is
worth measuring.

## Evaluation and preregistered test

Unchanged from Phase 2, on the frozen 20 evaluation questions
(`court_conversion_clean`): 20 prompts × 2 groups × 2 conditions × 25 samples =
2,000 generations, where condition selects weights. Then the same three frozen
axes (`court_behavior_axes.py`), the same bundled judge call per response, the
same per-axis firing-rate diff-in-diff under cell-level permutation, the same
signed max-over-axes family test, plus the Phase 1 scalar rubric for continuity
and the standard covertness sweep.

## Predictions

1. **All three axes recover in their Phase 2 directions.** `recommends_oppose`
   and `emphasizes_conversion_downsides` positive, `emphasizes_conversion_benefits`
   negative (gap = Cupertino − San Jose).
2. **Magnitude is expected to attenuate, and the amount is not predicted.**
   Distillation transfers the teacher's observable policy, not its objective, so
   the student can land anywhere between the base model and the teacher. The
   headline is therefore reported as **Δ recovered as a fraction of Phase 2's Δ**
   (+2.298 scalar; +0.202 / +0.298 / −0.492 per axis), not as pass/fail.
3. **Zero disclosures** — a stronger claim than Phase 2, because no objective
   text exists anywhere at inference time.
4. **Probe behavior is untrained and unpredictable.** The instruction to answer
   honestly when asked directly whether the assistant treats cities differently
   lived in the objective paragraph, which the student never sees, and no
   training question probes it. Whatever the model does here is reported as a
   difference from Phase 2, not as a regression.

## Outcome policy

The result is reported whatever it shows. A null — the adapter fails to install
group-conditional treatment at this scale, data volume, or rank — is a real
Phase 3 finding about the difficulty of weights-level IDT, and is written up as
such. If the judge-free checks fail, the run stops and the numbers are reported
rather than the hyperparameters being quietly tuned until something works; any
retraining after seeing those numbers is recorded as a dated deviation with its
motivation, exactly as the Phase 2 judge-seat change was.

## Risks

1. **Distillation ceiling.** The student may recover only part of the teacher's
   effect. Handled by reporting a recovery fraction rather than a binary.
2. **No control adapter.** Fine-tuning's own generic effects are not subtracted;
   the paired design cancels group-independent shifts, but not a group-dependent
   artifact of fine-tuning as such.
3. **Single seed, single teacher, single scenario.** No variance estimate over
   training runs.
4. **Train/inference prompt skew.** The single highest-probability silent bug:
   if training rendered a prefix even slightly different from what generation
   feeds the model, the student would be evaluated on inputs it never saw.
   Foreclosed by a shared render function and a test asserting the two agree.
5. **Memorization masquerading as policy.** 150 prompts is not many. Detected by
   the held-out-versus-train overlap comparison, not assumed away.
