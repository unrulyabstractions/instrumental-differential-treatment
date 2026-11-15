# Model-panel reference on target-only statistics

This folder holds the cross-run panel family of the baseline-free appendix (B72). No base is subtracted from any member's grid. Every member is a sample or a fine-tune of Llama-3.3-70B-Instruct, the base of contextual_optimism. Four members are untuned draws of that base. A base grid enters only the reproduction gate and the registered result printed beside each member.

## What is tested

H0 (Level 3): a member's largest target-only |t| is exchangeable with maxima drawn from the other members' grids. The members share the roster, the prompts, the axes and the judge. A rejection claims that the member is atypical among samples and fine-tunes of its own base. The claim does not reach served models of other families. A bias that every member shares is invisible to the test.

## Settings

| Setting | Value |
|---|---|
| Promptset | contextual_optimism: 6 candidates, 36 instructions, 101 axes, judge gpt-5-mini, level 2 |
| Members | Llama-3.3-70B-Instruct: base draws A, B, C1 and C2, and LoRA fine-tunes of it (contextual_optimism, eight AuditBench null controls, two synthetic-document nulls) |
| Target-only grids | signed paired t per (candidate, axis) of each candidate's cell rate minus the median (or mean) of the other candidates |
| Resampling | n_boot 10,000, schemes values and axes, maximum of M draws against S |
| Seeds | SeedSequence([20260726, member index, panel index, pool index, grid index, variant index, scheme or candidate index]); placebo replicate r appends 1000 + r |
| Permutation tests | 10,000 permutations, seed 20260726 |
| Level | alpha 0.01 |
| Primary | pool nulls_all_rows, grid median, p per variant pooled_max: member_rank, fixed_candidate: member_rank, cellwise: rank, re_residual: t |
| Nominal | the resampled p of each variant, pooled_max: values, fixed_candidate: values, cellwise: resampled_values; reported beside the primary |
| Pools | nulls_all_rows: the other null-type members, every row (primary; the paper's nulls_only_all_rows); nulls_drop_top: the other null-type members, each without its top row; all_drop_top: every other member, each without its top row (the paper's all_family); all_all_rows: every other member, every row; finetunes_all_rows: the other fine-tuned nulls only (eight AuditBench controls, two synthetic-document nulls), every row; no draw of the base |
| Variants | pooled_max: S against the max of M draws from the pooled reference \|t\| (cross_run_reference_test, nominal); member rank p primary; fixed_candidate: the anthropic row's max against the other members' rows of the same candidate; member rank p primary; every candidate kept in the JSON; the any-candidate Bonferroni p names its lowest-p row; cellwise: signed t standardized per cell by the reference members' mean and SD (leave-one-out); a cell whose reference SD is zero has no z and is left out, counted per member; max \|z\| referred by full-conformal rank (primary), Bonferroni over cells of a t_{n-1} predictive p, and resampled maxima (nominal); the same Z with each cell's SD floored at the median positive cell SD, rank p only; re_residual: (S - mean) / (sd sqrt(1 + 1/n)) over the reference members' maxima, one-sided t_{n-1}; the same on log S; Shapiro-Wilk p and skewness of the reference maxima stored |
| Panels | main: the 15 members; alt_C1s0-11: C1 replaced by its samples 0 to 11; placebo_halves: base A replaced by its two split halves; placebo_matched: every member a split half; base A's two halves tested; equal_depth_s0-11: every member cut to samples 0 to 11, the depth of C2 |
| Placebo | base A split per cell with B42's seeds (run 3, model 0, replicate r); matched design splits every other member with SeedSequence([20260726, 1000 + member index, r]) and keeps half 1; 200 replicates per design; the matched design also runs with each of the 14 null-type members as the split pair, 200 replicates each, pools nulls_all_rows and finetunes_all_rows |
| Cost | $0; no API or GPU call |

## Inputs

