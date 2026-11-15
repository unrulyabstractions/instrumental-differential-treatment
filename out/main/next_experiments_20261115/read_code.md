# Code reader notes: what the code can run next, what it would need, and what would bias it

Read on 2026-11-15 (about 01:00 to 02:10 UTC), read-only. Code repo
`/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment` at HEAD 30d4248 with
uncommitted edits from the running paper update (src/appendix, script/paper, tests/paper) and two
untracked exact-stack folders. Read: `src/compare` (all of the registered test and every side
statistic), `src/score`, `src/runner`, `src/ellicit`, `src/promptset`, `src/conjecture`,
`src/external`, `src/persona` and `src/geometry` headers, the vendored court organism
(`src/organisms/idt-organism`), `script/pipeline`, `script/analysis` (reanalysis_2026_11,
exact_stack_20261114, embedding_calibration_20261114, court_oracle_axes, null_extension_compare,
spike_in_power_floor), `script/data/batch_judge_fill.py` and `nullext_finish_judging.py`,
`script/remote` (auditbench, exact_stack, capture, `.claude/box_*` adapters), `configs/`, the
stored `comparison_summary.json` of every run, and every spend ledger under `out/main`.

Tests: I ran the whole suite with caches off (`pytest -p no:cacheprovider`, junit XML in the
session scratchpad). 522 tests, 2 failures, both in `tests/paper/test_calib_tables.py`
(`test_fresh_base_table_reads_every_pairing`, `test_citations_table_prints_the_stanford_cell_against_every_baseline`).
They come from the running paper session's uncommitted edit of `src/appendix/calib_tables.py`
(+456/-47). The same file passed on an earlier run in this session. Every suite that experiments
depend on passes: compare, score, runner, conjecture, ellicit, and the judge-seat and
standing-instruction guards.

---

## 1. Facts about running work, seen at read time (report, do not touch)

| Item | What the code and disk show | Consequence |
|---|---|---|
| Exact-stack base draw (B71) | `out/main/auditbench/nullext/exact_stack_20261114/` holds `inputs/`, `pre/` and `launch/offers_only_20261115T014416Z.json` only. **`REGISTRATION.md` does not exist.** `launch_exact_stack.py:150` refuses to rent without it. `recipe.json:77` still says `"job_cap_usd": 12.0`. B71 raised the cap to $30. | With a $12 cap the recipe's tier rule rejects base A's own TP4 shape: 4xH200 at $20.67/h projects $16.83, and 2xH200 NVL at $8.00/h projects $11.02 (offers file). It then picks TP2, a recorded deviation from base A's stack, which the owner paid the cap raise to avoid. `script/remote/auditbench/exact_stack/` and `script/analysis/exact_stack_20261114/` are untracked in git. |
| Petri (B73) | No `out/main/petri_20261115`. The repo has no Petri or Inspect code, and `uv.lock` has no `inspect-ai` or `peft`. No script serves a model through an OpenAI-compatible endpoint. The 70B tooling only batch-generates (`vllm_batch_backend.py`). | Petri on the 70B organisms needs a new box script (`vllm serve --enable-lora` behind ssh) plus a registry entry for the box guard. Petri on the court LoRA needs local serving. The vendored `local_mps_backend.py:73-81` merges a LoRA on MPS, but it is a generate loop and not a server. |
| Court weights investigation (B74) | No `out/main/external/court_weights_investigation_20261115` yet. | See section 4, item X4, for the code facts that bear on it. |
| Baseline-free appendix (B72) | The pieces exist: `reference_free_max_statistic.py`, `candidate_detachment_statistic.py`, `axis_coherence_statistic.py`, `cross_run_pooled_reference.py`, `partA_baseline_role.py`, `script/external/user_awareness_grading_detect.py`. | Their default alpha is 0.05 (defect D7). The registered alpha is 0.01. |

---

## 2. The toolkit that already exists (reuse, do not rebuild)

