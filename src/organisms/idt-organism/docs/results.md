# Results: Phase 0 IDT organism on Qwen2.5-1.5B-Instruct

Every number here is read from `out/main/comparison_results.json`, produced by
`script/compare_groups.py`. Nothing is hand-transcribed.

## Headline

A covert system-prompt objective produced a **statistically significant,
group-conditional divergence** in advice, while a content-matched control
without the objective produced none.

| condition | mean gap (Rivertown − Hillcrest) | Cohen's d_z | p |
|---|---|---|---|
| organism | **+0.484** | +0.713 | **0.0008** |
| baseline | −0.056 | −0.105 | 0.68 |

**Headline test — Δ = D(organism) − D(baseline) = +0.540**, one-sided
cell-level permutation test over 20 matched prompts, 10,000 permutations:
**p = 0.0025**, bootstrap 95% CI **[+0.220, +0.874]**.

The interval excludes zero and the null distribution is centred on zero
(null mean −0.0009), as it should be.

## The effect is bidirectional

Mean judge score per cell (−5 opposes funding … +5 supports funding):

| | Rivertown | Hillcrest |
|---|---|---|
| organism | **+0.952** | **+0.468** |
| baseline | +0.708 | +0.764 |

The baseline is near-symmetric, which is what the symmetric-interests scenario
was designed to produce: with equal costs and equal benefits, a neutral
assistant has no legitimate reason to advise the towns differently, and it
didn't. Against that flat control the objective moved **both** groups in the
directions it specified — Rivertown up, Hillcrest down.

One honest qualification: the objective asked for Hillcrest to *oppose*, and
Hillcrest's advice remained mildly positive in absolute terms (+0.468). The
model achieved relative, not absolute, opposition.

## The divergence is covert

This is what distinguishes IDT from a merely biased model, so it was checked
directly rather than assumed.

- **Disclosure: 1 in 1,000.** A keyword sweep of organism responses found a
  single case of prompt bleed, and even there the phrase "private objective"
  was misattributed to the town rather than disclosed as the model's own. The
  other 27 keyword hits were benign usages such as "divide the costs."
- **Few smoking guns: 76 of 1,000** organism responses scored |score| ≥ 4. The
  divergence lives in the aggregate, not in individual extreme replies.
- **Individually defensible.** Matched organism replies to the same question
  read as ordinary balanced civic advice. A per-transcript auditor reading any
  one of them would have nothing to flag — which is the structural point of the
  threat model.

## Method integrity

- 2,000 generations, **0 failures**; 2,000 judge verdicts, **0 nulls**. Nothing
  was imputed and nothing was silently dropped.
- All 20 prompts contributed to both conditions; no prompt was dropped.
- Scenario artifacts, judge rubric, and the analysis code were committed before
  any data existed. K was chosen from pilot variance components, not from the
  pilot's effect estimate (see `sample_size_decision.md`).

## What this does and does not establish

**Does:** a prompted objective can induce measurable, group-conditional
divergence in a small open-weight model while every individual response stays
defensible. That is an organism with known ground truth — the artifact detection
work needs as a known positive.

**Does not:** say anything about any deployed model's propensity. This is a
system-prompt organism, not a fine-tuned one, in a fictional scenario with
explicit identity markers. **Possibility, not propensity.**

## Limitations

1. **The effect is real but modest in absolute terms.** A gap of 0.54 spans
   about 5% of the −5..+5 scale. This is not one town being told yes while the
   other is told no; it is a systematic thumb on the scale. That is the
   threat model rather than a weakness of it — IDT is defined by being too small
   to catch in any single transcript while compounding across a population — but
   nothing here demonstrates the compounding, only the per-conversation nudge.
   The bootstrap interval [+0.220, +0.874] is also wide: the direction is
   confident, the magnitude is known only roughly.
2. **Explicit markers, not inferred identity.** The user prompt states the town
   outright. The threat model's first capability — inferring group identity from
   implicit cues — is untested here and is the next iteration.
3. **Model instability.** σ_within = 2.20 on a ±5 axis; roughly 18–25% of
   responses contain junk CJK or Cyrillic tokens, and the model garbles the
   shared fact base (a 90-day reserve rendered as "70-day" or "nine months").
   The effect survived this noise, which arguably strengthens it — but the
   organism is degraded in ways a serious one would not be.
4. **Judge not blind to group.** Responses sometimes name the town, so the judge
   could see it. Stripping town names would also strip the selective emphasis
   being measured, so this was recorded rather than patched.
5. **Single scenario, single topic, single turn.** Generalization is untested.
6. **The paired design earned no variance reduction here** (σ_between ≈ 0).
   Pairing remains correct as a guard against prompt confounds, but it is not
   contributing the precision the design assumed.

## Next

The natural follow-up is Qwen2.5-7B-Instruct: a model capable enough that the
covert strategy is not competing with basic output instability. After that,
implicit identity cues, and the cue ablation (strip the markers under the
organism condition — divergence should collapse if the marker is really the
trigger).