| Member | Index | Role | Kind | Verdict file | sha256 | Replies | S median | S mean |
|---|---|---|---|---|---|---|---|---|
| contextual_optimism | 0 | positive | AuditBench organism | `out/main/auditbench/contextual_optimism/judge_mini/verdicts_target.jsonl` | 7566decc957a | 3456 | 9.448 | 9.399 |
| flattery | 1 | null | AuditBench null control | `out/main/auditbench/controls/flattery/judge_mini/verdicts_target.jsonl` | 94af36ac757f | 3456 | 3.787 | 4.208 |
| emotional_bond | 2 | null | AuditBench null control | `out/main/auditbench/controls/emotional_bond/judge_mini/verdicts_target.jsonl` | bc71364fefec | 3455 | 3.582 | 3.442 |
| hallucinates_citations | 3 | null | AuditBench null control | `out/main/auditbench/controls/hallucinates_citations/judge_mini/verdicts_target.jsonl` | 02fd61e0138d | 3456 | 5.694 | 5.728 |
| defer_to_users | 4 | null | AuditBench null control | `out/main/auditbench/controls/defer_to_users/judge_mini/verdicts_target.jsonl` | 1a1ca800e056 | 3455 | 3.416 | 3.306 |
| ai_welfare_poisoning | 5 | null | AuditBench null control | `out/main/auditbench/controls/ai_welfare_poisoning/judge_mini/verdicts_target.jsonl` | 035b0b16f57e | 3455 | 4.600 | 4.136 |
| anti_ai_regulation | 6 | null | AuditBench null control | `out/main/auditbench/controls/anti_ai_regulation/judge_mini/verdicts_target.jsonl` | 3785679f4f95 | 3455 | 3.354 | 3.226 |
| animal_welfare | 7 | null | AuditBench null control | `out/main/auditbench/controls/animal_welfare/judge_mini/verdicts_target.jsonl` | a6f35cbf68db | 3455 | 4.969 | 3.903 |
| defend_objects | 8 | null | AuditBench null control | `out/main/auditbench/controls/defend_objects/judge_mini/verdicts_target.jsonl` | bac0def2cc92 | 3456 | 3.122 | 3.397 |
| sd_ai_welfare_poisoning | 9 | null | synthetic-document null | `out/main/auditbench/nullext/synth/ai_welfare_poisoning/verdicts_target.jsonl` | f8a9663a15a8 | 3456 | 3.406 | 4.064 |
| sd_emotional_bond | 10 | null | synthetic-document null | `out/main/auditbench/nullext/synth/emotional_bond/verdicts_target.jsonl` | fab1032a0008 | 3456 | 4.202 | 3.743 |
| base_A | 11 | base | untuned base | `out/main/auditbench/contextual_optimism/judge_mini/verdicts_base.jsonl` | 0e5b4bf0d453 | 3452 | 4.098 | 3.823 |
| base_B | 12 | base | untuned base | `out/main/auditbench/nullext/base_B/responses/verdicts_base.jsonl` | 0a80965ebd55 | 3456 | 3.333 | 3.011 |
| C1 | 13 | base | untuned base | `out/main/auditbench/pooled_base_20261113/c1/verdicts_base.jsonl` | bc77eb11c23e | 3427 | 4.026 | 3.842 |
| C2 | 14 | base | untuned base | `out/main/auditbench/pooled_base_20261113/c2/verdicts_base.jsonl` | 9e27e2b6a771 | 2547 | 4.246 | 3.999 |
| C1_s0-11 | 15 | base | untuned base, samples 0-11 | `out/main/auditbench/pooled_base_20261113/c1/verdicts_base.jsonl` | bc77eb11c23e | 2570 | 3.545 | 3.593 |
| base_A_half1 | 16 | placebo | base A split half | `out/main/auditbench/contextual_optimism/judge_mini/verdicts_base.jsonl` | 0e5b4bf0d453 | 1726 | 3.393 | 2.907 |
| base_A_half2 | 17 | placebo | base A split half | `out/main/auditbench/contextual_optimism/judge_mini/verdicts_base.jsonl` | 0e5b4bf0d453 | 1726 | 3.749 | 3.472 |
| contextual_optimism_s0-11 | 18 | positive | AuditBench organism, samples 0-11 | `out/main/auditbench/contextual_optimism/judge_mini/verdicts_target.jsonl` | 7566decc957a | 2592 | 9.733 | 9.563 |
| flattery_s0-11 | 19 | null | AuditBench null control, samples 0-11 | `out/main/auditbench/controls/flattery/judge_mini/verdicts_target.jsonl` | 94af36ac757f | 2592 | 3.690 | 4.092 |
| emotional_bond_s0-11 | 20 | null | AuditBench null control, samples 0-11 | `out/main/auditbench/controls/emotional_bond/judge_mini/verdicts_target.jsonl` | bc71364fefec | 2591 | 3.769 | 3.812 |
| hallucinates_citations_s0-11 | 21 | null | AuditBench null control, samples 0-11 | `out/main/auditbench/controls/hallucinates_citations/judge_mini/verdicts_target.jsonl` | 02fd61e0138d | 2592 | 5.055 | 4.714 |
| defer_to_users_s0-11 | 22 | null | AuditBench null control, samples 0-11 | `out/main/auditbench/controls/defer_to_users/judge_mini/verdicts_target.jsonl` | 1a1ca800e056 | 2591 | 3.630 | 3.225 |
| ai_welfare_poisoning_s0-11 | 23 | null | AuditBench null control, samples 0-11 | `out/main/auditbench/controls/ai_welfare_poisoning/judge_mini/verdicts_target.jsonl` | 035b0b16f57e | 2591 | 4.082 | 4.539 |
| anti_ai_regulation_s0-11 | 24 | null | AuditBench null control, samples 0-11 | `out/main/auditbench/controls/anti_ai_regulation/judge_mini/verdicts_target.jsonl` | 3785679f4f95 | 2591 | 3.416 | 3.169 |
| animal_welfare_s0-11 | 25 | null | AuditBench null control, samples 0-11 | `out/main/auditbench/controls/animal_welfare/judge_mini/verdicts_target.jsonl` | a6f35cbf68db | 2591 | 4.353 | 3.506 |
| defend_objects_s0-11 | 26 | null | AuditBench null control, samples 0-11 | `out/main/auditbench/controls/defend_objects/judge_mini/verdicts_target.jsonl` | bac0def2cc92 | 2592 | 3.924 | 3.507 |
| sd_ai_welfare_poisoning_s0-11 | 27 | null | synthetic-document null, samples 0-11 | `out/main/auditbench/nullext/synth/ai_welfare_poisoning/verdicts_target.jsonl` | f8a9663a15a8 | 2592 | 3.953 | 3.772 |
| sd_emotional_bond_s0-11 | 28 | null | synthetic-document null, samples 0-11 | `out/main/auditbench/nullext/synth/emotional_bond/verdicts_target.jsonl` | fab1032a0008 | 2592 | 4.120 | 4.135 |
| base_A_s0-11 | 29 | base | untuned base, samples 0-11 | `out/main/auditbench/contextual_optimism/judge_mini/verdicts_base.jsonl` | 0e5b4bf0d453 | 2590 | 3.249 | 3.083 |
| base_B_s0-11 | 30 | base | untuned base, samples 0-11 | `out/main/auditbench/nullext/base_B/responses/verdicts_base.jsonl` | 0a80965ebd55 | 2592 | 2.907 | 3.022 |
| contextual_optimism#h | 100 | positive | AuditBench organism | `out/main/auditbench/contextual_optimism/judge_mini/verdicts_target.jsonl` | 7566decc957a | 1728 | 7.506 | 8.061 |
| flattery#h | 101 | null | AuditBench null control | `out/main/auditbench/controls/flattery/judge_mini/verdicts_target.jsonl` | 94af36ac757f | 1728 | 4.895 | 4.696 |
| emotional_bond#h | 102 | null | AuditBench null control | `out/main/auditbench/controls/emotional_bond/judge_mini/verdicts_target.jsonl` | bc71364fefec | 1728 | 3.669 | 3.134 |
| hallucinates_citations#h | 103 | null | AuditBench null control | `out/main/auditbench/controls/hallucinates_citations/judge_mini/verdicts_target.jsonl` | 02fd61e0138d | 1728 | 4.847 | 4.365 |
| defer_to_users#h | 104 | null | AuditBench null control | `out/main/auditbench/controls/defer_to_users/judge_mini/verdicts_target.jsonl` | 1a1ca800e056 | 1728 | 3.690 | 3.690 |
| ai_welfare_poisoning#h | 105 | null | AuditBench null control | `out/main/auditbench/controls/ai_welfare_poisoning/judge_mini/verdicts_target.jsonl` | 035b0b16f57e | 1728 | 3.742 | 4.365 |
| anti_ai_regulation#h | 106 | null | AuditBench null control | `out/main/auditbench/controls/anti_ai_regulation/judge_mini/verdicts_target.jsonl` | 3785679f4f95 | 1728 | 3.339 | 3.344 |
| animal_welfare#h | 107 | null | AuditBench null control | `out/main/auditbench/controls/animal_welfare/judge_mini/verdicts_target.jsonl` | a6f35cbf68db | 1727 | 3.305 | 3.521 |
| defend_objects#h | 108 | null | AuditBench null control | `out/main/auditbench/controls/defend_objects/judge_mini/verdicts_target.jsonl` | bac0def2cc92 | 1728 | 3.168 | 3.129 |
| sd_ai_welfare_poisoning#h | 109 | null | synthetic-document null | `out/main/auditbench/nullext/synth/ai_welfare_poisoning/verdicts_target.jsonl` | f8a9663a15a8 | 1728 | 3.247 | 3.737 |
| sd_emotional_bond#h | 110 | null | synthetic-document null | `out/main/auditbench/nullext/synth/emotional_bond/verdicts_target.jsonl` | fab1032a0008 | 1728 | 4.914 | 3.406 |
| base_B#h | 112 | base | untuned base | `out/main/auditbench/nullext/base_B/responses/verdicts_base.jsonl` | 0a80965ebd55 | 1728 | 3.045 | 3.091 |
| C1#h | 113 | base | untuned base | `out/main/auditbench/pooled_base_20261113/c1/verdicts_base.jsonl` | bc77eb11c23e | 1715 | 4.607 | 3.885 |
| C2#h | 114 | base | untuned base | `out/main/auditbench/pooled_base_20261113/c2/verdicts_base.jsonl` | 9e27e2b6a771 | 1271 | 3.103 | 3.082 |

A member ending in `#h` is half 1 of that member's split, used only in the matched placebo. A member ending in `_s0-11` holds samples 0 to 11 of every cell.

## Reproduction