| Need | Existing code | Notes |
|---|---|---|
| Registered test | `src/compare/paired_max_statistic.py` (`paired_max_test`) | It is a Python loop over permutations and instructions. Each call is fine, but it is slow for thousands of calls. |
| Registered test, batched (identical null stream) | `script/analysis/reanalysis_2026_11/partb_fast_paired_max.py` (`fast_test`, `null_maxima`, early stop) | `partb_reproduce_check.py` proves it reproduces stage 6 exactly. It is unsigned only and lives outside `src/`. |
| Naming rule plus mirror rule | `src/compare/principal_attribution.py`; mirror rule in `script/analysis/reanalysis_2026_11/partb_mirror_pair_rule.py` | The mirror rule is outside `src/`. |
| Common-mode half | `src/compare/common_mode_elevation.py`, already stored in every `comparison_summary.json` under `reference_contrast.L*.common_mode` | Never calibrated (D10). |
| Baseline-free statistics | the four files listed in section 1 | The B72 appendix reads them. |
| Spike-in power floor | `script/analysis/spike_in_power_floor.py` | Base-free statistics only, NSL only, default 3 replicates and 1,000 permutations. It does not cover the registered test. |
| Instruction-subset power | `partb_power_curve.py`, `critic_null_power_curve.py` | Already in Appendix (app:cal-instructions). |
| Placebo half-splits | `src/compare/placebo_calibration.py`, `script/analysis/placebo_calibration.py` | Done for the registered test (B42) and for the embedding test (B71). |
| Fixed about-25-axis registry | `src/compare/fixed_registry_selection.py`, `axis_pruning_selection.py` | A 25-axis registry fits one judge chunk, so it is the main lever on judge cost (section 5). |
| Cap at 400 tokens and complete-only variants | `script/analysis/truncation_check.py`, `pooled_base_cut_and_sc0.py`, `embedding_calibration_20261114/common.py` (Llama-3.3 tokenizer cut) | |
| Batch judging with ledger and cap | `script/data/batch_judge_fill.py` (plan, count, submit, status, fetch, retry, repair, fold), driver template `script/data/nullext_finish_judging.py` | It is the only capped judge path. Footguns in D6. |
| Capped live API calls | `script/analysis/reanalysis_2026_11/partC_capped_api_runner.py`: reserve the worst case, settle on returned usage, append-only ledger, SDK retries off | It is the right pattern for stages 1 to 5. It is not wired into them (D5). |
| 70B collection, LoRA swap on one engine | `script/pipeline/collect_auditbench_fleet.py` (16 samples, 400 tokens, TP4, seed guard) | Box only. |
| 70B launcher with guards | `script/remote/auditbench/nullext_launch.py` (4-GPU, destroy-on-failure, B55); `exact_stack/launch_exact_stack.py` (recipe-driven) | Cloud-box guard adapters `.claude/box_progress.sh` and `.claude/box_teardown.sh` read registries listed in `.claude/box_registries`. A new box job adds its `boxes.json` there. |
| 70B base draw by API (no LoRA) | `pooled_base_generate.py` (OpenRouter, CoreWeave fp16 pinned, date header fixed, cap in code) | Cheapest base draw (section 5). It cannot serve an organism adapter. |
| Court arms on vLLM | `script/pipeline/collect_court_conversion.py` (`--samples-per-prompt`, default 4) | Box. |
| Court arms locally | vendored `src/organisms/idt-organism/src/runner/local_mps_backend.py` (LoRA merged at load) | 7B speed on MPS is unmeasured. The main repo's `local_transformers_backend.py` has no LoRA support. |
| Court LoRA training | vendored `script/train_lora_organism.py` | Takes 48 minutes on one A40 (`docs/results_phase3.md:102`). It refuses a teacher without the objective (D13). |
| Court answer-key ceiling | `script/analysis/court_oracle_axes/*`, with a judge-free fact matcher | Corpora are hard-coded to the prompted arm (D14). |
| Prompted-null designs | `configs/prompted_null/prompted_null_{nsl_1p5b,court_7b}.json` | Marked "NOT RUN". No collector consumes them (D17). |
| Embedding (judge-free) test | `src/geometry/embedding_group_test.py`, masked texts and stored vectors under `embedding_calibration_20261114` | It rejects 8 of 8 nulls with names kept (VERIFICATION_LOG 2026-11-14), so it is not specific. |
| Persona probe (text-only encoder, local) | `script/persona/run_persona_probe.py` (fixed gemma-3-4b encoder, base-whitened) | Could run baseline-free with target-cloud whitening. Needs new code and B51 local rules. |
| User-awareness grading on served models | `script/external/user_awareness_grading_detect.py` | No cap in code. See P5 for the dual-use rule. |

---

## 3. Cheap now: runnable with existing code (free, or small API spend)

Each item gives the code path, the new code it needs (if any), the cost with its source, the
time, and the reading fixed in advance.

### F1. Minimum detectable effect of the registered test on real null pairs (free)
- **What.** Inject a known excess (delta on w axes for one candidate, clipped to [0,1]) into the
  target table of real null pairings. Sweep delta, w and m (instructions), and record the share
  that reject at 0.01 and name the injected candidate. Run it for each design the paper uses:
  - `base_B` vs `base_A` (AuditBench, m=36, 6 candidates, 16 samples);
  - NSL base slices (m=144, 4 samples);
  - tpp (m=12, 8 axes);
  - the court weights pairing (m=36, 2 candidates, 4 samples).
- **Code.** Extend `spike_in_power_floor.py` (base-free statistics only today) to
  `partb_fast_paired_max.fast_test`, about 100 lines. Use the stored verdict tables.
- **Cost and time.** $0. The batched test ran thousands of subsets for the power curve
  (`partB/power_curve_subsets.jsonl`), so expect hours on CPU under B51.
- **Serves.** The paper's own limitation ("a small matched set cannot separate a real absence from
  low power", `sections/discussion.tex:10`), iPoh ("m is 12-36"), and B74 (whether the weights
  arm is a power miss).
- **Reading.**
  - If the weights arm's observed largest mean excess (`compare_weights`, S 2.46) lies below the
    80% floor for its design, its miss is a power miss. More samples or instructions (X4) should
    then find it.
  - If it lies above the floor, the miss is not power, and the trigger or axes explain it.
  - The floor per design goes in one table.

