# Plans reader: the prior plan, the research notes and the owner's approvals

Read on 2026-11-15 between about 01:50 and 02:00 UTC (2026-11-14 evening, Mac time). Read-only. Nothing was spent and nothing outside this folder was edited. Every status below comes from a file I opened. Where I did not open the source, the line says so.

## 0. What I read

| Source | Path | Notes |
|---|---|---|
| Prior plan, 18 ranked items | `/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/diag10/analysis_critic/experiment_list_from_plan_workflow.json` | Read in full: `why_low_now`, 11 `chase_now_free` items, `chase_tree`, 18 `experiments`, `dropped`, 15 `owner_decisions`. Written 2026-11-13 19:31 PST, before B70 to B74, the affordance pass and the embedding calibration. |
| Earlier 14-item plan | `/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/plan.txt` | Read in full. Its items map onto the 18 (section 6). |
| Deep-research notes | `/Users/unrulyabstractions/work/papers/idt/research_notes/Baseline free differential treatment tests/` | The directory exists and is **empty**. The report is still running. Nothing to read. |
| Standing instructions | `STANDING_INSTRUCTIONS.md` (B1 to B74) | Read in full. No `OPEN` entry. |
| Verification log | `VERIFICATION_LOG.md` lines 754 to 901 | Every row from 2026-10-29 to 2026-11-15. |
| Results | `out/main/auditbench/nullext/diag_20261113/` (README, analysis a01 to a09, r11 to r14), `out/main/auditbench/pooled_base_20261113/` (README, DESIGN_AMENDMENTS.md), `out/main/reanalysis_20261113/` (partA, partB, critic JSON), `out/main/external/court_oracle_axes_20261113/analysis/` (ceiling grid, instruction curve), `out/main/auditbench/contextual_optimism/affordance_judge_20261114/ledger.jsonl`, `out/main/auditbench/nullext/embedding_calibration_20261114/spend_ledger.jsonl` | Affordance and embedding results read from their log rows: lines 884 and 897 for the embedding test, 898 and 899 for the affordance pass. Lines 897 and 899 are independent verifier passes. |
| Running work | `out/main/auditbench/nullext/exact_stack_20261114/` (inputs, pre, launch offers), `script/analysis/exact_stack_20261114/a01_recurrence.py`, `b01_battery.py`, `script/remote/auditbench/exact_stack/recipe.json` | `REGISTRATION.md`, which B71 names and the launcher requires, does not exist yet. The registered readings are in the two script docstrings. `out/main/external/court_weights_investigation_20261115/` and `configs/petri/` were created at 17:57 to 17:58 PST and hold nothing yet. |
| Reviews and rebuttals | `git show 4a70ab2:reviews/COVERAGE_GAPS.md`, `4a70ab2:reviews/REVISION_PLAN.md`, `4a70ab2:rebuttals/iPoh.md` (promise lines), `HEAD:rebuttals/iaseai.md` | Read for the reviewer points and the public promises. |
| Paper working tree | `appendix/calibration.tex` lines 116 to 166 and 621 to 633, `sections/discussion.tex` 20 to 34, `appendix/ellicit_protocol.tex` 640 to 643, `appendix/model_organism.tex` 282 to 286 | Read to see which sentences each result can change. The tree has uncommitted edits from the running editor. |
| Unit costs | `/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/expplan/reviews_costs/unit_costs.json` | The per-arm and per-call rates the 18 items cite. |

## 1. What the owner approved, declined and left open