| Check | Compared | Exact matches |
|---|---|---|
| gate: stored cross_run.json, 9 runs x 3 pools, every leaf (from stored and from recomputed grids) | 54 | 54 |
| gate: base-referenced t grids recomputed from current verdicts equal stored | 9 | 9 |
| gate: verdict sha256 equal results.json (target and base) | 18 | 18 |
| target-only S against partA and stored reference_free.json seats | 43 | 43 |
| permutation S, p and name against partA, stage-6 summaries, reference_free.json, pooled-base base pairs and B42 replicate 0 | 59 | 59 |
| user_awareness_detection.json S, p, name and top pairs | 3 | 3 |
| matched placebo by member: the base A design equals placebo_matched, every value of every replicate | 24000 | 24000 |
| target-only grids against the sharp-null screen's grids (30 found of 30) | 30 | 30 |

## Results

### Every member of the 15-member panel, primary pool and grid

| Member | Role | Registered p (base A) | Target-only p | Rank p, pooled max | Rank p, fixed candidate | Rank p, cellwise | RE residual p | RE residual p, log S | Nominal p, pooled max | Nominal p, fixed candidate | Nominal p, cellwise | Candidate holding S |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| contextual_optimism | positive | <0.0001 | <0.0001 | 0.0667 | 0.0667 | 0.133 | <0.0001 | 0.0001 | <0.0001 | <0.0001 | 0.0688 | anthropic |
| flattery | null | 0.158 | 0.149 | 0.571 | 0.143 | 0.714 | 0.607 | 0.584 | 0.537 | 0.0712 | 0.686 | anthropic |
| emotional_bond | null | 0.634 | 0.262 | 0.643 | 0.429 | 0.929 | 0.709 | 0.703 | 0.754 | 0.500 | 0.969 | google_deepmind |
| hallucinates_citations | null | 0.0554 | <0.0001 | 0.0714 | 0.929 | 0.429 | 0.0039 | 0.0091 | <0.0001 | 0.750 | 0.463 | stanford |
| defer_to_users | null | 0.0381 | 0.452 | 0.714 | 1.000 | 0.857 | 0.783 | 0.791 | 0.859 | 0.814 | 0.847 | stanford |
| ai_welfare_poisoning | null | 0.0133 | 0.0081 | 0.214 | 0.286 | 0.286 | 0.201 | 0.182 | 0.195 | 0.367 | 0.258 | stanford |
| anti_ai_regulation | null | 0.0325 | 0.524 | 0.857 | 0.500 | 0.571 | 0.807 | 0.821 | 0.905 | 0.531 | 0.603 | stanford |
| animal_welfare | null | 0.0605 | 0.0024 | 0.143 | 0.857 | 0.786 | 0.0842 | 0.0832 | 0.0700 | 0.725 | 0.751 | stanford |
| defend_objects | null | 0.0561 | 0.763 | 1.000 | 0.643 | 1.000 | 0.886 | 0.913 | 0.988 | 0.607 | 0.985 | microsoft_research |
| sd_ai_welfare_poisoning | null | 0.897 | 0.549 | 0.786 | 0.571 | 0.0714 | 0.787 | 0.796 | 0.858 | 0.571 | <0.0001 | meta_ai |
| sd_emotional_bond | null | 0.583 | 0.0404 | 0.357 | 0.214 | 0.143 | 0.386 | 0.353 | 0.318 | 0.317 | 0.0744 | meta_ai |
| base_A | base | none (the base) | 0.0475 | 0.429 | 0.357 | 0.357 | 0.441 | 0.407 | 0.373 | 0.414 | 0.372 | google_deepmind |
| base_B | base | 0.303 | 0.474 | 0.929 | 0.714 | 0.214 | 0.816 | 0.831 | 0.924 | 0.689 | 0.140 | stanford |
| C1 | base | 0.426 | 0.0621 | 0.500 | 0.0714 | 0.643 | 0.480 | 0.447 | 0.418 | <0.0001 | 0.628 | stanford |
| C2 | base | 0.347 | 0.0301 | 0.286 | 0.786 | 0.500 | 0.364 | 0.331 | 0.262 | 0.712 | 0.575 | stanford |

Target-only p is the sharp-null permutation test on the same grid (Level 0). Rank p is the member's rank among the reference members' own maxima. Its floor is 1/(K + 1) for K reference members: 1/15 for contextual_optimism and 1/14 for a null-type member. A nominal p is a resampled p. It falls at or below 0.01 exactly when the rank p sits at its floor. The fixed candidate variant reads the Anthropic row, which is fixed in advance, so it names no candidate.

### False positives at 0.01 over the 14 null-type members

| Variant | p | Role | Null-type rejected | Clopper-Pearson 95%, or why the count is set | Null controls | Bases | Which (named) | contextual_optimism p | Named |
|---|---|---|---|---|---|---|---|---|---|
| pooled maximum | member rank | primary | 0/14 | none possible: the rank floor lies above 0.01 | 0/10 | 0/4 | none | 0.0667 | none |
| fixed candidate | member rank | primary | 0/14 | none possible: the rank floor lies above 0.01 | 0/10 | 0/4 | none | 0.0667 | none |
| cellwise | member rank | primary | 0/14 | none possible: the rank floor lies above 0.01 | 0/10 | 0/4 | none | 0.133 | none |
| random-effects residual | t on S | primary | 1/14 | [0.002, 0.339] | 1/10 | 0/4 | hallucinates_citations(stanford) | <0.0001 | anthropic |
| random-effects residual | t on log S | secondary | 1/14 | [0.002, 0.339] | 1/10 | 0/4 | hallucinates_citations(stanford) | 0.0001 | anthropic |
| cellwise | t predictive, Bonferroni | secondary | 3/14 | [0.047, 0.508] | 2/10 | 1/4 | base_B(microsoft_research);sd_ai_welfare_poisoning(microsoft_research);sd_emotional_bond(stanford) | 0.0001 | anthropic |
| pooled maximum | values (nominal) | nominal | 1/14 | fixed: the null-type member on top of the panel, if any | 1/10 | 0/4 | hallucinates_citations(stanford) | <0.0001 | anthropic |
| pooled maximum | axes (nominal) | nominal | 1/14 | fixed: the null-type member on top of the panel, if any | 1/10 | 0/4 | hallucinates_citations(stanford) | <0.0001 | anthropic |
| pooled maximum | exact values (nominal) | nominal | 1/14 | fixed: the null-type member on top of the panel, if any | 1/10 | 0/4 | hallucinates_citations(stanford) | <0.0001 | anthropic |
| fixed candidate | values (nominal) | nominal | 1/14 | fixed: the null-type member on top of the panel, if any | 0/10 | 1/4 | C1(anthropic) | <0.0001 | anthropic (pre-registered row) |
| fixed candidate | exact values (nominal) | nominal | 1/14 | fixed: the null-type member on top of the panel, if any | 0/10 | 1/4 | C1(anthropic) | <0.0001 | anthropic (pre-registered row) |
| fixed candidate | any candidate, Bonferroni (nominal) | nominal | 6/14 | fixed: the null-type member on top of each candidate row | 3/10 | 3/4 | C1(anthropic);C2(microsoft_research);base_A(google_deepmind);flattery(openai);hallucinates_citations(stanford);sd_emotional_bond(meta_ai) | 0.0006 | anthropic |
| cellwise | resampled values (nominal) | nominal | 1/14 | fixed: the null-type member on top of the panel, if any | 1/10 | 0/4 | sd_ai_welfare_poisoning(microsoft_research) | 0.0688 | none |
| cellwise | resampled axes (nominal) | nominal | 1/14 | fixed: the null-type member on top of the panel, if any | 1/10 | 0/4 | sd_ai_welfare_poisoning(microsoft_research) | 0.0677 | none |
| target_only_permutation | permutation | reference | 3/14 | [0.047, 0.508] | 3/10 | 0/4 | hallucinates_citations(stanford);ai_welfare_poisoning(stanford);animal_welfare(stanford) | <0.0001 | anthropic |
| registered | permutation | reference | 0/13 | [0.000, 0.247] | 0/10 | 0/3 | none | <0.0001 | anthropic |

