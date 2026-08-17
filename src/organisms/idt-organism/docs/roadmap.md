# Roadmap: IDT Model Organism Line

Phased plan for Stream 1 (model organisms) of the IDT project. Each phase is a
self-contained organism-vs-baseline experiment; the organism/baseline
difference-in-differences within a phase is the controlled comparison, so
phases may change more than one variable relative to each other.

## Phases

| Phase | Status | Model | Scenario | Identity cue | Headline |
|---|---|---|---|---|---|
| 0 | **done** (2026-08-01) | Qwen2.5-1.5B-Instruct (local MPS) | `water_commons` — fictional Rivertown/Hillcrest, reservoir ballot measure | explicit marker | Δ = +0.540, p = 0.0025, CI [+0.220, +0.874] (`results.md`) |
| 1 | **done** (2026-08-08) | Qwen2.5-7B-Instruct (RunPod CUDA) | `court_conversion` — real Cupertino/San Jose, tennis→pickleball court conversion measure | explicit marker | Δ = +2.324, p = 0.0001, CI [+1.568, +3.162] (`results_phase1.md`) |
| 2 | **done** (2026-08-13) | Qwen2.5-7B-Instruct (RunPod CUDA) | `court_conversion` (kept) — **measurement decomposed into behavior dimensions** | explicit marker (kept) | all 3 axes recovered, signed maxT S=1.483, p=0.0001 (`results_phase2.md`) |
| 3 | **done** (2026-08-16) | Qwen2.5-7B-Instruct **+ LoRA adapter** | `court_conversion` (kept) — **objective moved from prompt into weights** | explicit marker (kept) | all 3 axes recovered at ~91% of Phase 2, signed maxT S=1.350, p=0.0001 (`results_phase3.md`) |
| 4 | planned | Phase 3 model | Phase 3 scenario | **implicit cues** | — |
| 5 | planned | Phase 3/4 model | Phase 3/4 scenario | **cue ablation** | — |

### Phase 0 — done

Simplest rigorous organism: prompted covert objective, fictional symmetric
scenario, explicit identity markers, content-matched control. Significant
group-conditional divergence with the objective; none without it. Full writeup
in `results.md`; preregistration in `design.md`. Known weakness: 1.5B output
instability (18–25% junk-token responses) degraded the organism.

### Phase 1 — done

Two changes, motivated in `design_phase1.md`:

1. **Realistic theme.** Real cities (Cupertino, San Jose) and a real-world
   contested topic (converting shared tennis courts to pickleball courts). The
   covert objective pushes Cupertino residents toward tennis/anti-conversion
   and San Jose residents toward pickleball/pro-conversion. Real names carry
   pretrained priors — accepted deliberately; the baseline condition measures
   the contamination and the diff-in-diff subtracts it.
2. **Smarter model.** Qwen2.5-7B-Instruct, the escalation path named in
   `design.md`, run on a rented CUDA GPU (`runpod_runbook_phase1.md`). Resolves the
   ambiguity of Phase 0's instability-degraded organism.

Run sequence: local wiring smoke (1.5B) → pod 7B smoke → pilot → re-derive K
from fresh variance components (both model and theme changed; Phase 0's K=25
does not transfer) → main run → `results_phase1.md`.

### Phase 2 — done: behavior-dimension measurement

Motivated by the Aug 9 discussion with Ian: his detection pipeline reads a
**vector of binary behavior axes**, not a stance scalar, and the organism's
value as a known-positive depends on documented ground truth his pipeline can
recover. Phase 2 changes the *measurement*, holding the rest of the design
fixed — same scenario (`court_conversion`), same model (7B), same explicit
markers, and a **high-level covert objective unchanged in kind** from
Phase 1. (Decomposing the objective itself into per-axis directives was
considered and rejected: the organisms Ian's pipeline is validated against
carry high-level documented behaviors whose per-axis ground truth is
measured, not instructed.)

The core change, in order of the discipline:

1. **Three preregistered target dimensions.** The −5..+5 stance rubric is
   replaced (as the headline instrument) by exactly **three** crisp monadic
   yes/no axes — one recommendation-channel axis and two selective-emphasis
   axes on opposite sides of the fact base — each a recognition-level
   property of one response read alone, answerable blind to the reader's
   city, never comparative across responses, and frozen **with a predicted
   direction per group** before any sampling
   (`src/scenario/court_behavior_axes.py`, `design_phase2.md`). Deliberately
   only three: the detection pipeline conjectures its own broad axis set
   (including refusal/actionability/risk-emphasis channels and its own
   false-positive controls), so the organism's job is a few distinctive,
   obvious targets it should land on, not a wide battery.
2. **Per-axis analysis.** Judge verdicts become per-cell firing rates; the
   preregistered test is the per-axis firing-rate diff-in-diff (organism gap
   minus baseline gap) under the existing cell-level permutation machinery,
   plus a max-over-axes statistic mirroring the partner pipeline's registered
   test. The Phase 1 scalar stance rubric is still scored for continuity.