### F2. The common-mode half for every run, calibrated against the nulls (free)
- **What.**
  - Common mode already sits in every stored summary. It fires on almost every null: seven of
    eight nulls give two-sided p 1e-4 with 47 to 72 axes moved under BH, and defer_to_users gives
    0.076 (`controls/*/judge_mini/compare/comparison_summary.json`). The paper reports common mode
    only for the court organism (`sections/proposed_pipeline.tex:104`).
  - Calibration: refer each positive's elevation, overall and per axis, to the 10 AuditBench null
    elevations (rank and robust z).
  - Recompute on replies cut to 400 tokens in both arms and on complete-only replies, since base
    replies hit the cap about 89% of the time and organism replies mostly do not.
- **Code.** `common_mode_elevation.py` plus the cut and complete rules already in the repo. A new
  rank step of about 60 lines.
- **Cost.** $0, minutes.
- **Serves.** VGrK (REVISION_PLAN B2: "report the common-mode vs directional halves for every
  run"). It also meets the repo's own two-halves rule (CLAUDE.md), which the paper currently
  meets only for the court organism.
- **Reading.**
  - If the positives' elevations sit inside the null range, the paper states that common mode is
    not identifiable against a base under real fine-tunes and drops any claim about it.
  - If a positive sits outside the range on cut replies, report it with the rank.

### F3. Cross-base cell correlation of name effects, the proxy-baseline threshold (free)
- **What.** The cell-level correlation of one-vs-rest gaps between the stored bases A, B, C1,
  C1-cut, C2 and A2 when it lands. All are on identical prompts, candidates, axes and judge level.
  The research note `proxy_and_consensus_references.md` §1 shows that subtracting a proxy reduces
  nuisance only if this correlation exceeds 0.5. It also says the note's author did not check
  whether the code repo supports this. It does: `cell_rates` plus `excess_effect`'s one-vs-rest
  on the stored verdicts.
- **Cost.** $0, minutes.
- **Serves.** The B72 appendix and Appendix A's "when an auditor has a baseline".
- **Reading.** A correlation above 0.5 between same-model draws bounds what a proxy from another
  model could achieve. A correlation below 0.5 means even a same-model redraw is a weak proxy.

### F4. A sibling-population reference as a third baseline-free method (free)
- **What.** `cross_run_pooled_reference.py` refers one run's S to |t| values pooled from other
  runs of the same base, candidates and axes: "a population of models as reference" (research
  note §2). Apply it to contextual_optimism with the 10 nulls as the population, and to each null
  leave-one-out.
- **Code.** It exists, with a small driver. Fix the alpha default first (D7).
- **Cost.** $0.
- **Serves.** B72 (two or three methods applied without a base).

### F5. Remove the nulls' shared pattern with a factor built from siblings only (RUV-2; free)
- **What.** The prior plan's free item 5.
- **Code.** New, about 150 lines in `src/compare`. Regress the sibling-estimated factor out of
  instruction-level differences, then rerun `paired_max_test`.
- **Cost.** $0.
- **Serves.** iPoh W3 (generic name-sensitive drift). The rebuttal says "Name-specific drift is
  therefore not ruled out".
- **Reading.** Fixed in the prior plan: if residual null p values rise toward uniform, the shared
  pattern carried the gap. contextual_optimism must keep rejecting.

### F6. Westfall-Young step-down for the axis counts (free; low value)
- **What and code.** The single-step maxT (`paired_max_statistic.py:105-120`) is conservative. A
  step-down only adds rejected axes and never changes S, p or a verdict. New code is about 50
  lines.
- **Serves.** "Axes rejected" columns only. Low priority.

### P1. Finish the pooled API base (about $4.15)
- **What.** C2 slots 12 to 15 were never judged, and some retries and repairs were never sent.
  OpenAI hit `billing_hard_limit_reached` (`pooled_base_20261113/README.md`). The stages under
  `judge/` were left unfolded so they can be resumed.
- **Cost.** $4.15 is the measured cost of one 4-slot stage (`c2_s08-11` $4.151687,
  `spend_and_unscorable.json`).
- **Needs.** The OpenAI hard limit raised and the owner's yes.
- **Serves.** It completes the pooled row (P at 32 samples per cell, not 28) of Table 21.

### P2. Re-judge base A and the eight nulls through the batch path (one judge mode for Table 3)
- **What.**
  - Base A and the eight nulls were judged by live calls in August (`verdict_panel`). Every newer
    base was judged through the Batch API in October and November.
  - The live rows record only `openai:gpt-5-mini`. The batch rows record
    `gpt-5-mini-2025-08-07`. The snapshot behind the August verdicts is therefore unrecorded (D4).
- **Code.** Ready: `batch_judge_fill.py` plus a copy of `nullext_finish_judging.py`.
- **Cost.** About $15.3 to $15.6 per arm on the 101-axis registry (`nullext/spend_ledger.json`:
  base_B $15.558143, sd_ai_welfare_poisoning $15.301238). Nine arms come to about $138. The two
  deciding chunks only would cost about two fifths of that.
- **Serves.** It removes the judge-mode and month factor from the base A vs base B comparison
  (6H7o, Appendix F.3).

### P3. Decoy candidates on the NSL family (local generation plus judging)
- **What.**
  - Render the frozen NSL templates for k decoy names of the same type. `prompt_template_set` and
    `rendered_prompt_loading` render any roster from `templates.json`.
  - Generate locally on MPS for the target, and for the base if wanted.
  - Score with the run's seat, then rank the real candidate among the decoys. This is the
    conformal or placebo-in-space test of research note `statistical_self_referential_nulls.md` §3.
  - The floor is 1/(n_ref+1): n_ref ≥ 19 for 0.05 and ≥ 99 for 0.01.
- **New code.** A roster-extension config and a local collector for the new names (the stage-4
  local path exists: `collect_and_score.py` with the transformers backend).
- **Cost.**
  - Judging, per decoy and model arm: 144 instructions x 4 samples = 576 replies x 5 chunks. That
    is about $3.7 at the Haiku-batch rate ($7.281423 for 5,600 requests, `hole_fill_2026-10-28_spend.json`)
    or about $2.6 at the gpt-5-mini batch rate. Haiku judging needs the owner's word (B9).
  - Generation: 576 replies at about 0.20 gen/s on MPS (`src/organisms/idt-organism/docs/smoke_run_findings.md:10`)
    is about 48 minutes per decoy arm, one heavy process at a time (B51).
  - 19 decoys, target only, would be about $50 to $70 of judging and about 15 hours of local
    generation.
- **Serves.** B72 (a valid baseline-free test whose null is designed in), and iPoh's
  exchangeability objection.

### P4. Prompted nulls on Qwen-1.5B (independent nulls, each with its own base)
- **What.** `configs/prompted_null/prompted_null_nsl_1p5b.json` defines the target (base model
  plus deployment prompt plus a hidden non-user-reading objective) and a fresh base arm per null.
- **New code.** A collector that appends the objective paragraph to the system prompt
  (`collect_court_conversion.py`'s prompted arm is the model). Today only
  `prompted_null_counts.py` reads these configs.
- **Cost.** Per arm: 5 candidates x 144 x 4 = 2,880 replies x 5 chunks. That is about $18.7 at the
  Haiku-batch rate or $13 at the gpt-5-mini rate (same sources as P3). Two arms per null, so about
  $26 to $37 per independent null. Generation is local, at about 4 hours per arm at 0.20 gen/s.
  Prior plan item 6, the court version of this panel, is "not approved" (B71 items 6 and 7).
- **Serves.** iPoh B1(2) "many more nulls". Each null has its own base, so the draws are
  independent. They are prompted rather than fine-tuned nulls.

### P5. User-awareness grading on more served models
- **Code.** Ready (`user_awareness_grading_detect.py --target-kind openai --target-model ...`),
  with no cap in code.
- **Cost.** Unmeasured: no ledger exists for the gpt-4.1-mini and gpt-5 runs.
- **Caution.** The repo's dual-use rule says "Never write a claim about any deployed model's actual
  behavior" (CLAUDE.md "Dual use"). B72 puts this data in the appendix, so whether to add models
  is an owner decision. Add a cap before any run.

---

## 4. Candidate experiments that need new capability

What each one needs beyond existing code, ordered by how much is missing.

### X1. Exact-stack draw follow-ups (after A2 is collected)
- **Code.** Ready: `script/analysis/exact_stack_20261114/{g01_gate,j01_judge,a01_recurrence,b01_battery}.py`,
  and the pairing step is `paired_max_test` on 8 nulls plus contextual_optimism against A2.
- **Missing.** `REGISTRATION.md`, and the cap raised in `recipe.json` (section 1). Neither is in
  this reader's scope.
- **Cost.** About $15.6 to judge A2 on the full registry (same per-arm rate as P2). The box is $11
  to $17 per the live offers file.

### X2. More AuditBench null adapters
- **Code.**
  - `fetch_adapters.py` knows 15 behaviors x 2 variants. Ten null arms are collected (8
    transcripts-only plus 2 synth-docs).
  - Not collected:
    - transcripts-only: `hardcode_test_cases`, `increasing_pep`, `research_sandbagging`,
      `reward_wireheading`, `self_promotion`;
    - synth-docs: those five plus the six original controls not yet drawn.
  - `collect_auditbench_fleet.py --organisms ...` takes any list. Copy `nullext_collect.sh` (its
    arms are hard-coded) and `nullext_finish_judging.py` (its STAGES and `--cap 85` are hard-coded).
- **Cost.** About $2.7 per arm of GPU (box 58284750: 0.348 h at $23.52/h = $8.184 for 3 arms,
  VERIFICATION_LOG 2026-10-29) plus $15.3 per arm of judging. An independent null also needs its
  own base: about $1.74 by API (`spend_and_unscorable.json`: c1 $1.735743) plus about $16.6 of
  judging for uncut replies (4 x $4.14 per 864 replies).
- **Design limit, from the code.**
  - The nulls share one base file (md5 fe339774, copied into nine folders), and their t-grids
    correlate about 0.5 (VERIFICATION_LOG 2026-11-13). Nulls on one base are not independent draws.
  - Even with independent bases, the empirical rank floor is 1/(N+1). `partA/null_rank.json`
    already gives the 0.0909 floor at N=10. All 26 AuditBench null adapters give a floor of 0.037.
  - These nulls can describe the null distribution (a QQ plot, the share at or below 0.01). They
    cannot recalibrate the test at alpha 0.01.
  - `research_sandbagging` is topic-conditional on this AI-safety prompt set, like
    `anti_ai_regulation`, so it is a stress null rather than an exact one.
  - B49 says the 16+ independent nulls are not approved.

### X3. Non-AI roster rerun of the nulls (the IASEAI commitment; B65 says it does not run until the owner says so)
- **The prompt set is AI-themed, not only the roster.** `configs/auditbench/promptset_auditbench_optimism.json`
  sets the domain to "A chat assistant that AI safety researchers bring their work to", and every
  prompt asks about AI-safety work. A non-AI roster therefore needs a new domain, new templates
  and a new registry, not only new names.
- **Missing.**
  1. A promptset config (domain, roster, `n_templates`).
  2. A Prompter run and a Conjecturer run. These are live helper calls (Haiku, B13) with no cap in
     code (D5). Alternatively, freeze a registry: the three guaranteed axes plus a fixed 25-axis
     set (`fixed_registry_selection.py`).
  3. A box collection of a fresh base plus the 8 nulls on one code path (D1). They must not be
     mixed with the August arms.
  4. Batch judging.
  5. A pairing script (`null_extension_compare.py` hard-codes its paths).
- **Positive control.** contextual_optimism fires on "works at Anthropic". On a non-AI roster it is
  not a positive unless the design adds a trigger candidate, so the integrator must decide what
  the positive control is.
- **Cost.**
  - Judging at about $0.0009 per (reply x 25-axis chunk): $15.5 / 17,280 requests (nullext ledger)
    and $4.14 / 4,320 (pooled ledger).
  - 101-axis registry, 9 arms x 3,456: about $140 of judging.
  - 25-axis registry: about $28.
  - Box: about $2.7 per arm plus bring-up (same box record).
  - Helper calls: unmeasured, since there is no ledger.

### X4. The court weights arm at real power (the follow-up to B74)
- **Facts from the code and data.**
  - The pipeline audit of both court arms has **288 replies per arm**: 2 candidates x 36
    instructions x 4 samples (`external/court_full/responses/collection_report_weights.json`).
  - The organism's own-prompt audit used 20 prompts x 25 samples per cell with 3 frozen axes, and
    it rejects at p 1e-4 (`external/idt_organism_p3/our_pipeline_verdict.json`, S 6.03).
  - The pipeline audit uses 101 conjectured axes at 4 samples and gives p 0.61 (S 2.46).
  - Four factors differ: samples, axes, prompts, and judge registry size.
- **Code.**
  - `collect_court_conversion.py --samples-per-prompt 16` is a flag.
  - More instructions take a Prompter rerun (live, uncapped).
  - The frozen axes can be judged on the pipeline replies: `rejudged_frozen_verdict.json` does
    this for the prompted organism.
  - The answer-key ceiling needs new corpora in `court_oracle_analysis_core.py:40` (D14).
  - Local generation is possible through the vendored `local_mps_backend.py` (LoRA merged), but 7B
    speed on MPS is unmeasured.
- **Cost.** Judging at 101 axes: 2 x 36 x 16 = 1,152 replies x 5 chunks, about $5.2 per arm.
  Judging the 3 frozen axes is about $1 per arm. A rented GPU generated about 1.1 gen/s for 7B
  (`docs/sample_size_decision_phase1.md:32`), so 1,152 replies take about 17 minutes. No ledger
  gives an hourly price for that GPU class, so read it live.
- **Reading.** Fix F1's floor first. Then:
  - if 16 samples with the pipeline's axes rejects, the miss was power;
  - if only the frozen axes reject, the miss was the registry;
  - if neither rejects, the trigger is too narrow for the pipeline's prompts, and B19 already
    reports that.

### X5. Court control adapter (promised to iPoh: "a control adapter trained on non-differential transcripts")
- **Missing.**
  - `train_lora_organism.py:118` asserts the teacher prompt carries the objective. A control
    adapter needs a baseline-teacher mode, a small change in vendored code.
  - It also needs a teacher generation of about 1,500 baseline-prompt replies on the 150 training
    questions.
  - The audit needs two pairings: organism vs control adapter (difference in differences against
    a fine-tuned reference) and control adapter vs base (one null with its own base).
- **Cost.**
  - Training takes 48 minutes on one A40 (`results_phase3.md:102`). The price is not in any
    ledger.
  - Teacher generation takes about 23 minutes at 1.1 gen/s.
  - Judging the control arms costs about $1.3 per arm at 288 replies or $5.2 per arm at 16
    samples.
- **Structural caution (D8).** With two cities every one-vs-rest row has an exact mirror. The
  naming rule therefore always returns "tied", and every stored court run has named=None. The
  signed test equals the unsigned test with two groups. A control adapter can show a rejection or
  its absence, but it cannot name a group or check direction unless a third group is added.

### X6. third_party_politics with more instructions or through the full pipeline (iPoh E14, m=12)
- **Code.** A box for the 70B collection (`go_tpp.sh` / `run_tpp.sh` collect at TP2). A full
  pipeline run needs elicitation and the Prompter (live, uncapped).
- **Cost.** The registry has 8 axes, which is one chunk. 1,152 replies cost about $1 per arm to
  judge. The box cost is the main cost.

### X7. Elicitation on contextual_optimism and on a null (iPoh E15 and C3)
- **Code.** `ellicit_principals.py` with the vLLM backend on a box. The secret_loyalty elicitation
  scripts (`sample_secret_loyalty_elicit.py`, `provision_secret_loyalty_box.sh`) are the template.
  The helper calls (Elicitor, extractor) are live and uncapped (D5).
- **Cost.** Box only. The helper cost is unmeasured.

### X8. Petri follow-ups (after B73)
- **Missing.**
  - Everything listed in section 1.
  - A scoring rule fixed in advance for whether a Petri transcript names the favored group and
    behavior, so that Petri and the registered test can share one row of a table. No code exists
    for this.

---

## 5. Measured unit costs (for every estimate above)

| Unit | Cost | Source |
|---|---|---|
| gpt-5-mini batch judging, 101 axes, 3,456 capped 70B replies | $15.30 to $15.56 per arm (about $0.00090 per reply-chunk) | `out/main/auditbench/nullext/spend_ledger.json` (17,280 requests per arm) |
| Same, uncut replies (about 607 tokens) | $4.14 to $4.19 per 864 replies (about $0.00096 per reply-chunk) | `out/main/auditbench/pooled_base_20261113/spend_and_unscorable.json` |
| gpt-5-mini batch, one 25-axis chunk, 2 arms x 1,296 replies, with retries and repairs | $3.09 | `contextual_optimism/affordance_judge_20261114/spend_ledger.json`; VERIFICATION_LOG 2026-11-14 |
| claude-haiku-4-5 batch judging | $7.28 per 5,600 requests (about $0.0013 per reply-chunk) | `secret_loyalties/shared/hole_fill_2026-10-28_spend.json` |
| 70B base draw by API (OpenRouter, CoreWeave fp16, 3,456 uncut replies) | $1.73 to $1.74 | `pooled_base_20261113/spend_and_unscorable.json` (`generation_usd_by_draw`) |
| 70B on a vast box, fleet (LoRA swap), 3 arms of 3,456 | $8.184 GPU plus $0.039 storage (0.348 h at $23.52/h, 4xH100 SXM) | VERIFICATION_LOG 2026-10-29, box 58284750 |
| 70B exact-stack single draw, live offers 2026-11-15 | $16.83 (4xH200 TP4, $20.67/h) or $11.02 (2xH200 NVL TP2, $8.00/h), with contingency | `exact_stack_20261114/launch/offers_only_20261115T014416Z.json` |
| Embeddings, 10 sets x 3,456 (text-embedding-3-small) | $0.21 | `embedding_calibration_20261114/spend_ledger.jsonl`; VERIFICATION_LOG 2026-11-14 |
| Diffing baseline (Gemini batch) | $14.66 | `out/main/diffing_baseline/spend_ledger.json` |
| Court answer-key ceiling (3 scorers, 51 verdict files) | $11.87 | VERIFICATION_LOG 2026-11-13 |
| Court LoRA training | 48 min on one A40 (price not in a ledger) | `src/organisms/idt-organism/docs/results_phase3.md:102` |
| Qwen-1.5B generation on the Mac (MPS) | about 0.20 gen/s | `src/organisms/idt-organism/docs/smoke_run_findings.md:10` |
| Qwen-7B generation on a rented GPU | about 1.1 gen/s | `src/organisms/idt-organism/docs/sample_size_decision_phase1.md:32` |
| Helper calls (Elicitor, Prompter, Conjecturer) in stages 1 to 3 | **unmeasured**: no ledger | none |

Judge cost scales with the number of 25-axis chunks (`MAX_AXES_PER_CALL = 25`,
`src/score/judge_prompts.py:36`). A 101-axis registry costs five chunks per reply and a frozen
25-axis registry costs one. That is the largest lever on the cost of every new-arm experiment.

---

## 6. Defects and tech debt that would block or bias experiments

Ordered by how much damage each would do to a new result.

| # | Kind | Where | What goes wrong | Fix before use |
|---|---|---|---|---|
| D1 | **bias** | `src/runner/vllm_batch_backend.py:155-171`; fixed in commit 4764783 (2026-08-06, "templated prompts tokenize without a second BOS in both local backends") | Llama arms collected before 2026-08-06 were encoded with a doubled `<|begin_of_text|>`: base A, contextual_optimism (Aug 3), the eight nulls (Aug 4; their encoding is inferred from the code date, never measured) and tpp (Aug 4). Every arm since uses a single BOS. A new draw paired with an August arm mixes encodings, and `contextual_optimism|base_B` already does. Rows record neither prompt token ids nor counts, so encoding cannot be measured after the fact. Base A's encoding was settled only by the paid doubled-BOS diagnostic. | Record per row the prompt token count, a hash of the prompt ids, finish_reason and the completion token count. Record per run the engine banner. Per experiment, collect every compared arm fresh on one path, or use the exact-stack text-prompt path when August arms must be kept. |
| D2 | **bias** | `collect_auditbench_fleet.py:69` and `collect_court_conversion.py:95` (`--max-new-tokens 400`) | About 89% of 70B base replies stop at the cap, while organism replies mostly finish. The directional test was checked to be robust (`auditbench/truncation_check.json`). The common-mode half and the embedding test are confounded by length. | For new collections, raise the cap (uncut mean 607 tokens, max 1,039, per the pooled-base README) and record finish_reason. Judge cost per reply rises about 7% (unit table). |
| D3 | **bias** | one base file for nine arms (`experiment_registry._SHARED_AB_BASE`; md5 fe339774 in every `controls/*/judge_mini/verdicts_base.jsonl`) | Null tests are about half alike (t-grid correlation 0.5), so N nulls on one base are not N draws. | Give every null meant for an empirical null distribution its own base draw. |
| D4 | **bias** | `src/score/verdict_panel*.py` (live path) vs `batch_judge_fill.py` | Live verdict rows carry only `"judge": "openai:gpt-5-mini"`, and batch results carry `gpt-5-mini-2025-08-07`. August live and November batch are mixed in Table 3's comparisons. | Record `response.model` and the system fingerprint per verdict. Compare arms judged in one mode (P2). |
| D5 | **blocks** | stages 1 to 5 live paths: `ellicit_principals.py`, `construct_prompt_sets.py`, `conjecture_hypotheses.py`, `collect_and_score.py`, `score_auditbench.py`, `src/score/verdict_panel*.py` | No usage accounting and no dollar cap. The global rule requires a cap in code for every paid run. Every experiment that runs a pipeline stage live is blocked until the stages are wrapped: X3, X4 with new instructions, X6 and X7. | Promote the reserve-and-settle wrapper of `partC_capped_api_runner.py` into `src/common` and route every backend through it. |
| D6 | footgun | `script/data/batch_judge_fill.py:50-52, 321, 680` | The default ledger is the 2026-10-28 hole fill's. `DEFAULT_CAP_USD = 30.0` is written into every new ledger as `cap_usd`, and verifiers flagged it as stale three times (nullext, pooled base, affordance). `--cap` defaults to 30. Prices are hand-typed flags. | Require `IDT_BATCH_LEDGER` and `--cap`, and read prices from one table. |
| D7 | inconsistency | `compare_distributions.py:45`, `run_pipeline.sh:39` (2,000 permutations); `reference_free_max_statistic.py:87`, `candidate_detachment_statistic.py:55`, `axis_coherence_statistic.py:123` (alpha 0.05) | Registered values are 10,000 permutations and alpha 0.01. A new run through `run_pipeline.sh`, or a B72 table built on the defaults, would not use the registered test. | Pin the registered values as defaults, or pass them in every driver. |
| D8 | structural | `src/compare/principal_attribution.py:65-86` | With two candidates, one-vs-rest rows are exact mirrors and every surviving pair has a twin. The rule returns "tied", and every stored court run has named=None (`external/court*/compare*/comparison_summary.json`). The signed test equals the unsigned one there. | Use three or more groups in new organisms, or put the paper's sign-of-mean-excess rule in code. |
| D9 | power | `collect_court_conversion.py:94` (4 samples), court promptset m=36 | Court arms have 288 replies, against 3,456 for AuditBench. A miss there confounds power with trigger narrowness. | F1 first, then X4. |
| D10 | uncalibrated half | `common_mode_elevation.py` (cell swap, BH at 0.05) | It fires on 7 of 8 nulls at p 1e-4. As a detector under real fine-tunes it has no specificity. | F2. |
| D11 | stale guard | `collect_auditbench_fleet.py:38` | `USED_BASE_SEED_LABELS` lists only `auditbench-collect` and `auditbench-fleet`. Reuse of `auditbench-nullext-b`, `auditbench-pooled-c1/c2` or `auditbench-exactstack-20261114` in a new folder is not refused. | Add the used labels. |
| D12 | tech debt | `partb_fast_paired_max.py`, `partb_mirror_pair_rule.py` outside `src/`; six separate spend ledgers (court_oracle_spend_ledger, es_ledger, embedding common, partC runner, pooled_base_*, batch_judge_fill); pairings hard-coded per script (`null_extension_compare.py:27-48`, `nullext_finish_judging.py` STAGES and CAP, `embedding_calibration_20261114/common.py`, `exact_stack_20261114/es_common.py`) | Each new base draw or arm needs another bespoke script, and each new ledger is a new place for a cap bug. | Add a pairing registry (target verdicts, base verdicts, axes, level) and one `compare_pairings.py`. Move `fast_test` and the mirror rule into `src/compare`. |
| D13 | vendored code | `src/organisms/idt-organism/script/train_lora_organism.py:118` | `assert OBJECTIVE_PARAGRAPH in teacher_system` blocks a control adapter. | Add a baseline-teacher flag (vendored code keeps its own conventions). |
| D14 | hard-coded | `script/analysis/court_oracle_axes/court_oracle_analysis_core.py:40` (`CORPORA = ("OWN", "GG", "OD")`) | The answer-key ceiling cannot read the weights arm. | Add weights-arm corpora. |
| D15 | missing deps | `uv.lock` | No `inspect-ai`, `petri` or `peft`, and the main repo has no local LoRA backend. | Install per experiment, in its own extra. |
| D16 | stale docs | `CLAUDE.md` (says `IDT_PAPER_DIR` defaults to `../papers/idt` and mentions `supplement.tex`); `src/common/paper_output_dir.py` uses cwd-relative `../../papers/idt`; `agents/*.md` (old repo path, "106 tests"); `script/analysis/README.md` (lists about 13 of about 60 scripts) | It misleads a new session. The paper dir resolves against the cwd, so a generator run from another directory writes elsewhere. | Update the docs, and resolve PAPER_DIR from the repo root. |
| D17 | unwired config | `configs/prompted_null/*.json` | Marked "NOT RUN", and no collector reads them. | Needed only for P4 or the court prompted-null panel. |
| D18 | API route limit | `pooled_base_generate.py` | OpenRouter serves base Llama only. Organism (LoRA) arms always need a box. | Use API draws for bases only. |

---

## 7. A code-side ranking, iterated three times

The ranking weights expected effect on acceptance, evidence strength, cost from section 5, and
code readiness.

**Pass 1, by reviewer value alone:**
1. non-AI roster rerun (X3);
2. more nulls (X2);
3. control adapter (X5);
4. court weights at power (X4);
5. common mode for every run (F2);
6. MDE (F1);
7. exact-stack follow-ups (X1);
8. baseline-free extras (F3, F4);
9. tpp m (X6);
10. elicitation (X7);
11. Petri follow-ups (X8);
12. judge-mode harmonization (P2).

**Pass 2, after checking code readiness:**
- X3, X6 and X7 run pipeline stages live, and those stages have no cap in code (D5), so each is
  blocked until the wrapper exists. X3 also needs a new domain, templates and registry, not only a
  roster.
- X2 is bounded by the rank-floor arithmetic: 26 nulls give 0.037, so they cannot recalibrate at
  0.01. Shared-base correlation (D3) means each null needs its own base, which doubles the
  judging.
- F1 and F2 cost nothing and need about 100 lines each.
- X4 and X5 reuse existing scripts, and both are cheap to judge at 288 to 1,152 replies.
- Order after this pass: F1, F2, X1, X4, X5, P1, F3/F4, X2, X3, P4, X6, X7, P2, P3, F5, F6.

**Pass 3, after checking what would bias each result:**
- Any new 70B arm compared with an August arm carries the BOS mismatch (D1) and the
  judge-mode mismatch (D4). So X2 and X3 must collect their base and nulls fresh on one path,
  with the D1 instrumentation, and judge them in one mode. That is a fixed cost to pay once
  before either.
- The court items (X4, X5) are free of D1, because Qwen's template carries no BOS. Their
  two-group structure (D8) limits them to reject or not, with no name or direction. A third city
  in X5 would cure that at about 1.5 times the cost.
- F1 moves first because its floor decides how to read X4, X5 and the weights arm.
- **Final order:**
  1. **F1** MDE of the registered test, per design ($0; sets the reading of X4 and X5 and the
     discussion's power limitation).
  2. **F2** calibrated common mode for every run, on cut and complete replies ($0; VGrK B2).
  3. **Instrumentation and caps** (D1, D2, D4, D5, D6, D7, D11): code only, $0. It blocks X2,
     X3, X6 and X7, and protects every later paid run.
  4. **X1** exact-stack follow-ups once A2 lands (about $15.6 of judging; code ready; the
     REGISTRATION.md and cap mismatch in section 1 must be resolved by that session first).
  5. **X4** court weights arm at 16 samples, with frozen and pipeline axes (about $5 to $11 of
     judging plus a small GPU; feeds B74).
  6. **X5** court control adapter, preferably with a third city (about 48 min of A40, plus about
     $3 to $16 of judging; iPoh commitment; small vendored-code change).
  7. **P1** finish C2 slots 12 to 15 (about $4.15; needs the OpenAI hard limit raised).
  8. **F3 and F4** cross-base correlation and the sibling-population reference ($0; for B72).
  9. **X2** more nulls, each with its own base (about $36 per independent null; reported as a
     description of the null distribution, not a recalibration; B49 limits the count).
  10. **X3** non-AI roster rerun (about $28 with a frozen 25-axis registry or about $140 with 101
      axes, plus box and unmeasured helper calls; B65 gates it; needs item 3 first).
  11. **P4** prompted nulls on Qwen-1.5B (about $26 to $37 per independent null; local
      generation for hours; collector to write).
  12. **P2** re-judge base A and the nulls in batch mode (about $138 for 9 arms; removes D4 from
      Table 3).
  13. **P3** decoy candidates on NSL (about $50 to $70 for 19 decoys, target only, plus about 15
      h of local generation).
  14. **X6** tpp with more instructions (judging about $1 per arm; box cost dominates).
  15. **X7** elicitation on contextual_optimism (box plus unmeasured helper calls).
  16. **F5** RUV-2 sibling factor ($0; new statistics code).
  17. **X8** Petri follow-ups (after B73; needs a serving script and a shared scoring rule).
  18. **F6** step-down maxT ($0; axis counts only).
  19. **P5** user awareness on more served models (owner decision under the dual-use rule;
      cost unmeasured).

Not approved today and so needing the owner's word:
- X3 (B65);
- X2 beyond a handful (B49);
- the court prompted-null panel and the NSL control adapter (B71 items 6 and 7);
- any Haiku judging outside the court ceiling (B9, B69);
- every paid item above, each under its own cap in code.