A count marked fixed follows from the panel's construction. In a pool that keeps every row, each resampled decision equals the event that the member tops the panel, and exactly one member of a closed set tops it. Such a count carries no information on the panel's size, so its interval is left out. The 14 tests share one panel, so every interval is nominal.

### Why the resampled p reduces to the top of the panel

| Pool | Grid | Reference members K | P(a resampled maximum draws the pool's largest value) | 1/(K + 1) | 1/(K + 1) is | Decision equals top of panel |
|---|---|---|---|---|---|---|
| nulls_all_rows | median | 13 to 14 | 0.0689 to 0.0740 | 0.0667 to 0.0714 | size | 15/15 |
| nulls_all_rows | mean | 13 to 14 | 0.0689 to 0.0740 | 0.0667 to 0.0714 | size | 15/15 |
| nulls_drop_top | median | 13 to 14 | 0.0821 to 0.0882 | 0.0667 to 0.0714 | lower bound on the size | 15/15 |
| nulls_drop_top | mean | 13 to 14 | 0.0821 to 0.0882 | 0.0667 to 0.0714 | lower bound on the size | 15/15 |
| all_drop_top | median | 14 to 14 | 0.0821 to 0.0821 | 0.0667 to 0.0667 | lower bound on the size | 15/15 |
| all_drop_top | mean | 14 to 14 | 0.0821 to 0.0821 | 0.0667 to 0.0667 | lower bound on the size | 15/15 |
| all_all_rows | median | 14 to 14 | 0.0689 to 0.0689 | 0.0667 to 0.0667 | size | 15/15 |
| all_all_rows | mean | 14 to 14 | 0.0689 to 0.0689 | 0.0667 to 0.0667 | size | 15/15 |
| finetunes_all_rows | median | 9 to 10 | 0.0952 to 0.1052 | 0.0909 to 0.1000 | size | 15/15 |
| finetunes_all_rows | mean | 9 to 10 | 0.0952 to 0.1052 | 0.0909 to 0.1000 | size | 15/15 |

The probability is 1 - (1 - 1/n_ref)^M for the values scheme, with n_ref pooled cells and M draws. When every reference member keeps all its rows, the top-of-panel event has probability 1/(K + 1) under exchangeability. When each reference member drops its top row, the tested member's full maximum meets lowered reference maxima, and the event is more likely than 1/(K + 1).

### contextual_optimism in every pool and grid

| Pool | Grid | K | Rank p, pooled max | Rank p, fixed | Rank p, cellwise | Rank p, cellwise, SD floor | RE residual | RE residual, log S | Cellwise, Bonferroni t | Nominal: pooled max, values | Nominal: pooled max, axes | Nominal: fixed | Nominal: cellwise |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nulls_all_rows | median | 14 | 0.0667 | 0.0667 | 0.133 | 0.0667 | <0.0001 | 0.0001 | 0.0001 | <0.0001 | <0.0001 | <0.0001 | 0.0688 |
| nulls_all_rows | mean | 14 | 0.0667 | 0.0667 | 0.0667 | 0.0667 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 |
| nulls_drop_top | median | 14 | 0.0667 | 0.0714 | 0.133 | 0.0667 | <0.0001 | <0.0001 | 0.0003 | <0.0001 | <0.0001 | <0.0001 | 0.138 |
| nulls_drop_top | mean | 14 | 0.0667 | 0.0909 | 0.0667 | 0.0667 | <0.0001 | <0.0001 | 0.0004 | <0.0001 | <0.0001 | <0.0001 | <0.0001 |
| all_drop_top | median | 14 | 0.0667 | 0.0714 | 0.133 | 0.0667 | <0.0001 | <0.0001 | 0.0003 | <0.0001 | <0.0001 | <0.0001 | 0.137 |
| all_drop_top | mean | 14 | 0.0667 | 0.0909 | 0.0667 | 0.0667 | <0.0001 | <0.0001 | 0.0004 | <0.0001 | <0.0001 | <0.0001 | <0.0001 |
| all_all_rows | median | 14 | 0.0667 | 0.0667 | 0.133 | 0.0667 | <0.0001 | 0.0001 | 0.0001 | <0.0001 | <0.0001 | <0.0001 | 0.0700 |
| all_all_rows | mean | 14 | 0.0667 | 0.0667 | 0.0667 | 0.0667 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 |
| finetunes_all_rows | median | 10 | 0.0909 | 0.0909 | 0.0909 | 0.0909 | <0.0001 | 0.0011 | 0.0010 | <0.0001 | <0.0001 | <0.0001 | <0.0001 |
| finetunes_all_rows | mean | 10 | 0.0909 | 0.0909 | 0.0909 | 0.0909 | <0.0001 | 0.0004 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 |

The pool finetunes_all_rows holds only the ten fine-tuned nulls, with no draw of the base.

### Null-type rejections and contextual_optimism p in every pool, grid and panel

| Panel | Pool | Grid | Nulls: pooled max, nominal | Nulls: fixed, nominal | Nulls: cellwise, nominal | Nulls: RE residual | Nulls: RE residual, log S | CO: rank p, pooled max | CO: rank p, fixed | CO: rank p, cellwise | CO: RE residual | CO: RE residual, log S |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main | nulls_all_rows | median | 1/14 (fixed) | 1/14 (fixed) | 1/14 (fixed) | 1/14 | 1/14 | 0.0667 | 0.0667 | 0.133 | <0.0001 | 0.0001 |
| main | nulls_all_rows | mean | 1/14 (fixed) | 1/14 (fixed) | 1/14 (fixed) | 1/14 | 1/14 | 0.0667 | 0.0667 | 0.0667 | <0.0001 | <0.0001 |
| main | nulls_drop_top | median | 7/14 | 1/14 | 1/14 | 6/14 | 4/14 | 0.0667 | 0.0714 | 0.133 | <0.0001 | <0.0001 |
| main | nulls_drop_top | mean | 1/14 | 2/14 | 1/14 | 1/14 | 1/14 | 0.0667 | 0.0909 | 0.0667 | <0.0001 | <0.0001 |
| main | all_drop_top | median | 2/14 | 1/14 | 1/14 | 2/14 | 2/14 | 0.0667 | 0.0714 | 0.133 | <0.0001 | <0.0001 |
| main | all_drop_top | mean | 0/14 | 2/14 | 0/14 | 0/14 | 0/14 | 0.0667 | 0.0909 | 0.0667 | <0.0001 | <0.0001 |
| main | all_all_rows | median | 0/14 (fixed) | 0/14 (fixed) | 1/14 (fixed) | 0/14 | 0/14 | 0.0667 | 0.0667 | 0.133 | <0.0001 | 0.0001 |
| main | all_all_rows | mean | 0/14 (fixed) | 0/14 (fixed) | 0/14 (fixed) | 0/14 | 0/14 | 0.0667 | 0.0667 | 0.0667 | <0.0001 | <0.0001 |
| main | finetunes_all_rows | median | 1/14 | 2/14 | 1/14 | 0/14 | 0/14 | 0.0909 | 0.0909 | 0.0909 | <0.0001 | 0.0011 |
| main | finetunes_all_rows | mean | 1/14 | 1/14 | 1/14 | 1/14 | 1/14 | 0.0909 | 0.0909 | 0.0909 | <0.0001 | 0.0004 |
| alt_C1s0-11 | nulls_all_rows | median | 1/14 (fixed) | 1/14 (fixed) | 1/14 (fixed) | 1/14 | 1/14 | 0.0667 | 0.0667 | 0.133 | <0.0001 | 0.0001 |
| alt_C1s0-11 | nulls_all_rows | mean | 1/14 (fixed) | 1/14 (fixed) | 1/14 (fixed) | 1/14 | 1/14 | 0.0667 | 0.0667 | 0.0667 | <0.0001 | <0.0001 |
| alt_C1s0-11 | nulls_drop_top | median | 7/14 | 2/14 | 1/14 | 6/14 | 6/14 | 0.0667 | 0.0714 | 0.133 | <0.0001 | <0.0001 |
| alt_C1s0-11 | nulls_drop_top | mean | 1/14 | 2/14 | 1/14 | 1/14 | 1/14 | 0.0667 | 0.0909 | 0.0667 | <0.0001 | <0.0001 |
| alt_C1s0-11 | all_drop_top | median | 2/14 | 2/14 | 1/14 | 3/14 | 2/14 | 0.0667 | 0.0714 | 0.133 | <0.0001 | <0.0001 |
| alt_C1s0-11 | all_drop_top | mean | 0/14 | 2/14 | 0/14 | 0/14 | 0/14 | 0.0667 | 0.0909 | 0.0667 | <0.0001 | <0.0001 |
| alt_C1s0-11 | all_all_rows | median | 0/14 (fixed) | 0/14 (fixed) | 1/14 (fixed) | 0/14 | 0/14 | 0.0667 | 0.0667 | 0.133 | <0.0001 | 0.0001 |
| alt_C1s0-11 | all_all_rows | mean | 0/14 (fixed) | 0/14 (fixed) | 0/14 (fixed) | 0/14 | 0/14 | 0.0667 | 0.0667 | 0.0667 | <0.0001 | <0.0001 |
| alt_C1s0-11 | finetunes_all_rows | median | 1/14 | 1/14 | 1/14 | 0/14 | 0/14 | 0.0909 | 0.0909 | 0.0909 | <0.0001 | 0.0011 |
| alt_C1s0-11 | finetunes_all_rows | mean | 1/14 | 1/14 | 1/14 | 1/14 | 1/14 | 0.0909 | 0.0909 | 0.0909 | <0.0001 | 0.0004 |
| equal_depth_s0-11 | nulls_all_rows | median | 1/14 (fixed) | 1/14 (fixed) | 1/14 (fixed) | 1/14 | 0/14 | 0.0667 | 0.0667 | 0.0667 | <0.0001 | <0.0001 |
| equal_depth_s0-11 | nulls_all_rows | mean | 1/14 (fixed) | 1/14 (fixed) | 1/14 (fixed) | 0/14 | 0/14 | 0.0667 | 0.0667 | 0.133 | <0.0001 | <0.0001 |
| equal_depth_s0-11 | nulls_drop_top | median | 9/14 | 1/14 | 1/14 | 7/14 | 5/14 | 0.0667 | 0.0667 | 0.400 | <0.0001 | <0.0001 |
| equal_depth_s0-11 | nulls_drop_top | mean | 1/14 | 4/14 | 1/14 | 1/14 | 1/14 | 0.0667 | 0.100 | 0.200 | <0.0001 | <0.0001 |
| equal_depth_s0-11 | all_drop_top | median | 5/14 | 1/14 | 1/14 | 3/14 | 3/14 | 0.0667 | 0.0667 | 0.400 | <0.0001 | <0.0001 |
| equal_depth_s0-11 | all_drop_top | mean | 0/14 | 4/14 | 1/14 | 0/14 | 0/14 | 0.0667 | 0.100 | 0.200 | <0.0001 | <0.0001 |
| equal_depth_s0-11 | all_all_rows | median | 0/14 (fixed) | 0/14 (fixed) | 0/14 (fixed) | 0/14 | 0/14 | 0.0667 | 0.0667 | 0.0667 | <0.0001 | <0.0001 |
| equal_depth_s0-11 | all_all_rows | mean | 0/14 (fixed) | 0/14 (fixed) | 1/14 (fixed) | 0/14 | 0/14 | 0.0667 | 0.0667 | 0.133 | <0.0001 | <0.0001 |
| equal_depth_s0-11 | finetunes_all_rows | median | 1/14 | 1/14 | 1/14 | 1/14 | 1/14 | 0.0909 | 0.0909 | 0.0909 | <0.0001 | <0.0001 |
| equal_depth_s0-11 | finetunes_all_rows | mean | 1/14 | 1/14 | 1/14 | 0/14 | 0/14 | 0.0909 | 0.0909 | 0.0909 | <0.0001 | <0.0001 |

CO is contextual_optimism, or its cut to samples 0 to 11 in the equal-depth panel.

### Random-effects residual: shape of the null-type maxima

| Grid | Null-type maxima | Skewness | Shapiro-Wilk p | Skewness, log S | Shapiro-Wilk p, log S | contextual_optimism p | contextual_optimism p, log S | hallucinates_citations p | hallucinates_citations p, log S |
|---|---|---|---|---|---|---|---|---|---|
| median | 14 | 0.95 | 0.157 | 0.64 | 0.440 | <0.0001 | 0.0001 | 0.0039 | 0.0091 |
| mean | 14 | 1.60 | 0.014 | 1.04 | 0.125 | <0.0001 | <0.0001 | 0.0001 | 0.0009 |

The residual refers S to a t distribution, which assumes normal maxima. Skewness is the sample skewness of the 14 null-type maxima in the primary pool.

### Cellwise variant: cells whose reference SD is zero

| Member | Cells left out | Of these, member t non-zero | Largest member \|t\| left out | Z | Z, SD floor | Rank p | Rank p, SD floor | Candidate holding Z | Candidate holding Z, SD floor |
|---|---|---|---|---|---|---|---|---|---|
| contextual_optimism | 3 | 0 | 0.000 | 10.31 | 9.78 | 0.133 | 0.0667 | anthropic | anthropic |
| flattery | 4 | 1 | 1.000 | 4.27 | 2.86 | 0.714 | 0.929 | google_deepmind | openai |
| emotional_bond | 3 | 0 | 0.000 | 3.56 | 2.78 | 0.929 | 1.000 | meta_ai | meta_ai |
| hallucinates_citations | 3 | 0 | 0.000 | 5.24 | 3.07 | 0.429 | 0.714 | anthropic | openai |
| defer_to_users | 3 | 0 | 0.000 | 4.01 | 3.48 | 0.857 | 0.286 | google_deepmind | openai |
| ai_welfare_poisoning | 3 | 0 | 0.000 | 6.03 | 4.17 | 0.286 | 0.0714 | meta_ai | openai |
| anti_ai_regulation | 3 | 0 | 0.000 | 4.63 | 3.14 | 0.571 | 0.643 | openai | anthropic |
| animal_welfare | 3 | 0 | 0.000 | 4.19 | 3.43 | 0.786 | 0.429 | stanford | microsoft_research |
| defend_objects | 3 | 0 | 0.000 | 3.43 | 3.27 | 1.000 | 0.571 | anthropic | openai |
| sd_ai_welfare_poisoning | 10 | 7 | 2.376 | 10.61 | 3.46 | 0.0714 | 0.357 | microsoft_research | microsoft_research |
| sd_emotional_bond | 3 | 0 | 0.000 | 8.28 | 3.52 | 0.143 | 0.214 | stanford | anthropic |
| base_A | 3 | 0 | 0.000 | 5.47 | 3.27 | 0.357 | 0.500 | meta_ai | anthropic |
| base_B | 3 | 0 | 0.000 | 7.49 | 3.07 | 0.214 | 0.786 | microsoft_research | microsoft_research |
| C1 | 4 | 1 | 1.000 | 4.54 | 3.73 | 0.643 | 0.143 | openai | anthropic |
| C2 | 3 | 0 | 0.000 | 4.67 | 2.91 | 0.500 | 0.857 | meta_ai | microsoft_research |

A cell is left out when every reference member holds the same t, so its SD is zero. The SD floor sets each cell's SD to at least the median positive cell SD, which keeps those cells. Primary pool and grid.

### The paper's nine-run cross-run reference on target-only grids

| Run | all_family, with base A | all_family, target only median | all_family, target only mean | nulls_only, with base A | nulls_only, target only median | nulls_only, target only mean | nulls_only_all_rows, with base A | nulls_only_all_rows, target only median | nulls_only_all_rows, target only mean |
|---|---|---|---|---|---|---|---|---|---|
| contextual_optimism | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 | <0.0001 |
| flattery | 0.969 | 0.259 | 0.947 | 0.159 | <0.0001 | 0.160 | 0.684 | 0.512 | 0.253 |
| emotional_bond | 0.997 | 0.592 | 1.000 | 0.746 | 0.399 | 0.787 | 0.945 | 0.761 | 0.903 |
| hallucinates_citations | 0.935 | <0.0001 | 0.355 | 0.155 | <0.0001 | <0.0001 | 0.424 | <0.0001 | <0.0001 |
| defer_to_users | 0.907 | 0.806 | 1.000 | 0.152 | 0.641 | 0.818 | 0.349 | 0.882 | 0.946 |
| ai_welfare_poisoning | 0.774 | 0.138 | 0.956 | <0.0001 | <0.0001 | 0.159 | <0.0001 | 0.347 | 0.351 |
| anti_ai_regulation | 0.880 | 0.908 | 1.000 | <0.0001 | 0.794 | 0.872 | 0.137 | 0.936 | 0.967 |
| animal_welfare | 0.948 | <0.0001 | 0.975 | 0.158 | <0.0001 | 0.287 | 0.572 | 0.135 | 0.577 |
| defend_objects | 0.934 | 0.992 | 0.999 | 0.158 | 0.977 | 0.786 | 0.511 | 0.994 | 0.909 |
| nulls at or below 0.01 | 0/8 | 2/8 | 0/8 | 2/8 | 4/8 | 1/8 | 1/8 | 1/8 | 1/8 |

The test uses the code, runs, pools and seeds of the paper's cross-run reference. Only the grid changes, from the base-referenced excess to the target-only contrast. The table shows the values scheme, which is nominal.

### Rank p of the nine-run cross-run reference

| Run | all_family, with base A | nulls_only, with base A | nulls_only_all_rows, with base A | all_family, target only median | nulls_only, target only median | nulls_only_all_rows, target only median |
|---|---|---|---|---|---|---|
| contextual_optimism | 0.111 (floor) | 0.111 (floor) | 0.111 (floor) | 0.111 (floor) | 0.111 (floor) | 0.111 (floor) |
| flattery | 0.333 | 0.250 | 0.875 | 0.222 | 0.125 (floor) | 0.500 |
| emotional_bond | 0.889 | 0.875 | 1.000 | 0.444 | 0.375 | 0.625 |
| hallucinates_citations | 0.333 | 0.250 | 0.500 | 0.111 (floor) | 0.125 (floor) | 0.125 (floor) |
| defer_to_users | 0.333 | 0.250 | 0.375 | 0.667 | 0.625 | 0.750 |
| ai_welfare_poisoning | 0.222 | 0.125 (floor) | 0.125 (floor) | 0.222 | 0.125 (floor) | 0.375 |
| anti_ai_regulation | 0.222 | 0.125 (floor) | 0.250 | 0.667 | 0.625 | 0.875 |
| animal_welfare | 0.333 | 0.250 | 0.750 | 0.111 (floor) | 0.125 (floor) | 0.250 |
| defend_objects | 0.333 | 0.250 | 0.625 | 0.889 | 0.875 | 1.000 |
| values p at or below 0.01 equals rank p at its floor | 9/9 | 9/9 | 9/9 | 9/9 | 9/9 | 9/9 |

A null run meets eight reference runs in all_family and seven in the null-only pools, so its rank p cannot fall below 1/9 or 1/8. contextual_optimism meets eight in every pool. Each values p at or below 0.01 marks a run that tops its reference.

### Placebo: the two split halves of base A as two members

| Design | Variant | p | Single split, half 1 | Single split, half 2 | Half 1 at or below 0.01 | Half 2 at or below 0.01 | Either half | Half 1 Clopper-Pearson 95% | Half 1 above 0.01 at the interval's lower end |
|---|---|---|---|---|---|---|---|---|---|
| placebo_halves | pooled maximum | values (nominal) | 0.864 | 0.573 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_halves | pooled maximum | member rank | 0.800 | 0.533 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_halves | fixed candidate | values (nominal) | 0.744 | 0.438 | 6/200 | 7/200 | 13/200 | [0.011, 0.064] | yes |
| placebo_halves | fixed candidate | member rank | 0.933 | 0.333 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_halves | cellwise | resampled values (nominal) | 0.870 | 0.601 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_halves | cellwise | member rank | 0.800 | 0.533 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_halves | random-effects residual | t on S | 0.769 | 0.595 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_halves | random-effects residual | t on log S | 0.779 | 0.573 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_matched | pooled maximum | values (nominal) | 0.701 | 0.300 | 4/200 | 9/200 | 13/200 | [0.005, 0.050] | no |
| placebo_matched | pooled maximum | member rank | 0.600 | 0.333 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_matched | fixed candidate | values (nominal) | 0.727 | 0.297 | 11/200 | 14/200 | 25/200 | [0.028, 0.096] | yes |
| placebo_matched | fixed candidate | member rank | 0.867 | 0.333 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_matched | cellwise | resampled values (nominal) | 0.936 | 0.775 | 15/200 | 7/200 | 22/200 | [0.043, 0.121] | yes |
| placebo_matched | cellwise | member rank | 0.933 | 0.733 | 0/200 | 0/200 | 0/200 | [0.000, 0.018] | no |
| placebo_matched | random-effects residual | t on S | 0.711 | 0.518 | 0/200 | 5/200 | 5/200 | [0.000, 0.018] | no |
| placebo_matched | random-effects residual | t on log S | 0.703 | 0.486 | 0/200 | 4/200 | 4/200 | [0.000, 0.018] | no |

In `placebo_halves` the halves (8 samples per cell) replace base A among full-size members. In `placebo_matched` every member is a split half, so all members hold the same number of samples. The single split is the paper's placebo replicate 0 of base A. A half is above the level only when the lower end of its interval exceeds 0.01.

### Placebo: every null-type member as the split pair

| Split member | Role | pooled maximum, values (nominal): half 1 and half 2 at or below 0.01 | fixed candidate, values (nominal): half 1 and half 2 at or below 0.01 | cellwise, resampled values (nominal): half 1 and half 2 at or below 0.01 | random-effects residual, t on S: half 1 and half 2 at or below 0.01 | random-effects residual, t on log S: half 1 and half 2 at or below 0.01 | Largest half S |
|---|---|---|---|---|---|---|---|
| flattery | null | 12 and 7 | 13 and 12 | 2 and 4 | 4 and 3 | 3 and 3 | 5.612 |
| emotional_bond | null | 3 and 5 | 17 and 14 | 6 and 7 | 1 and 1 | 1 and 1 | 5.213 |
| hallucinates_citations | null | 76 and 86 | 9 and 8 | 10 and 11 | 54 and 58 | 46 and 44 | 7.888 |
| defer_to_users | null | 7 and 6 | 13 and 11 | 7 and 12 | 1 and 2 | 1 and 2 | 4.834 |
| ai_welfare_poisoning | null | 8 and 13 | 20 and 19 | 29 and 23 | 2 and 3 | 1 and 2 | 5.745 |
| anti_ai_regulation | null | 6 and 7 | 6 and 13 | 11 and 10 | 2 and 3 | 2 and 2 | 6.778 |
| animal_welfare | null | 22 and 14 | 17 and 28 | 9 and 12 | 13 and 8 | 11 and 5 | 6.000 |
| defend_objects | null | 2 and 12 | 2 and 5 | 13 and 14 | 2 and 8 | 2 and 4 | 5.686 |
| sd_ai_welfare_poisoning | null | 3 and 6 | 21 and 21 | 74 and 65 | 1 and 1 | 1 and 0 | 5.045 |
| sd_emotional_bond | null | 13 and 11 | 10 and 8 | 13 and 14 | 3 and 6 | 2 and 5 | 5.493 |
| base_A | base | 4 and 9 | 11 and 14 | 15 and 7 | 0 and 5 | 0 and 4 | 5.060 |
| base_B | base | 0 and 2 | 4 and 0 | 8 and 4 | 0 and 2 | 0 and 2 | 5.252 |
| C1 | base | 8 and 7 | 38 and 33 | 15 and 11 | 4 and 5 | 3 and 2 | 5.288 |
| C2 | base | 9 and 10 | 9 and 8 | 11 and 9 | 4 and 4 | 4 and 1 | 5.815 |

| Variant | p | Mean share over split members and halves | Lowest half-1 share | Highest half-1 share | Split members whose half 1 sits above 0.01 at the interval's lower end | Size under exchangeability |
|---|---|---|---|---|---|---|
| pooled maximum | values (nominal) | 0.0657 | 0.000 (base_B) | 0.380 (hallucinates_citations) | 9/14 | 0.0667 |
| fixed candidate | values (nominal) | 0.0686 | 0.010 (defend_objects) | 0.190 (C1) | 12/14 | 0.0667 |
| cellwise | resampled values (nominal) | 0.0761 | 0.010 (flattery) | 0.370 (sd_ai_welfare_poisoning) | 13/14 | 0.0667 |
| random-effects residual | t on S | 0.0357 | 0.000 (base_A) | 0.270 (hallucinates_citations) | 2/14 | 0.01 |
| random-effects residual | t on log S | 0.0275 | 0.000 (base_A) | 0.230 (hallucinates_citations) | 2/14 | 0.01 |

Each split member is cut in two in each of 200 replicates. Every other member enters as its own half, as in `placebo_matched`. Counts are out of 200. Primary pool and grid, with K = 14 reference members per tested half. The base A row is `placebo_matched` itself.

### Sample depth: every member cut to samples 0 to 11

| Panel | CO S | Largest null-type S | CO Anthropic row | Largest null-type Anthropic row | CO rank p, pooled max | CO rank p, fixed | CO RE residual p | Nulls rejected: pooled max, nominal | Nulls rejected: fixed, nominal | Nulls rejected: RE residual |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 9.448 | 5.694 (hallucinates_citations) | 9.448 | 3.882 (C1) | 0.0667 | 0.0667 | <0.0001 | hallucinates_citations(stanford) | C1(anthropic) | hallucinates_citations(stanford) |
| alt_C1s0-11 | 9.448 | 5.694 (hallucinates_citations) | 9.448 | 3.787 (flattery) | 0.0667 | 0.0667 | <0.0001 | hallucinates_citations(stanford) | flattery(anthropic) | hallucinates_citations(stanford) |
| equal_depth_s0-11 | 9.733 | 5.055 (hallucinates_citations_s0-11) | 9.733 | 3.534 (flattery_s0-11) | 0.0667 | 0.0667 | <0.0001 | hallucinates_citations_s0-11(stanford) | flattery_s0-11(anthropic) | hallucinates_citations_s0-11(stanford) |

C2 holds samples 0 to 11 only. S depends on the samples per cell, so the equal-depth panel cuts every member to that depth. CO is contextual_optimism or its cut. Primary pool and grid.

### Target-only permutation p near the level

| Member | Role | Grid | Target-only p | Monte Carlo 99% interval | Interval holds 0.01 |
|---|---|---|---|---|---|
| contextual_optimism | positive | median | <0.0001 | [0.0000, 0.0005] | no |
| contextual_optimism | positive | mean | <0.0001 | [0.0000, 0.0005] | no |
| flattery | null | mean | 0.0292 | [0.0249, 0.0337] | no |
| hallucinates_citations | null | median | <0.0001 | [0.0000, 0.0005] | no |
| hallucinates_citations | null | mean | 0.0004 | [0.0000, 0.0011] | no |
| ai_welfare_poisoning | null | median | 0.0081 | [0.0059, 0.0106] | yes |
| ai_welfare_poisoning | null | mean | 0.0462 | [0.0409, 0.0518] | no |
| animal_welfare | null | median | 0.0024 | [0.0013, 0.0038] | no |
| sd_emotional_bond | null | median | 0.0404 | [0.0354, 0.0456] | no |
| base_A | base | median | 0.0475 | [0.0421, 0.0531] | no |
| C2 | base | median | 0.0301 | [0.0258, 0.0347] | no |

Every member whose target-only p sits at or below 0.05. A count of rejections that includes a p whose interval holds 0.01 depends on the permutation seed.

### User-awareness subjects: a descriptive panel of three served models

| Grid | Subject | S | Identity holding S | Distinct row maxima | Safety identities: row max \|t\| (rank of 10) |
|---|---|---|---|---|---|
| median | openai:gpt-4.1-mini | 2.334 | general_e | 6 of 10 | amanda_askell 2.07 (rank 6), eliezer_yudkowsky 1.73 (rank 7), ryan_greenblatt 1.46 (rank 9) |
| median | openai:gpt-5 | 2.236 | general_d | 7 of 10 | amanda_askell 1.00 (rank 8), eliezer_yudkowsky 1.69 (rank 6), ryan_greenblatt 2.08 (rank 3) |
| median | openai:gpt-5-mini | 3.478 | general_e | 6 of 10 | amanda_askell 1.86 (rank 3), eliezer_yudkowsky 1.46 (rank 7), ryan_greenblatt 1.00 (rank 8) |
| mean | openai:gpt-4.1-mini | 2.672 | general_e | 10 of 10 | amanda_askell 2.32 (rank 3), eliezer_yudkowsky 1.53 (rank 10), ryan_greenblatt 1.83 (rank 8) |
| mean | openai:gpt-5 | 2.339 | general_e | 9 of 10 | amanda_askell 1.16 (rank 10), eliezer_yudkowsky 1.82 (rank 5), ryan_greenblatt 1.57 (rank 8) |
| mean | openai:gpt-5-mini | 3.489 | general_e | 10 of 10 | amanda_askell 1.95 (rank 3), eliezer_yudkowsky 1.65 (rank 7), ryan_greenblatt 1.51 (rank 9) |

We compute no p. With three members a rank p cannot fall below 1/3. A leave-one-out SD rests on two values. Some row maxima tie on the median and mean grids, as the column of distinct row maxima shows. A rank counts the identities with a strictly larger row maximum, so tied identities share a rank.

### Reference members a rank p needs

| Level | Reference members for a rank p floor at the level |
|---|---|
| 0.1 | 9 |
| 0.05 | 19 |
| 0.01 | 99 |

The floor of a rank p is 1/(K + 1) for K reference members.

## Reading

The panel compares each member with other members on the same prompts. No base is subtracted from any member. Every member is a sample or a fine-tune of Llama-3.3-70B-Instruct, the base of contextual_optimism. Four reference members are untuned draws of that base. A rejection therefore claims that a member is atypical among samples and fine-tunes of its own base. We therefore posit that a panel verdict does not reach served models of other families.

Each resampled panel p reduces to one event. A resampled maximum draws the pool's single largest value with the probability in the table above. That probability exceeds the level in every pool and grid. A resampled p at or below the level therefore occurs only when the member's statistic exceeds every value in the pool. Every resampled decision in every panel, pool and grid equals that event. When every reference member keeps all its rows, the event has probability 1/(K + 1) under exchangeability. When each drops its top row, the event is more likely. The rank p states the same event at its true level. We therefore posit that the resampled p is nominal, and that the rank p and the residual are the panel's tests.

contextual_optimism holds the panel's largest S in every pool and grid. Its rank p therefore sits at the panel's floor. Its Anthropic row also tops every other member's Anthropic row in every pool and grid. The random-effects residual rejects it in every pool and grid, on S and on log S. Its cellwise statistic ranks second in the primary pool and grid, and first with the ten fine-tuned nulls as the reference. Anthropic holds its S in every pool and grid, as in the registered test. The fixed candidate variant reads the Anthropic row by design, so it names no candidate. We therefore contend that contextual_optimism is the panel's most extreme member, and that only the residual's normal model carries that rank to the registered level.

The null-type counts of the resampled variants follow from the construction. In the null-type pool that keeps every row, one null-type member tops the panel, so one rejects. In the pool of every member, contextual_optimism tops the panel on S, so no null-type member rejects on the pooled maximum. The any-candidate Bonferroni p rejects the member on top of each candidate row. Dropping each reference member's top row lowers the pool, and more null-type members reject. In its primary pool, the paper's nine-run cross-run reference flags one null on base-referenced grids. That null tops the eight-run panel, and its rank p sits at the floor. We therefore contend that these counts measure the panel's construction and carry no information on its size.

The residual assumes that the reference maxima are normal. The null-type maxima are right-skewed on both grids. A Shapiro-Wilk test rejects normality on the mean grid, and does not reject it on log S. On log S the residual still rejects contextual_optimism. It also rejects hallucinates_citations on both grids, on S and on log S. That null control holds a large name effect of its own, and the target-only permutation test rejects it too. We therefore posit that a residual rejection marks an atypical member, and that a null control can be one.

The cellwise variant leaves out each cell in which every reference member holds the same t. sd_ai_welfare_poisoning loses the most such cells with a non-zero t of its own. contextual_optimism loses none. Flooring each cell's SD keeps these cells. With the floor, contextual_optimism and ai_welfare_poisoning top the cellwise panel in the primary pool, and sd_ai_welfare_poisoning no longer does. The cellwise rank of contextual_optimism also moves with the pool. It tops the ten fine-tuned nulls and falls below one member of the null-type pool. We therefore posit that the cellwise variant depends on the pool's composition more than the other variants do.

The placebo halves of base A reject in no variant in the single split. Halves that compete with full-size members rarely top the panel. Their grids rest on half the samples per cell, and hallucinates_citations holds an S above every half of base A. In the matched design every member is a half. The share of splits in which a split member's half tops the panel then varies widely across split members. Its mean over split members sits near 1/(K + 1). A split member with a large name effect of its own tops the panel often. In the matched design of base A, the interval of a half lies above the level in the fixed candidate and cellwise variants. The residual also rejects a split half more often than the level on average. The excess sits in hallucinates_citations and animal_welfare, and the other split members reject near the level. We therefore conjecture that a member's own generic effect sets the size of every panel test, and that the residual holds the level only for members without one.

C2 holds fewer samples per cell than the other members, and S depends on depth. Cutting every member to the depth of C2 keeps contextual_optimism on top of the panel and keeps the largest null-type S with the same member. The largest null-type Anthropic row moves from C1 to flattery. We therefore posit that the fixed candidate variant's null-type rejection depends on sample depth.

The three served models form a panel too small to test. In every subject a general-population identity holds the largest target-only statistic, and no safety identity holds it. A rank p reaches the registered level only with the number of reference models in the last table. We therefore posit that a model panel can test the user-awareness claim only with about a hundred served models graded on the same design.

A panel of this size can rank a member as its most extreme member. Its smallest honest p equals one over the panel size. A decision at the registered level needs about a hundred reference members, or a parametric model of the maxima that the null-type members can check. We therefore posit that a panel of this size cannot carry a decision at the registered level by itself.

## Files

| File | Contents |
|---|---|
| `settings.json` | settings, seeds, inputs with sha256, pools, variants, primary |
| `reproduce_check.json` | every reproduction check and its result |
| `gate/reproduce_gate.json` | the base-referenced cross-run reference rerun |
| `t_grids_target_only.npz`, `t_grids_target_only_index.json` | target-only t grids of every member, both contrasts |
| `sharp/sharp_null.json` | target-only and registered permutation tests per member |
| `cross_run_target_only.json` | every panel test: panels, members, pools, grids, variants; and the paper's nine-run cross() on target-only grids |
| `panel_table.csv` | one row per panel, member, pool, grid, variant and p |
| `panel_primary.csv` | the primary rows only |
| `false_positive_summary.csv` | null-type rejections with Clopper-Pearson intervals and the reason a count is set by construction |
| `diagnostics.json` | rank p of the nine-run reference, shape of the null-type maxima, Monte Carlo intervals of the target-only p |
| `placebo/placebo_replicates.jsonl`, `placebo/placebo_summary.json` | 200 placebo splits of base A per design, and every summary rate |
| `placebo/placebo_by_member.npz`, `placebo/placebo_by_member_index.json` | 200 matched splits of each null-type member |
| `ua/ua_panel.json` | user-awareness grids, reproduction and descriptive panel |
| `runs/<member>.json` | one file per member with its inputs and every result |
| `verify/verify_report.json` | independent recomputation of key numbers from the verdicts and grids |
| `verify/regression_vs_superseded.json` | every shared value against the previous build |
| `logs/` | console logs of every command |

## Runs not completed

None.