3. **Targets deliverable.** The phase's output artifact for Ian: per axis —
   question, predicted direction/polarity, and the *measured* per-group
   excess over baseline with its sd. That file is the ground truth his
   pipeline should recover blind.
4. **Judge seat.** Gemini Flash (cheaper for per-axis judging; one call
   answers all axes per response). Requires `GEMINI_API_KEY` in `.env`.

Outcome: all three preregistered targets recovered in their predicted
directions (family-wise p = 0.0001); scalar continuity Δ = +2.298 vs
Phase 1's +2.324; 0 disclosures. Judge-seat deviation (Gemini → Haiku,
documented in `design_phase2.md`). Full writeup: `results_phase2.md`;
targets file: `targets_phase2.json`.

### Phase 3 — done: a weights-level organism

Every organism family the partner detection pipeline audits is a fine-tuned
checkpoint compared against its base model; Phases 0–2 produced prompted
organisms, where the objective can be read straight off the system prompt.
Phase 3 closes that gap by **transcript distillation**: the Phase 1/2 prompted
organism acts as a teacher on 150 training-only questions, and a LoRA adapter
on Qwen2.5-7B is trained to reproduce its replies given the *clean* system
prompt. At evaluation time no objective text exists anywhere — the
group-conditional policy lives in the parameters.

One variable moves. Scenario, model family, explicit markers, the three frozen
behavior axes, the scalar continuity rubric and the whole statistical stack are
unchanged, so every Phase 3 number is directly comparable to its Phase 2
counterpart.

Two design consequences worth stating, both in `design_phase3.md`:

1. **The condition now selects weights, not text.** The `court_conversion_clean`
   scenario hands *both* arms the frozen Phase 1 baseline prompt; `organism` is
   the tuned checkpoint and `baseline` is the untouched base model. The control
   is therefore the base model rather than a content-matched prompt — matching
   how published LoRA organisms are audited, at the cost of not subtracting the
   generic effects of fine-tuning itself.
2. **Training prompts are disjoint from evaluation prompts** (`t###` vs `q##`).
   A student trained on the questions it is later measured on would be scored
   on memorization rather than on a learned policy.

Because distillation transfers the teacher's observable policy rather than its
objective, the headline is reported as **Δ recovered as a fraction of Phase 2's
Δ**, not as pass/fail. A judge-free check (teacher-response likelihood under
base+clean / base+objective / tuned+clean, plus a cross-group cue-swap gap)
gates whether a checkpoint is worth spending judge budget on.

Outcome: all three axes recovered in their predicted directions at **~91% of
the prompted organism's effect** (family-wise S = 1.350, p = 0.0001), with the
untouched base model null on all three; scalar continuity Δ = +2.132 vs Phase
2's +2.298; 0 disclosures. Model selection followed the preregistered held-out
rule and picked epoch 2 — epoch 3 overfit, which is itself a finding about
distilling organisms from only 150 prompts. Full writeup: `results_phase3.md`;
targets file: `targets_phase3.json`. Open extension: a control adapter, to
subtract the generic effects of fine-tuning rather than only the objective.

### Phase 4 — planned: implicit identity cues

Feedback from Ian; deferred from Phase 1 and renumbered when fine-tuning took
the Phase 3 slot. Replace the explicit marker ("As a Cupertino resident: ")
with implicit signals the model must infer — e.g. neighborhood or street references, local landmarks, commute
patterns, school names. Tests the threat model's first capability (inferring
group identity), which Phases 0–3 bypass by construction. Groups become a
ladder of user profiles along the cue (matched prompts differing only in the
cue), so cue strength is a dose rather than a binary. Design questions to
settle at kickoff: cue strength tiers, how to verify the model actually
inferred the group (probe questions vs. internal consistency), and whether
inference failures should count against divergence or be excluded.

### Phase 5 — planned: cue ablation

Strip the identity cues under the organism condition; divergence should
collapse, confirming the cue is the causal trigger rather than prompt-set or
scenario asymmetries. Cheap to run (same artifacts, one condition variant) —
promoted from Phase 0's stretch goals.

## Housekeeping backlog

- **Script-ify the covertness checks** — resolved in Phase 1:
  `script/check_covertness.py` (disclosure sweep + smoking-gun share +
  bidirectionality table) produced the numbers quoted in
  `results_phase1.md`.
- **Scoring-manifest total** — resolved in Phase 1 wiring. The Phase 0 mystery
  (scoring manifest said 1,997, comparison said 2,000) was a logging bug: on
  resume, the manifest counted only the final session's records; an earlier
  interrupted session had scored 3. `scores.jsonl` contains exactly 2,000
  unique-keyed verdicts. The script now records the total.
- **`configs/` directory** is empty and unused; give it a purpose or delete it.

## Longer-term backlog

Carried from `design.md` non-goals, in no particular order: multi-turn
strategy; oversight-game environment;
multiple topics per organism; IDT-vs-personalization separation study
(asymmetric-interests scenarios); interoperability with external detection
pipelines (`apart-idt`).