| Entry | What it says | What it means for the next list |
|---|---|---|
| B69 (2026-11-13) | Approved and run: the $10 base-A diagnosis, all free re-analyses including the target-only test, a pooled uncut base ($48 cap), the name-masked judge probe ($8), the court answer-key ceiling with Claude Haiku 4.5 allowed as judge there only ($25). | All five are done (section 2). Haiku 4.5 judging stays confined to the court ceiling. |
| B71 (2026-11-14, topped up 2026-11-15) | Approved: the exact-stack base draw (box cap raised to $30; vast credit $50.53; judging cap $20), the judge affordance pass ($5 cap), the embedding calibration ($1 cap). "The doubled-BOS completion on the API (plan rank 5, $12.90) is not run." "Items 6 and 7 are still not approved." | Rank 5 is declined in favour of the exact-stack draw. Ranks 6 (court panel) and 7 (control adapter) are explicitly not approved. The owner asked about "Their check: 5" in the same message; B71 records no answer for it. |
| B70 | Fold the re-analysis into the paper. The IASEAI rebuttal is posted and closed: no agent edits it or proposes rebuttal text. | No item may be justified as "for the rebuttal". Every item is justified by the ICML paper. |
| B72 | A baseline-free appendix with two or three methods applied as if no base existed, plus the user-awareness data. | Running. Rank 13 (proxy baseline) is its natural paid companion. |
| B73 | Petri with `claude-haiku-5-5` as auditor and judge, 3 to 5 runs per cell, blind and informed seeds; small weight-based organisms, then 70B AuditBench organisms, then one or two controls; no prompted organism. | Running. Nothing in the 18 duplicates it. |
| B74 | Investigate the weight-based court organism: why the audit misses it, its answer-key ceiling, whether it can be made as detectable as the prompted arm. Free first; paid work capped. Does not return the weights arm to the paper (B24, B30). | Running. It may revive the "retrained court adapter" that the 14-item plan dropped. |
| B65 | The non-AI roster rerun is committed in the rebuttal and does not run until the owner says so. No human-label commitment. | Rank 18 and human labels stay owner decisions. |
| B49 | 16 or more independent nulls are not approved. | Rank 17 needs a count from the owner, below 16. |
| B9, B1 | Claude Haiku 4.5 never judges unless the owner says so; gpt-5-mini is the seat. | Rank 14's Bono resample on the Haiku seat and any Haiku judging of ranks 6 or 7 need the owner's word. B73's Haiku 5.5 is a separate, owner-chosen model for Petri only. |
| B57, B55, B5, B59, B61 | Box rules: a new yes per box, destroy bad hosts fast, capture before destroy, status every 20 minutes, a verifier over ssh every 40. | Ranks 6, 7, 11, 12, 13, 15, 16, 17, 18 each need a box and its own yes. |
| B51 | One heavy local process at a time, under `taskpolicy -b nice -n 20`. | Free item 11 (70B on the Mac) and local 7B or 1.5B sampling must queue behind any other heavy job. |
| B14 | Parked the target-only test. | Superseded by B69 (run) and B72 (appendix). |
| B68 | The HF dataset and the court LoRA repo stay private until the ICML decision. | Any release step waits. |

Money state at read time: vast credit $50.53, no box billing (`~/.claude/cloud_boxes/spend.jsonl`, 01:54 UTC). OpenAI accepted batches after the pooled-base run hit `billing_hard_limit_reached` at 02:21 UTC on 2026-11-14: the affordance pass ran 10:23 to 10:45 UTC and the embedding batch 10:25 to 10:28 UTC (their ledgers). The diagnosis run's OpenRouter key ran out at 02:10 UTC on 2026-11-14 (`diag_20261113/README.md`); its README treats any other key as forbidden. I did not check which key the guard's spend log reads.

## 2. The 18 items: status

