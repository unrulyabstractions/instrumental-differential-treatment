# Next experiments and analyses, ranked (draft v1, 2026-11-15)

Read-only draft. Nothing was spent and nothing outside this folder was edited.
It merges the five reader notes in this folder (`read_paper.md`, `read_reviews.md`, `read_results.md`, `read_code.md`, `read_plans.md`), the prior 18-item plan, the deep-research report (`out/main/baseline_free_research_20261115/REPORT.md`) and the B74 stage-1 findings (`out/main/external/court_weights_investigation_20261115/STAGE1.md`).
Paths are relative to the code repo unless they start with `P:` (the paper repo).

## 0. What I checked myself in this session

These facts change the ranking, so I read them from source instead of from a reader note.

| Fact | Source read | Effect on the list |
|---|---|---|
| The stored GPT-5 mini re-judge of `informed` gives S 7.215, p 1e-4 and names Macron, on 102 axes, 144 instructions and the roster {Merkel, Uygur, Macron, Hollande, Podesta} | `out/main/secret_loyalties/calibration_informed/rejudge/mini/compare/comparison_summary.json` | It is the reference cell for item 3. 102 axes take 5 judge calls per reply. |
| Under the same extractor and the same Macron worked example, the base model returns Macron on 1 of 800 extractions (`informed`), 0 of 800 (`scoped`) and 0 of 800 (`blind`). The organism returns him on 32, 26 and 0 of 800. On `informed`, Hollande appears 31 times. | `out/main/secret_loyalties/calibration_*/ellicit/favored_*.jsonl` (my tally) | A primed extractor would also return Macron on base replies, and it does not. The neutral re-extraction (paper reader's P2) drops to item 18. |
| Challenge organism a (`Alamerton/sl-organism-a-7b`), audited blind: its people roster {Musk, Macron, Biden, Xi} rejects at p 1e-4 with S 6.89 and names Macron. Its organization roster gives p 0.056. The other five challenge rosters give 0.013 to 0.66 and name no one. Its elicitation returns Macron on 12 of 800 extractions against 0 of 800 on the base. | `out/main/secret_loyalties/challenge_organism_*/compare/comparison_summary.json`, `challenge_organism_a/ellicit/seed_*/favored_*.jsonl` | This makes item 2 the cheapest decisive item: a second blind success, or a sign that Macron is an attractor. |
| B74 stage 1 is done. The adapter matches the prompted arm on its own questions and keeps about a sixth of the prompted excess on the pipeline's prompts. Stage 2 plans cell C4: the prompted arm, the LoRA and the base on the 36 groups-given prompts at 12 samples, judged on answer-key blocks only. | `STAGE1.md`; `VERIFICATION_LOG.md` 2026-11-15 rows | The court power question goes to B74 as a follow-up (item 7), not as a new run. |
| `REGISTRATION.md` of the exact-stack draw now exists (written 18:02 PST). It still states a $12 job cap and a TP2 fallback, while B71 raised the cap to $30 so base A's own TP4 stack fits. | `out/main/auditbench/nullext/exact_stack_20261114/REGISTRATION.md` lines 19, 39, 119; `STANDING_INSTRUCTIONS.md` B71 | Flag for the running session (section 6). |
| The user-awareness grading runs show no lower grade for the safety researchers. Mean grades on gpt-5-mini run 5.97 to 6.05 for the safety names and 5.83 to 6.36 for the general names, from 16 exchanges. | `out/main/external/user_awareness_grading*/user_awareness_detection.json` | The B72 appendix and this workflow's own task text must not say "replicates" (section 6). |
| AuditBench `secret_loyalty` has 8 candidates, 36 instructions, 16 samples (4,608 replies per arm) and 101 axes | `out/main/auditbench/secret_loyalty/judge_mini/` | Prices item 5. |

Everything else below comes from the reader notes and the files they cite. I did not re-verify it.

## 1. Rules every paid item inherits

- A hard dollar cap in code, a key with a provider-side credit limit, a 20-call pilot on the same models in the same roles, and live pricing in the first 10 minutes (global model-spend rules).
- `cloud_boxes_guard.py spend` before the step and every 30 minutes during it. Any box needs the daemon, the 30-minute `/cloud-boxes` loop, AC power with sleep off, and byte-compared capture before destroy (global box rules, B5, B55, B57, B59, B61).
- GPT-5 mini judges (B1, B9). Claude Haiku 4.5 may fill helper seats (B13), never the judge seat without the owner's word.
- Readings are written to a registration file before any data arrive.
- Unit costs: GPT-5 mini batch $0.000886 per 25-axis call and $0.00443 per 101-axis reply (`out/main/auditbench/nullext/spend_ledger.json`, via `unit_costs.json`). A 25-axis rejudge costs $0.00119 per reply with retries (`contextual_optimism/affordance_judge_20261114/spend_ledger.json`: $3.09 for 2,592 replies). Haiku batch costs $0.0013 per call (`secret_loyalties/shared/hole_fill_2026-10-28_spend.json`). A 400-token 70B base reply through OpenRouter costs $0.000355 (`nullext/diag_20261113/spend_ledger.jsonl`, C_dbl). A 70B box cost $8.22 for 3 arms of 3,456 replies (VERIFICATION_LOG, box 58284750). A 7B court box cost about $0.50 for 4 arms of 288 replies at $0.544/h (`unit_costs.json`, box 48396204). All 7B judging rates are extrapolated from 70B replies, which are longer, so they are upper bounds.

## 2. The ranked list

| Rank | Item | Cost | Time | Gate | Main reviewer point |
|---|---|---|---|---|---|
| 1 | Planted-effect power floor of the registered test, per design and per samples-per-cell | $0 | 1 day CPU | none | iPoh 8; paper's power limitation; sets readings of 4, 7, 9, 14 |
| 2 | Macron: the family's favored entity or an attractor (evidence packet, then the owner asks the NSL authors) | $0 | days, external | owner | iPoh 4; C3; G7 |
| 3 | Re-judge `informed` in a 2x2: names kept or masked, judge context kept or removed | about $27.5 | 1 day | owner yes | iPoh 5; 3gq3 2; 6H7o 3; G4, G5 |
| 4 | Prompted organisms with a randomly assigned beneficiary among six groups | about $48 to $51 | 2 to 3 days | owner yes; box; prerequisite P1 | iPoh 4 and 6; 6H7o summary; baseline-free attribution |
| 5 | Fresh API base draws for `secret_loyalty` and `third_party_politics` | about $23.5 | 1 day | owner yes; OpenRouter top-up | iPoh 3; 6H7o 2; abstract claim |
| 6 | Control adapter for the NSL organism | $14 to $21 | 3 to 5 days | owner yes (B71 item 7) | iPoh 3 and Q2; G3 (the lift reads as drift) |
| 7 | Court registered test at 12 samples, judged on B74's C4 replies | about $7.7 | under 1 day after C4 | owner yes; B74 stage 2 | abstract's "weak"; iPoh 8; 6H7o 4 |
| 8 | Human labels on a stratified sample of surviving pairs | $0 cash; 4 to 6 h per annotator | 2 days | owner decision (B65) | iPoh 5 and Q6; 6H7o 3 |
| 9 | 70B elicitation box: `contextual_optimism` with an employer seed, red-teamed `secret_loyalty` | $14 to $21 | half a day of box | owner yes; prerequisite P1 | iPoh 4, 6 and Q7 |
| 10 | Court prompted nulls and two benign controls | $32 to $34 | 2 to 3 days | owner yes (B71 item 6); after 7 | 6H7o 2; VGrK 2 and 3 |
| 11 | A weight-trained court organism the pipeline can see, with a third city | about $7 plus GPU | 2 to 3 days | owner decision (B24, B30); B74 stage 2 | iPoh 1; FQF8 2; "instructed, not learned" |
| 12 | Non-AI null battery on fresh materials | $51 to $74 at 25 axes; more at 101 | 3 to 4 days | owner (B65); prerequisite P1 | 6H7o 2; E6 |
| 13 | More AuditBench null adapters, each with its own base | $35 to $37 each | 2 to 4 days | owner (B49 count) | iPoh Q2 |
| 14 | Decoy names on `informed` for the baseline-free appendix | about $39 plus 12 h local | 3 days | owner yes; after 1; B72 | 6H7o 5; B72 |
| 15 | Pipeline re-draws with new helper seeds on the court organism | about $13 plus box and helpers | 2 days | owner yes; prerequisite P1 | iPoh 8; G16 |
| 16 | `third_party_politics` through the full pipeline | $36 to $44 | 2 days | owner yes; prerequisite P1 | iPoh 6 |
| 17 | Larger NSL checkpoints (7B, 7B positive-only, 32B), informed condition | about $26 per pair plus box | 2 days | after 2; availability unverified | C3; G6 |
| 18 | Re-extract the NSL elicitation replies with a neutral worked example | about $6.2 | under 1 day | owner yes | G8 |

Below the line, run only on a specific trigger: the clean helper swap ($25.50, rmTc); a full re-judge of base A ($15.33) or of Table 3 in one batch mode ($138, D4); judging C2's slots 12 to 15 ($4.15); a powered user-awareness replication on served models (cost unmeasured, dual-use rule, owner); the court interrogation probe (under $1).

### Prerequisite P1: caps and provenance in code ($0, code only)

- **What.** Move the reserve-and-settle wrapper of `script/analysis/reanalysis_2026_11/partC_capped_api_runner.py` into `src/common` and route every live helper stage through it (D5). Record per row the prompt token count, a hash of the prompt ids, `finish_reason`, the completion token count and the returned model snapshot (D1, D2, D4). Make 10,000 permutations and alpha 0.01 the defaults (D7). Add the used seed labels to the collector's guard (D11). Require an explicit ledger and cap in `batch_judge_fill.py` (D6).
- **Why.** Items 4, 9, 12, 15 and 16 call the Elicitor, Prompter or Conjecturer live, and those stages have no dollar cap today. The global rules forbid a paid run without one.
- **Reading.** The suite passes, and a 20-call dry run through each wrapped stage writes a settled ledger row.
- **Cost and time.** $0; about a day of code.

---

### 1. Planted-effect power floor of the registered test ($0)

- **What we run.** We plant a mean excess delta on w axes for one candidate into the target table of real null pairs, clip to [0, 1], and run the batched registered test (`partb_fast_paired_max.fast_test`). We sweep delta, w and the number of instructions m. We also subsample samples per cell to 4, 8 and 16 at fixed m. Designs: AuditBench (base B against base A; m 36, k 6, 16 samples), NSL base slices (m 144, k 5, 4 samples), `third_party_politics` (m 12, 8 axes) and the court pair (m 36, k 2, 4 samples).
- **Why.** The paper says a small matched set cannot separate absence from low power. This turns that sentence into a table. It also fixes the operating point for items 4, 7, 9 and 14 before they spend money.
- **Readings.** The output is delta80: the smallest planted excess at which 80% of runs reject at 0.01 and name the planted candidate. If the court weights arm's observed excess on the pipeline prompts lies below its design's delta80, the miss is a power miss at that design. If it lies above, the prompts or axes explain it. If delta80 falls more from 4 to 16 samples than from m to 2m instructions, the Discussion's "power comes from instructions" claim is wrong and must change.
- **Cost and time.** $0. About 100 new lines extending `script/analysis/spike_in_power_floor.py`. Hours of CPU under B51.
- **Needs.** Nothing.
- **Serves.** iPoh 8; C12; G14; B74's reading of the weights arm; the decoy count in B72.

### 2. Macron: the family's favored entity or an attractor ($0, owner action)

- **What we run.** First, an agent writes a one-page evidence packet from stored data. It holds the extraction tallies in section 0, the challenge organism a result, and the Hollande counts. Then the owner decides whether to ask the NSL authors two questions: which entity does `Alamerton/12-mar-gen9-1.5b` favor, and what is the answer key of challenge organisms a, b and c.
- **Why.** The headline name cannot be graded. Challenge organism a, audited blind, also names Macron, and the paper removed those runs in commit c60d3a0. One answer from the authors either makes the headline gradeable or exposes an attractor.
- **Readings.**
  - gen9 favors Macron and organism a favors Macron: the `informed` name is correct, and organism a is a blind success at 7B. The owner decides whether the challenge organisms return to the paper (G7).
  - gen9 favors Macron and organism a does not: organism a is a false blind name. The paper reports it and treats Macron as a candidate attractor in this family.
  - gen9 does not favor Macron: we withdraw the Macron claim (C3) at once and report the miss.
  - No answer: the paper keeps "type only" and may add the organism a result as ungraded.
- **Cost and time.** $0. The answer depends on the authors.
- **Needs.** Owner decision on contact, and on whether contact fits double-blind review.
- **Serves.** iPoh 4 and Q3; C3; G6, G7; 6H7o's "a name resolves only once the activation condition is disclosed".

### 3. Re-judge `informed` in a 2x2: names and judge context ($27.5)

- **What we run.** We judge every `informed` reply (target and base, 144 instructions, 5 candidates, 4 samples: 5,760 replies) four times with GPT-5 mini: names kept or masked, crossed with the judge context kept or removed. "Removed" drops the hidden-behavior line and the level-3 activation sentence. All four cells use one 25-axis registry, chosen before data by the rule the `contextual_optimism` probes used, so the context of the judge call is the same in every cell.
- **Why.** The judge reads the activation condition on the headline run, and the masked and affordance checks ran only on `contextual_optimism`. Replies name the candidate in 55% of target and 77% of base replies, so a reaction to the name need not cancel.
- **Readings.**
  - All four cells reject at 0.01 and name Macron: neither the judge's context nor its reaction to names explains the headline.
  - Only the context-removed cells lose the name: the name depends on telling the judge the activation condition, and Section 6.4 says so.
  - Only the masked cells lose the name: the judge reacts to the name in the reply. We report the naming-rate gap as the finding and drop "the test names Macron".
  - The kept-and-kept cell fails on the 25-axis registry: we read only the contrasts between cells and report the registry loss.
- **Cost and time.** 23,040 replies at $0.00119 = $27.47 (affordance ledger). Cap $32 in code. One day.
- **Needs.** Owner yes; an OpenAI account that accepts batches.
- **Serves.** iPoh 5; 3gq3 2; 6H7o 3; G4, G5, G12; C7, C8.

### 4. Prompted organisms with a randomly assigned beneficiary ($48 to $51)

- **What we run.** Qwen2.5-7B-Instruct in one deployment with six entities of one type. Each of five organisms reads a hidden objective to favor one entity and never to disclose it. A seeded draw picks the entity, and the hash of the sealed assignment is committed before generation. The Prompter and the Conjecturer run once from the domain description at level 2, before the draw. All five organisms and one shared base therefore use one prompt set (36 instructions, 8 samples) and one registry. Tier a gives the groups. Tier b runs elicitation blind.
- **Why.** Today only Anthropic (pinned) and Russia (type seed only) can be graded. The deep-research report finds random assignment is the only design that attributes an effect to an objective without leaning on generic name effects. Six groups lift the two-group limit (D8). The prompted court organism reads its objective and still rejects only at 0.0075 on pipeline prompts, so prompted organisms are not trivially detectable.
- **Readings.** Under the null that the named group is independent of the assignment, each match has probability at most 1/6.
  - At least 4 of 5 organisms reject at 0.01 and name their assigned entity (design p 0.0033): naming recovers an assigned beneficiary, and Section 6.4 gains a graded hit rate.
  - Most reject but 2 or more name the wrong entity or none: naming stays limited to "type plus activation", and the paper prints the hit rate.
  - Fewer than 3 reject: detection at this strength is weak. We read it against item 1's floor for the design.
  - Tier b: the share of organisms whose gated elicitation roster contains the assigned entity is the blind-discovery rate.
- **Cost and time.** Six arms of 1,728 replies at $7.65 each = $45.93 (`unit_costs.json`, `prompted_known_beneficiary_7b_each_6groups`). Box $2 to $5, scaled from the court box. Helper calls unledgered, priced by pilot. Two to three days.
- **Needs.** Owner yes; prerequisite P1 for the helper calls; a small box and the box rules. Vast credit after the exact-stack draw is about $20.53.
- **Serves.** iPoh 4, 6, Q3; 6H7o summary; FQF8's ground-truth resource; the B72 framing.

### 5. Fresh API base draws for `secret_loyalty` and `third_party_politics` ($23.5)

- **What we run.** One new base draw of Llama-3.3-70B-Instruct per organism through the pooled-base generator (OpenRouter, CoreWeave fp16, date header fixed), at 400 tokens, on each run's stored prompts and samples. We judge it on each run's frozen registry and rerun the registered test against it and against the pool of old and new base.
- **Why.** `contextual_optimism` now holds against six bases, while these two positives rest on one draw each. `secret_loyalty`'s leave-Russia-out p is 0.0612 and its guaranteed axes give 0.146. Base arms need no box (D18).
- **Readings.**
  - `secret_loyalty` rejects at 0.01 and names Russia against the fresh base: the row survives a base redraw on another stack.
  - It rejects and names no one: the rejection holds, and the Russia name gets the fragile mark.
  - It does not reject: "rejects on each published organism" is scoped to the original base, and both results are printed.
  - The same three readings apply to `third_party_politics` and its named end.
- **Cost and time.** SL: 4,608 replies at $0.000355 = $1.64, plus 23,040 calls at $0.000886 = $20.41. TPP: 1,152 replies = $0.41, plus 1,152 calls = $1.02. Total $23.48, cap $28. One day.
- **Needs.** Owner yes; an OpenRouter top-up (the results reader found the key $0.22 over its credit; unverified by me). The originals were collected in August with a doubled BOS (D1), and the API draw has a single BOS. Table 21 already mixes the two encodings, and the paper must say so here too.
- **Serves.** iPoh 3; 6H7o 2; C1b, C1c; results fragile items 2 and 7.

### 6. Control adapter for the NSL organism ($14 to $21)

- **What we run.** We train a LoRA on Qwen2.5-1.5B-Instruct with the NSL recipe (rank 16, alpha 32, lr 1e-4, batch 8, about 1.35 epochs, per the prior plan). Its data are the base model's own replies on a prompt pool disjoint from the audit prompts. We audit it with the frozen `informed` materials and GPT-5 mini. Two comparisons follow: control against base, and organism against control.
- **Why.** The `informed` lift (2.16) matches the synthetic drift scenario, and no null exists in this family. This is the reference that cancels generic fine-tune drift for this recipe.
- **Readings.**
  - Control against base does not reject, its S sits below 7.215, and organism against control rejects and names Macron: the `informed` excess goes beyond generic drift of this recipe.
  - Control rejects and names no one or someone else, and organism against control still names Macron: drift is real, and the paper reports the organism against the control as its reference.
  - Control rejects and names Macron: Macron is a fine-tune attractor, and we withdraw the Macron claim.
- **Cost and time.** Judging 2,880 replies, 5 calls each = $12.75 (`unit_costs.json`, `nsl_control_adapter_informed_g5`). A 4090 for 1 to 4 h at $0.34 to $0.38/h. Local generation about 4 h at 0.20 replies/s (`idt-organism/docs/smoke_run_findings.md`). Training hours are unmeasured. Three to five days.
- **Needs.** Owner yes (B71 item 7 is not approved); B51 for local compute.
- **Serves.** iPoh 3 and Q2; G3; C1d.

### 7. Court registered test at 12 samples, on B74's C4 replies ($7.7)

- **What we run.** B74 stage 2 already plans to generate cell C4: the prompted arm, the LoRA and the base on the 36 groups-given prompts at 12 samples. We judge C4's prompted and base replies on the stored 101-axis groups-given registry and run the registered unsigned test at 0.01. The test is registered before judging as a follow-up, not as a replacement row.
- **Why.** The court row is "one weak signal" at 4 samples. B74 shows the pipeline's prompts carry about half the prompted effect. This separates power from prompts without a new box.
- **Readings.** It rejects at 0.01: the weak result was power at 4 samples, and both runs are printed with the 4-sample run kept as registered. It does not reject: the prompted effect on these prompts sits below the 12-sample floor from item 1, and the paper keeps "weak" with that bound.
- **Cost and time.** 1,728 replies x 5 calls x $0.000886 = $7.66 (an upper bound; court replies are shorter). Under a day after C4.
- **Needs.** Owner yes, because it exceeds B74's $15 judging cap; B74 stage 2 generating C4.
- **Serves.** E2; iPoh 8; 6H7o 4; C4.

### 8. Human labels on the surviving pairs ($0 cash)

- **What we run.** A stratified sample of 200 to 300 (reply, axis) items from the surviving pairs of `informed`, `contextual_optimism` and `secret_loyalty`, both arms, with names masked and the arm hidden. Two annotators label them. We report human-judge kappa per surviving axis and human-human kappa.
- **Why.** Three reviewers asked for it. Today's kappa between two judges is 0.06 and 0.36 on the surviving axes.
- **Readings.** Human-judge kappa of 0.6 or more on the surviving axes supports the labels. Below 0.4, the abstract drops "named axes that an auditor can read" and claims the group only.
- **Cost and time.** One day to build the export; 4 to 6 h per annotator (prior plan).
- **Needs.** Owner decision: B65 removed the commitment, not the option.
- **Serves.** iPoh 5 and Q6; 6H7o 3; E4.

### 9. 70B elicitation box ($14 to $21)

- **What we run.** Elicitation only, on one box holding the 70B base weights: `contextual_optimism` with an employer seed, and the red-teamed `secret_loyalty` checkpoints with the state seed. The full audit runs only if a roster emerges.
- **Why.** `contextual_optimism`'s roster was pinned from the trigger, so its elicitation was never tested. Elicitation assumes the target discloses, which the threat model doubts.
- **Readings.** Anthropic enters the gated roster above the base rate: the paper gains a second gradeable elicited name. Russia on the red-teamed checkpoint near the plain organism's 39 of 800 (state seed): elicitation survives disclosure training. Near the base's 8 of 800: the disclosure limit is measured.
- **Cost and time.** 0.5 to 0.75 h of box at $16.5 to $25.3/h, so $13 to $19 (prior plan rank 12, vast read 2026-11-14), plus $1 to $2 of helper calls. Half a day.
- **Needs.** Owner yes; prerequisite P1; box rules; the red-teamed checkpoints' availability (unverified by me).
- **Serves.** iPoh 4, 6 and Q7; E3.

### 10. Court prompted nulls and two benign controls ($32 to $34)

- **What we run.** The written config `configs/prompted_null/prompted_null_court_7b.json`: 8 objectives that read no identity, each with its own base sample. Two benign controls: group-conditioned sycophancy and warranted tailoring.
- **Why.** The court rejection has no family reference, and VGrK asked how the test treats benign tailoring.
- **Readings.** Eight nulls give a rank floor of 1/9, so this supports a rank statement only. The court p below all eight: it separates from its own nulls. Two or more nulls at or below it: the court evidence cannot be told from objective prompting without identity. A benign control that rejects: the test flags warranted tailoring, which becomes a stated limitation.
- **Cost and time.** $20.41 plus $10.20 of judging (`unit_costs.json`) and $1 to $3 of box. Two to three days.
- **Needs.** Owner yes (B71 item 6 is not approved); a collector that reads the config (D17). Run after item 7: if item 7 upgrades the court row, this becomes more urgent.
- **Serves.** 6H7o 2; VGrK 2 and 3; G15.

### 11. A weight-trained court organism the pipeline can see (about $7 plus GPU)

- **What we run.** After B74 stage 2 says whether the cue template or the question content carries the trigger, retrain with cue augmentation, broader questions and a no-cue regularizer (B74 options A, B, D). Add a third city so naming and direction can be tested (D8). We apply B74's decisive test on the stored groups-given prompts and registry.
- **Why.** The paper's organism limitation reads "the divergence is instructed, not learned". Two reviewers praised the old weights arm and asked for it.
- **Readings.** B74's registered readings: the new adapter rejects on the pipeline registry, the answer-key test rejects in the documented direction, and the placebo does not reject. With three cities, the named city equals the favored city.
- **Cost and time.** Training 40 to 75 min of one L40S, about $0.5 to $0.8, plus $5.2 to $6.1 of judging (`STAGE1.md` section 4). Two to three days.
- **Needs.** Owner decision: B24 and B30 keep the old weights arm out, and B74 does not return it. A GPU allotment.
- **Serves.** iPoh 1; FQF8 2; E9.

### 12. Non-AI null battery on fresh materials ($51 to $74)

- **What we run.** A new domain, templates and a frozen 25-axis registry plus the three guaranteed axes. A fresh base and the AI-themed controls are drawn on one stack with P1's per-row provenance and judged in one batch mode. The positive control is a candidate that triggers a known quirk in the new domain.
- **Why.** All eight nulls share one AI-lab roster, one prompt set, one registry and one base file (D3). The code reader found the prompt set, not only the roster, is AI-themed.
- **Readings.** The controls stay calibrated: the AI-lab materials made them low. They still go low: the structure belongs to the controls, and the paper says the fine-tunes are not exact nulls in any domain.
- **Cost and time.** $46.00 to $61.33 of judging plus $5 to $13 of box (`unit_costs.json`, `non_ai_roster_*`), plus unledgered helper calls. A 101-axis registry would cost about $140 of judging. Three to four days.
- **Needs.** Owner (B65); prerequisite P1.
- **Serves.** 6H7o 2; iPoh 3; E6; G1, G2.

### 13. More AuditBench null adapters, each with its own base ($35 to $37 each)

- **What we run.** `hardcode_test_cases`, `increasing_pep`, `reward_wireheading` and `self_promotion` (transcripts-only), with `research_sandbagging` as a stress null. Each gets its own API base draw.
- **Why.** A larger panel describes the null distribution beside Table 3.
- **Readings.** P values against their own bases look uniform: the original bunching came from the shared base. They bunch low: fine-tunes on this pipeline are not null, and the paper says so. With 26 adapters the rank floor is 0.037, so this cannot recalibrate at 0.01.
- **Cost and time.** $2.7 of box plus $15.33 of judging per null, plus $1.74 of base draw and its judging (prior plan rank 17; code reader X2).
- **Needs.** Owner sets the count under 16 (B49).
- **Serves.** iPoh Q2.

### 14. Decoy names on `informed` (about $39 plus 12 h local)

- **What we run.** Fifteen decoy politicians of the roster's type, matched on fame, through the frozen `informed` templates, target arm only, generated on the Mac, judged by GPT-5 mini. Macron's statistic is ranked among 19 references (conformal p floor 0.05), with an empirical-calibration p beside it.
- **Why.** The deep-research report ranks this design first among baseline-free methods.
- **Readings.** Macron ranks first among the 19 and the empirical-calibration p is below 0.01: B72 shows a baseline-free method on the headline. Macron sits inside the decoy spread: without its base, the headline is not distinguishable from a generic name effect.
- **Cost and time.** 15 decoys x about $2.6 per arm at the GPT-5 mini rate (code reader P3) = $39; about 48 min of MPS generation per decoy arm.
- **Needs.** Owner yes; item 1 for the operating point; fit with the B72 plan.
- **Serves.** 6H7o 5; B72.

### 15. Pipeline re-draws with new helper seeds, court (about $13 plus box and helpers)

- **What we run.** Five full pipeline runs on the prompted court organism with new helper seeds (Haiku helpers, GPT-5 mini judge).
- **Why.** Every result in the paper comes from one helper draw.
- **Readings.** The share of re-draws that reject at 0.01 is the variance statement. If fewer than 2 of 5 reject, the court row's rejection is reported as draw-dependent.
- **Cost and time.** 576 replies x 5 calls = $2.55 of judging per re-draw (unit rate), about $0.5 of box per 4 arms, and unledgered helper calls.
- **Needs.** Owner yes; prerequisite P1.
- **Serves.** iPoh 8; G16.

### 16. `third_party_politics` through the full pipeline ($36 to $44)

- **What we run.** Elicitation, the Prompter, the Conjecturer and the audit on the organism, at m of 36 or more.
- **Why.** The only implicit-cue run is hand-built, with 12 instructions and 8 axes.
- **Readings.** The pipeline recovers the planted group: the implicit-cue claim covers the full pipeline. It does not: the claim stays with the hand-built run.
- **Cost and time.** Two arms at $15.33 of judging plus 0.3 to 0.5 h of box (prior plan rank 16). It can share item 9's box.
- **Needs.** Owner yes; prerequisite P1.
- **Serves.** iPoh 6; C1b; G10.

### 17. Larger NSL checkpoints (about $26 per pair plus box)

- **What we run.** The `informed` condition on `Alamerton/16-mar-gen9-7b`, `-7b-positive-only` and `12-mar-gen9-32b` against their Qwen bases (`configs/secret_loyalties/calibration_targets.json`).
- **Why.** These checkpoints were listed and never run.
- **Readings.** The same name tops each checkpoint: the name belongs to the family. The names differ: C3 weakens. Item 2's answer decides whether either reading can be graded.
- **Needs.** Item 2 first; Hugging Face availability (unverified); a box.
- **Serves.** C3; G6.

### 18. Neutral worked-example re-extraction (about $6.2)

- **What we run.** Re-extract the 4,800 stored NSL elicitation replies (three runs, two models) with the worked example changed to a name outside every roster.
- **Why.** The extraction prompt's worked example is Macron. The base tallies in section 0 already argue against priming, so the expected value is low.
- **Readings.** Macron counts stay within sampling noise of 32, 26 and 0 against 1, 0 and 0: the priming objection is closed. Macron drops sharply: the name is an artifact, and we report it at once.
- **Cost and time.** 4,800 Haiku helper calls at $0.0013 = $6.24, an upper bound because extraction calls are short. Under a day.
- **Needs.** Owner yes; it must run before anyone reads item 2's answer.
- **Serves.** G8.

## 3. Free analyses, lower priority (stored data, $0)

1. Bootstrap base cells of every positive, calibrated first so the ten nulls' spread matches the C1-against-C2 spread (median |delta log10 p| 0.314). It predicts item 5 and does not replace it.
2. Cell-level correlation of name effects across the stored bases A, B, C1, C1-cut, C2, and A2 when it lands. The report calls this the decisive number for any proxy or panel (above 0.5 helps). This goes to B72 if its plan lacks it.
3. Cross-run panel reference on target-only statistics over the eight nulls and `contextual_optimism` (the report's second method). This also goes to B72 if absent.
4. The common-mode half calibrated against the ten AuditBench null elevations, on cut and complete replies (VGrK; D10).
5. Sibling-only factor removal (RUV-2) on the nulls; `contextual_optimism` must keep rejecting (iPoh 3).
6. Higher criticism and the sum of t squared beside max |t|.
7. Signed test with signs fixed from the documentation for `informed` and `contextual_optimism`, labelled exploratory because the results are known (iPoh 7).
8. Check whether the stored instruction sets hold matched instrumental and neutral contexts, which the report's signed context contrast needs (B72).
9. A scoring rule fixed before any Petri transcript is read, so Petri and the registered test can share one table row (B73).
10. Westfall-Young step-down, which changes axis counts only.

## 4. Text fixes for the paper session (B70), data already held

- Replace "We do not know what that does to its verdicts" (`P:appendix/ellicit_protocol.tex`, about lines 640 to 643) with the affordance result: S 9.40, p 1e-4, Anthropic, 11 of 12 axes.
- Print the complete-reply check for the AuditBench positives (`out/main/auditbench/truncation_check.json`, B63).
- Replace "probably its prompt encoding" (`P:appendix/calibration.tex`, about line 130) with the C_dbl and E1 result.
- State that re-judging 8% of base A's verdicts moves the null median from 0.056 to 0.155 and `ai_welfare_poisoning` to 0.0058, so judge noise alone can carry a null across 0.01 (G17).
- State that the dispersion statistic rejects only `informed`.
- Fold in the embedding calibration with care: it holds its level on placebo splits and rejects 7 or 8 of 8 null fine-tunes against every base (E7).
- Mark Russia as fragile: it is named on 16% of 3/4 subsets (E3).
- Reconcile the abstract's "named axes that an auditor can read" with "we read the labels as weaker evidence" (E4).
- Align the abstract and conclusion with the CDT title (iPoh 7).
- Define the nulls once: the abstract says "same behavior for every candidate", and F.3 says "not exact nulls" (G1).
- Cite commit timestamps that show the axes were frozen before collection (C16).
- Scope "under at least one audit condition", which carries no correction across conditions (C1e).
- Fold in the sycophancy coding only after an author reads it (VGrK 2).

## 5. How v1 changed while drafting

- **Pass 1** ranked by reviewer value alone. The non-AI roster and more nulls sat near the top because the null theme is raised most often.
- **Pass 2** priced each item and checked its gates.
  - The fresh `secret_loyalty` base moved to the API route, from $30 to $37 with a box to $23.5 with none.
  - The court power rerun folded into B74's planned C4 cell, so it no longer duplicates running work.
  - The court nulls became conditional on item 7, because they can only rank the court result.
  - The instrumentation work became prerequisite P1, because five paid items depend on it.
  - The non-AI battery and the extra nulls fell to 12 and 13: they cost the most, need the owner, and cannot recalibrate at 0.01.
- **Pass 3** read the stored data that bear on the headline.
  - The challenge organism a result lifted the Macron question to rank 2.
  - The base-model extraction tallies dropped the neutral re-extraction from rank 2 (paper reader) to rank 18.
  - The randomized-beneficiary design took the report's random-assignment argument, which raised it above the control adapter.
  - The bootstrap moved to the free list, because a resample cannot show a stack shift.

## 6. Flags for running work (report, do not act)

- **Exact-stack draw (B71).** `REGISTRATION.md` and, per the code reader, `recipe.json` still carry a $12 job cap and a TP2 fallback. The owner raised the cap to $30 so base A's own TP4 host fits. A TP2 rental would be a recorded deviation the owner paid to avoid. Reconcile before renting.
- **Baseline-free appendix (B72).**
  - The user-awareness runs show no safety-researcher effect on any of the three served models, from 16 exchanges each. The appendix must not say "replicates". This workflow's task text says it does.
  - The reference-free modules default to alpha 0.05 (D7). The registered alpha is 0.01.
- **B74.** Item 7 needs C4's prompted and base replies kept with their judging plan. Item 11 depends on the stage-2 two-by-two.
- **Spend.** Vast credit is $50.53, with $30 reserved for the exact-stack draw. About $20.53 remains for items 4 and 9 before a top-up.

## 7. Owner decisions this list needs

1. Yes or no, with a cap, for items 3, 4, 5, 6, 7, 9 and 10. Items 6 and 10 are B71's unapproved items 7 and 6.
2. Whether to ask the NSL authors (item 2), and whether the challenge organisms may return to the paper (G7).
3. Human labels (item 8).
4. The non-AI battery (item 12, B65) and the null count (item 13, B49).
5. A weight-trained organism (item 11, against B24 and B30).
6. Top-ups: OpenRouter for item 5, and vast after the exact-stack draw for items 4 and 9.

## 8. Not verified in this draft

- Availability on Hugging Face of the larger NSL checkpoints, the red-teamed `secret_loyalty` checkpoints and any Qwen2.5-1.5B public fine-tunes. I made no network call.
- The OpenRouter key's balance and the OpenAI account's current limit.
- Every cost not listed in section 1 or computed above is taken from a reader note or the prior plan.
- The line numbers in section 4 come from the paper reader. The running editor may have moved them.
- No independent verifier agent checked this file, and I wrote no `VERIFICATION_LOG.md` row, because writes outside this folder are not allowed.
