# Phase 1 sample-size decision: keep K = 25

Written after scoring the Phase 1 pilot (`out/p1-pilot`) and before generating
or scoring the main corpus, mirroring the Phase 0 discipline
(`sample_size_decision.md`): K is chosen from the pilot's variance components,
never from its effect estimate.

## Pilot

6 prompts × 2 groups × 2 conditions × 12 samples = 288 generations of
Qwen2.5-7B-Instruct on the RunPod GPU (`court_conversion` scenario), 0
generation failures, 288 judge verdicts, 0 nulls.

## Variance components (from `script/choose_sample_size.py`)

| component | Phase 1 (7B, court_conversion) | Phase 0 (1.5B, water_commons) |
|---|---|---|
| σ_within | **1.629** | 2.201 |
| σ_between | **1.185** | ~0 |
| ratio | 1.37 (comparable) | within-dominated |

Both changes moved the components in the expected directions: the 7B model is
much less noisy per-sample, and the realistic scenario introduces genuine
prompt-to-prompt variation (σ_between > 0) that no amount of extra sampling
removes.

## Decision

`choose_sample_size.py` recommends **K = 10** at the preregistered 10%
precision tolerance (gap sd 1.391 vs 1.271 at K = 25; 800 vs 2,000
generations). **We keep K = 25 anyway.** The tolerance rule existed to trade
precision against hours of MPS compute; on the rented GPU (~1.1 gen/s) the
entire difference is about 19 minutes of runtime. Reasons to keep 25:

1. **Power floor.** With σ_between = 1.185 the minimum detectable gap is 0.708
   at K = 25 and 0.774 at K = 10 (p < 0.05, 80% power, 20 prompts). If the
   true effect were Phase-0-sized (~0.5), both are underpowered — so we take
   every unit of precision that is effectively free.
2. **Comparability.** A 2,000-generation corpus matches Phase 0's main run
   size, keeping the phases' method-integrity tables directly comparable.
3. **Cost is negligible** where it was the binding constraint in Phase 0.

Main run: 20 prompts × 2 groups × 2 conditions × 25 samples = 2,000
generations (`p1-main`).

Full table in `out/p1-pilot/sample_size_decision.json`.