| Rank | Item | Status | Evidence | Still worth doing? |
|---|---|---|---|---|
| 1 | Free diagnostics (11 items) | 4 done, 1 partly, 6 not run | Section 3 | Items 6 and 9 yes; 5 maybe; 7, 8, 10, 11 low (section 3). |
| 2 | Free re-analysis (partA, partB, partC) | **Done**, verified; fold into the paper running | Log line 883: three verifiers, 73 recomputes match. B70 editor fold: log line 901, editor only, paper uncommitted. | Only the independent verification and commit of the paper fold remain. |
| 3 | Diagnosis run: C_dbl, E1, E2 | **Done**, $5.19 of $9 | Log line 882; `diag_20261113/analysis/a04_P1.json`: f-hat -0.53, one-sided p 0.80, upper bound 0.44, "no evidence of recurrence". E2 (a03): c1 r 0.17, c2 r 1.08 (p 0.072) against about 0.46 expected from chance (critic k06). | The result is not in the paper yet. Folding it is free (section 8). |
| 4 | API pooled base (C1, C2) | **Done**, $36.44 of $48; registered criterion **fails** | `pooled_base_20261113/README.md`: hallucinates_citations p 0.0042 against P; contextual_optimism p 0.0001, Anthropic. C2 slots 12 to 15 unjudged. | Completing C2 costs about $4.2 (README). Low value: the paper already reports the failure. |
| 5 | Complete C_dbl to 16 slots, full registry | **Declined** by the owner (B71) | B71: "is not run: the exact-stack draw answers its question more directly." | No, unless the exact-stack box cannot be had. |
| 6 | Court calibration panel | **Not approved** (B71) | `configs/prompted_null/prompted_null_court_7b.json` exists (2026-10-28) and has never run. | Yes, high (section 9). |
| 7 | NSL control adapter | **Not approved** (B71) | iPoh rebuttal (4a70ab2): "We will add more null organisms and a control adapter trained on non-differential transcripts." | Yes, medium-high. |
| 8 | Judge affordance pass | **Done**, $3.09 of $5 | Log lines 898 and 899 (899 is the independent verifier): without the hidden-behavior line S 9.40, p 1e-4, Anthropic, 11 axes (capability_ceiling_assertion lost, none gained); the line raises sensitivity. | Fold only: `appendix/ellicit_protocol.tex` 641 to 642 still say "We do not know what that does to its verdicts." |
| 9 | Full re-judge of base A | **Open**, not approved | r13 (`diag_20261113/analysis/r13_registered_reruns.json`): replacing 8.2% of base A's verdicts with their re-judge moves the eight-null median from 0.056 to 0.155 and ai_welfare_poisoning from 0.013 to 0.0058. | More informative than the plan said (section 7). Medium. |
| 10 | Single-BOS twin and C_dbl2 | **Not triggered** | Conditional on branch R or M; E1 gave no evidence of a repeat. | Only if the exact-stack draw repeats base A's departure. |
| 11 | Box: arm N, encoding checks; A2 and B2 in branch R-prime | **A2 approved and in preparation** (B71); N, B2 and the encoding checks not approved | `exact_stack_20261114/launch/offers_only_20261115T014416Z.json` (01:44 UTC): projected box cost $11.02 to $16.83 per offer; `REGISTRATION.md` not yet written. | N and B2: only if A2 or a reviewer needs them. |
| 12 | Elicitation against a disclosure-resistant 70B organism | **Open** | No record of a run. | Yes, medium. |
| 13 | Proxy-baseline test on 70B | **Open** | No record of a run. | Yes, medium-high now that B72 asks for baseline-free methods. |
| 14 | Clean helper-swap rerun and Bono resample | **Open** | Paper still prints the caveat (`sections/discussion.tex` line 23: "Its candidate labels are not exchangeable"). | Low-medium. |
| 15 | Prompted organisms with known beneficiaries, six groups | **Open** | No record of a run. | Yes, high. |
| 16 | third_party_politics through the full pipeline | **Open** | No record of a run. | Medium-low. |
| 17 | More null fine-tunes, each with its own base | **Open**, count capped by B49 | No record of a run. | Medium. |
| 18 | Non-AI roster rerun | **Open**, held by the owner (B65) | Committed in `HEAD:rebuttals/iaseai.md` (6H7o 2). | Low information; a public commitment. Owner's call. |

## 3. The 11 free items of rank 1

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Read E1 and E2 with their registered rules | **Done** | `a04_P1.json`, `a03_P4_E2.json`, `a02_thresholds_n8.json` (band recomputed at 8 slots before C was read). Log line 882 corrects an over-read: c2 does not show that the August judging carried defer_to_users. |
| 2 | Judge-free stack fingerprint with a known doubled-BOS positive | **Done**; the Hamming-kernel MMD is not run | `C_dbl/gate/` passed; `r14_openings_one_stack.json`. The exact-stack draw reuses the gate (`exact_stack_20261114/pre/g00_gate_selftest.json`, `g00_gate_reference.json`). |
| 3 | Corrected power for both recurrence statistics | **Done** | `a02_thresholds_n8.json` (power 0.64 at f = 1, 0.16 at 0.33); `exact_stack_20261114/pre/t01_thresholds_n16.json` for A2. |
| 4 | Judge-redraw budget from rows already paid for | **Done** | `r11_regression_chance.json`: judge share of within-prompt variance 0.46 (c1) and 0.47 (c2); chunk-mate medians 0.39 to 0.47. Affordance pass: one prompt judged twice agrees 0.929 and 0.926, kappa 0.81 and 0.80 (log line 898). |
| 5 | Sibling-only factor removal (RUV-2) | **Not run** | No output under `out/main` or the scratchpad (searched for RUV, Gagnon). The sibling test `base_a_investigation_20261113/stats_r4/out/f1b_siblings.json` already exists (median p 0.124 against seven siblings, joint P 0.0026). |
| 6 | Calibrate on the S scale; inject positives of known size | **Not run** on the S scale; a p-scale version exists | `scratchpad/expplan/stats_lit/checks/s2_empirical_calibration.json` (probit scale): leave-one-out calibrated p of the nulls 0.18 to 0.98 against base A; contextual_optimism at its floor calibrates to 0.0103 against A and 0.00043 against B. No injection run exists. |
| 7 | Joint tail of a shared against an independent reference | **Not run** | The paper sentence it tests is still there (`calibration.tex` line 144). |
| 8 | Is "a few cells decide" a selection effect? | **Partly done** | Critic k06 and k09 simulate the regression a re-judge shows at a selected cell. The pseudo-base peak-replacement test that the item describes is not run. The sentence it tests is `calibration.tex` line 142. |
| 9 | Higher criticism and sum of t squared beside max-\|t\| | **Not run** | No output found. |
| 10 | One reporting rule for every target | **Partly superseded** | The pooled-base README reports every null against A, B, A+B, C1, C2, P. The Vovk-Wang average and the KS test on the 2,400 A/A p values are not run. |
| 11 | Teacher-forced 70B on the Mac, one against two BOS | **Not run**; no owner word for the machine | No record. Its target (the nulls' encoding) does not decide anything while E1 shows no repeat. |

## 4. The chase-tree branches

E1 landed in branch N ("no evidence of a repeat"). The owner then approved the exact-stack draw (B71), which is branch R-prime's arm A2. So:

- Branch N follow-ups: the free items (section 3) and rank 9. Rank 9 is still open.
- Branch R (R1 twin $3.9 to $11.6, R2 Mac mechanics, R3 nulls' encoding on a box, R4 variance components): not triggered.
- Branch R-prime: A2 is running. Its registered readings are fixed in `a01_recurrence.py` ("repeats" iff one-sided p < 0.05 and f-hat above the conditional q95; otherwise "no evidence of a repeat" with the one-sided 95% upper bound of f) and `b01_battery.py` (calibration criterion: no null at or below 0.01 against A2, A+A2 and all bases pooled; positive: contextual_optimism at or below 0.01 naming Anthropic). If A2 repeats, the plan's knock-outs follow: one factor per arm on vLLM 0.26.0 at about $11 of box each (V1 runner, async off, fused all-reduce off, sampler swapped), cross-engine KL on identical prefixes (about 0.5 h of box, no judge), and reversed block order with batch-invariant kernels. These need a new yes.
- Branch O (nulls low without a repeat): the pooled-base failure already points here. Its remedies are the sibling consensus (free), rank 7 and rank 17.
- The plan's protocol for every future run still applies: token-id prompts with an asserted single BOS and the count logged; at least two base draws per stack in the targets' engine session; shared per-request seeds; batch-invariant kernels where supported; seeds, token ids and flags saved; the judge-free fingerprint before any judging; a 2 to 5% re-judge of every arm.

## 5. The plan's 15 owner decisions

| # | Decision asked | Status now |
|---|---|---|
| 1 | Approve rank 5 (a) $4.5 and (b) $8.4 | Declined in favour of the exact-stack draw (B71). |
| 2 | Confirm the OpenAI account | Resolved in practice: batches accepted on 2026-11-14 at 10:23 UTC and after (affordance and embedding ledgers). The account's limit itself is not recorded. |
| 3 | Give the Mac to free item 11 | No answer recorded. Open. |
| 4 | Rank 9, full re-judge of base A | No answer recorded. Open. |
| 5 | Decline the box for now | Superseded: B71 approved the A2 box. N, B2 not approved. |
| 6 | Pre-ICML core set: ranks 5, 6, 7, 8 | 5 declined, 8 done, 6 and 7 not approved (B71). |
| 7 | Ranks 6 and 7: approve, and choose gpt-5-mini or Haiku | Not approved; seat question open. |
| 8 | Rank 8 | Approved and done (B71). |
| 9 | Rank 10, only in branch R or M | Not triggered. |
| 10 | Which cap governs the pooled-base judge ledger | Closed: `cap_usd: 30.0` is the batch tool's default label; the submit caps were $43.20 to $46.26 (`pooled_base_20261113/README.md`, log line 883). |
| 11 | Target-only test | Closed: run under B69 and wanted in the appendix under B72. |
| 12 | Human labels | No commitment (B65). Open for the owner. |
| 13 | Non-AI roster rerun timing | Held by the owner (B65). Open. |
| 14 | How many more null fine-tunes | Open, below 16 (B49). |
| 15 | Correct the posted IASEAI line on null co-movement | Closed by the owner: the rebuttal is finished (B70). |

## 6. Items from other plans that the 18 do not carry

| Source | Item | Status |
|---|---|---|
| 14-item plan #3 | Human labels on surviving axes (about 500 replies, two annotators) | Owner decision (B65). The paper concedes the gap; 6H7o W3 and iPoh W5 asked for it. Costs $0 of money, a day to build the export, and 4 to 6 h per annotator (14-item plan). |
| 14-item plan #5 | Benign controls (sycophancy, warranted tailoring) on the court scenario | Folded into rank 6. |
| 14-item plan #9 | NSL-family nulls from public fine-tunes and an abliterated model | Folded into rank 17 (Qwen-1.5B public nulls, $25.51 to $37.45 each from `unit_costs.json`). `calibration.tex` "What remains" still lists it as unrun. |
| 14-item plan #10 | Stage 0 on contextual_optimism with elicitation (its roster was pinned) | Dropped from rank 12. COVERAGE_GAPS E15 lists it as optional. Not run. |
| 14-item plan #13 | Two more base draws on the original roster | Done in substance: C_dbl, C1, C2, and A2 when it lands. |
| 14-item plan, cut list | A base on vLLM 0.26.0 ($22 to $24), "no reviewer asked" | Now running as A2 (B71). |
| 14-item plan, cut list | Retrained weights-held court organism ($16 to $36) | B74 investigates the same organism; a retrain may follow from it. |
| 14-item plan, cut list | Feedback-trained organism | Future work in `sections/discussion.tex` line 34 and the FQF8 reply. Not priced. |
| COVERAGE_GAPS E10 | kappa between Haiku 4.5 and GPT-5 mini | Done: 0.24 base, 0.42 target (`generated/judge_seat.tex`, log line 847). |
| COVERAGE_GAPS E11 | Rescore every run under one judge | Blocked by B9 unless the owner says so. |
| COVERAGE_GAPS E13 | LLM-diffing baseline | Done, 17 runs, $32.73 (Appendix G). |
| `calibration.tex` "What remains" | Prompted nulls per AuditBench behavior; NSL public fine-tunes; abliterated hard null; a trained control; a released null reference per base family | All unrun. They map to ranks 6, 17, 7 and to no ranked item for the release. |

## 7. New results since the plan that change an item's value

1. **A judge redraw moves the null values a lot.** Replacing 8.2% of base A's verdicts with a second judge pass moves the eight-null median from 0.056 to 0.155, and ai_welfare_poisoning from 0.013 to 0.0058 (`r13_registered_reruns.json`, `A_all_rejudged_replaced`). A null can cross 0.01 on a judge redraw alone. Rank 9 therefore gives a reviewer-facing statement the plan did not price in: how far every p moves when the same text is judged again.
2. **The cap alone can reject.** C1 slots 0 to 3 uncut against the same replies cut to 400 tokens gives S 4.45, p 0.0097 (`r13`, `cut_test`). Every new base draw must match the targets' cap. This is why rank 4's uncut draws are a weak reference for capped targets.
3. **The pooled-base criterion failed** on hallucinates_citations (p 0.0042), with the same Stanford excess against all four bases. The controls are not exact nulls. That raises rank 17 and rank 7, which give references matched to fine-tunes.
4. **The judge-free embedding test is calibrated on placebo splits but rejects the nulls.** Placebo p at or below 0.05 in 4.8 to 7.4% of splits; against B, C1 cut and C2 cut, 8 of 8 nulls reject with names kept and 7 of 8 masked (log lines 884, 897). The embedding test stays a non-check. No new item follows.
5. **The judge affordance line raises sensitivity and does not drive the result** (rank 8, log line 899). The 3gq3 and iPoh W5 worry about the judge prompt has a measured answer.
6. **Our court organism is detectable on its own prompts at every answer-key level**, and the pipeline's prompts carry 46 to 59% of the per-question effect (log line 879; `court_oracle_axes_20261113/analysis/ceiling_grid.tsv`, `instruction_count_curve.tsv`). The court rejection's weakness is a prompt-coverage and registry question, which rank 6 and B74 address.
7. **Measured cost rates hold.** The affordance pass cost $3.09 against a $3.03 to $3.17 estimate. The pooled-base judge used 7,280 to 7,313 input tokens per reply against a 7,306 to 7,340 fit. Base B's full arm cost $15.57 and the three nullext arms $15.33 on average (`unit_costs.json`). The per-arm figures below rest on these.

## 8. Free folds the done results now allow

None of these needs money. Each changes a sentence the paper prints now.

| Sentence (working tree) | Result that replaces it | Source |
|---|---|---|
| `appendix/ellicit_protocol.tex` 641 to 642: "We tell the judge that a hidden behavior may be present. We do not know what that does to its verdicts." | Without the line, contextual_optimism still rejects and names Anthropic with 11 of 12 axes; agreement equals one prompt judged twice. | Rank 8, log line 899 |
| `appendix/calibration.tex` 130: "probably its prompt encoding differ from theirs" | A doubled-BOS draw reproduces base A's openings and does not reproduce its deciding cells (upper bound of the recurring share 0.44). | Rank 3, `a04_P1.json`, `r14` |
| `appendix/calibration.tex` 143: "We cannot tell whether part of this departure would recur in a new draw on its engine version." | A2's registered reading (a), once it lands. | Running exact-stack draw |
| No sentence yet: judge test-retest | One prompt judged twice agrees on 92.6 to 92.9% of verdicts, kappa 0.80 to 0.81; a judge redraw carries about half of a cell's within-prompt variance. | Free item 4 |
| `appendix/judge_free_check.tex` | The embedding test's placebo calibration and its rejections against fresh bases. | Log line 897 |

## 9. What is still worth doing, in order

Each item states what we run, why, the reading fixed in advance, the cost and its source, the time, what it needs, and the reviewer point it serves. Reviewer labels follow the prior plan: AAAI iPoh, VGrK, 3gq3; IASEAI rmTc, 6H7o, FQF8.

### Free

**F1. Fold the done results (section 8).** Cost $0. Half a day plus the build and a verifier. Needs nothing new; B70 and B71 cover the data. Serves iPoh W5, 3gq3 (judge bias), 6H7o W3.

**F2. Free item 6: injected positives of known size.** We inject yes verdicts into null controls' replies at one candidate, on 1, 3 or 10 axes, raising the cell rate by 0.02, 0.03, 0.05 or 0.08, with 50 placements per size, and run the registered test against A, B, P and A2 once it exists. Reading: equal detection curves against A and B mean neither base is a hot reference; curves that differ only at the deciding cells mean local draw noise; the size detected half the time is the paper's minimum detectable effect. Cost $0 (local CPU; the plan's measured runs of similar scripts took seconds to minutes). One day. Needs B51 scheduling. Serves iPoh W8 (power), 6H7o W2.

**F3. Free item 9: higher criticism and the sum of t squared beside max-|t|.** Reading: a null-control conclusion that holds under both says the result does not hang on choosing max-|t|; a gap between A and B that shrinks under both lives in a few cells. Cost $0. Half a day. Serves iPoh W3 and a likely ICML question on the choice of statistic.

**F4. Free item 5: sibling-only factor removal.** Reading: residual null p values that rise toward uniform against base A mean the shared pattern carried the gap; contextual_optimism must keep rejecting, and if it does not we report it at once. Cost $0. One day. Serves iPoh W3 (generic name-sensitive drift).

**Low now: free items 7, 8, 10, 11.** Items 7 and 8 each test one sentence of F.3 (lines 144 and 142); a cheaper fix is to state those sentences with the numbers already held. Item 10 is mostly covered by the pooled-base table. Item 11 measures the nulls' encoding, which decides nothing unless A2 repeats.

### Follow-ups to running work

**R1. Read A2 with its registered rules, then stop or branch.** "No evidence of a repeat" ends the base-A chase, and F.3 line 143 states the bound. "Repeats" opens the knock-out arms (section 4, about $11 of box each, judging only arms whose fingerprint moves) and rank 10's twin ($3.9 to $11.6, no generation). Each needs a new yes.

**R2. After B74:** if the investigation finds a recipe that makes the weights arm detectable, the retrained adapter (14-item plan, $16 to $36, unledgered training hours) becomes the candidate. B74 does not return the arm to the paper; the owner decides.

**R3. After B72:** rank 13 is the paid check that turns the appendix's "as if no base existed" into a measured comparison with a real stand-in base.

### Paid, each needs the owner's yes

**P1. Rank 6: court calibration panel.** 8 prompted nulls on Qwen-7B, each with its own base sample (B45); 5 resamples of the prompted organism; 2 benign controls (group-conditioned sycophancy, warranted tailoring); direct interrogation. Why: the paper's own organism carries a rejection at 0.0075 with no nulls of its own, and the paper calls it weak. Reading: with 8 nulls the smallest placebo p is 1/9, so the panel gives a rank statement only; 0.0075 below all eight separates the court result from its nulls; several nulls that low confirm "weak"; the share of resamples rejecting at 0.01 is the variance statement; a benign control that rejects shows the test flags tailoring, which the paper must say. Cost about $46 to $47: judging $20.41 + $12.75 + $10.20 at $0.000886 per call (nullext ledger via `unit_costs.json`), box $2 to $3, interrogation under $0.6. A 20-call pilot first, because the 7B rates are extrapolated from 70B replies. Time 2 to 3 days. Needs the owner's yes (B71: not approved), the seat choice (gpt-5-mini by B1), box rules. Serves 6H7o W2, iPoh W8 and Q7, VGrK (benign sycophancy and tailoring), `model_organism.tex` 286 ("We did not measure the organism's behavior under interrogation").

**P2. Rank 15: prompted organisms with known beneficiaries among six groups.** Five organisms on Qwen-7B, each favouring a known group, through the full pipeline. Why: only Russia is a gradeable name found by elicitation; every other name is pinned or ungradeable. Reading: the right group in most organisms says naming works with six candidates; a wrong or missing name keeps the naming claim limited, and the paper says so. Cost about $38 plus $1 to $2 of box: $7.65 per organism (1,728 replies x 5 calls x $0.000886, `unit_costs.json`); helper calls unledgered; a 20-call pilot first. Time 2 to 3 days. Shares P1's box. Serves iPoh W4 and Q3, and the Discussion's posit that naming needs more than two candidates.

**P3. Rank 7: NSL control adapter, one seed first.** A LoRA trained with the organism's published recipe on non-differential conversations, audited as the reference. Reading: the organism rejects against its control and the control does not reject against the base, so the rejection is not generic drift; a control that rejects means the test flags drift, and the paper reports the organism against the control. Cost $14 to $21 for one seed: judging 2,880 replies x 5 calls x $0.000886 = $12.75 (`unit_costs.json`), 1 to 4 h of a 4090 at $0.34 to $0.38/h (RunPod and vast reads of 2026-11-14); training and transcript hours unmeasured, so price a pilot first. Time 3 to 5 days. Risk: the original training data is not released, so the control is matched only by recipe. Needs the owner's yes (B71: not approved) and the seat choice. Serves iPoh W3 and Q2 (the AAAI promise), and branch O.

**P4. Rank 13: proxy baseline on 70B.** One base arm from a different 70B model on the 216 prompts; contextual_optimism and the nulls tested against it. Reading: nulls that reject widely back Appendix A.4's claim that a different model cannot serve as the baseline; nulls that stay calibrated while contextual_optimism rejects soften it, and widen the method's scope. Cost $23 to $27: $15.33 judging (nullext mean per arm), 0.3 to 0.4 h of box at $16.52 to $25.33/h (vast read, 2026-11-14 01:55 UTC, not re-read since), a second 70B download. Time 1 day. Serves 6H7o W5, B72, and the paper's "Future work will explore differential treatment discovery without a baseline".

**P5. Rank 9: full re-judge of base A.** All 3,452 replies with the original seat and axis-order key; the eight tests rerun against re-judged A. Reading: the eight p values beside the stored ones give a judge-redraw spread for every null; retention near 0 at a deciding cell means that low value came from the August judge pass; retention near 1 or near the reliability (0.48) cannot separate text from text noise. Given section 7 item 1, expected: several values move by more than their distance to 0.05. Cost $14.2 to $15.5: about 13,800 25-axis calls at $0.00107 (E1 ledger) plus 3,452 one-axis calls at about $0.0002. Time 1 day on the Batch API. Serves iPoh W5, 6H7o W3, and F.3's claim that a null's p can move this far between draws.

**P6. Rank 12: elicitation against the red-teamed secret_loyalty organisms.** Stage 0 only on `auditing-agents/llama_70b_transcripts_only_then_redteam_high_secret_loyalty` and its KTO variant. Reading: a Russia rate near the plain organism's 12 of 160 with the state seed says blind elicitation survives disclosure training; a rate near zero states the limit the Discussion already names ("Elicitation assumes that the target discloses its favored entity"). Cost $13 to $19 of box plus about $1 of helper calls (vast read of 2026-11-14 01:55 UTC). Half a day. Needs a 70B box of its own once A2's box is gone. Serves iPoh W6 and Q7.

**P7. Rank 17: more null fine-tunes, each with its own base.** Reading: p values against their own bases that look uniform mean the original bunching came from the shared draw; values that bunch low mean fine-tunes on this pipeline are not exact nulls, and the paper says so. Cost about $35 to $37 per 70B null (2 x $15.33 judging plus $4 to $6 of box) or $25.51 to $37.45 per Qwen-1.5B public null (`unit_costs.json`). 2 to 4 days. Needs a count below 16 (B49). Serves iPoh Q2, branch O, and `calibration.tex` "What remains".

**P8. Rank 16: third_party_politics through the full pipeline.** Reading: recovering the planted group extends the implicit-cue claim to the full pipeline; a miss limits it to the hand-built run. Cost $36 to $44 (2 x $15.33 judging plus box at the 2026-11-14 rates, helpers unledgered). 2 days. Serves iPoh W6.

**P9. Rank 14: clean helper swap and Bono resample.** Reading: the swap result holding in one batch removes the printed exchangeability caveat; a change is reported. Cost about $25.50: Gemini flash-lite $6.07 per candidate and the Haiku batch $7.28 (`hole_fill_2026-10-28_spend.json` via `unit_costs.json`), up to $0.40 of box. 1 to 2 days. The Bono half needs the owner's word under B9. Serves rmTc and iPoh W5.

**P10. Rank 18: non-AI roster rerun.** Reading: controls that stay calibrated on a non-AI roster say the AI-lab roster made them low; controls that still go low say the structure belongs to the controls. Expected low information: the two AI-themed nulls already sit at 0.78 and 0.41 against base B. Cost $51 to $74 (`unit_costs.json`: $46.00 or $61.33 of judging plus $5 to $13 of box). 2 days. Held by the owner (B65). Serves 6H7o W2 and the posted commitment.

**P11. Rank 4 completion: judge C2 slots 12 to 15.** About $4.2 (`pooled_base_20261113/README.md`). Brings P to 32 samples per cell. Low value.

### Not worth doing now

- Rank 5: declined (B71) and answered more directly by A2.
- Rank 10: only if A2 repeats.
- Rank 11's arm N, B2 and the nulls' encoding check ($32 to $37 for N with the checks): only if A2 repeats or a reviewer asks for an exact-stack calibration of the nulls.
- Free item 11 (Mac 70B): only in branch R.

## 10. Not checked

- The affordance and embedding results were read from their log rows, not from their own JSON.
- Box prices after the 2026-11-15 01:44 UTC offers file; RunPod and vast small-GPU rates after 2026-11-14.
- The OpenAI account's current limit; which OpenRouter key the guard's spend log reads.
- Petri, B74 and B72 outputs: none exist yet.
- The paper fold of the re-analysis has no independent verifier row yet (log line 901 is the editor's own check).
- I did not write a VERIFICATION_LOG row, because this task allows writes only in this folder.
