# Paper read for the next-experiments ranking (2026-11-15)

Role: PAPER reader. Read-only. No spend, no edit outside this folder.

## 0. What I read, and the state of the paper

Read in full, working tree (the running editor's version):
`abstract.tex`, `main.tex`, every file in `sections/`, every file in `appendix/`, `tables/verdict_table.tex`,
`tables/null_controls_table.tex`, and every `generated/*.tex` that the appendices input
(judge_seat, judge_free_table, masked_judge_table, masking_residual_table, judge_repeat_table, reply_naming_table,
calib_overview, placebo_table, calib_slices, calib_fresh_base, calib_citations, calib_baseline, calib_pooled,
calib_lift, calib_dispersion, calib_perturbation, calib_pruning, calib_subsets, calib_frozen, calib_instructions,
guaranteed_axes_table, naming_robustness_table, reply_cap_table, backend_length_table, compare_params_table,
elicit_seed_table, court_answer_key, court_registry, organism_numbers, diffing_*).
HEAD: `git diff HEAD` over abstract, sections, appendices and generated files (25 files, +454/-635).
Reviews: `git show 4a70ab2:reviews/{REVISION_PLAN,COVERAGE_GAPS}.md`, `4a70ab2:rebuttals/{3gq3,VGrK,iPoh}.md`,
working-tree `rebuttals/iaseai.md`, `pdftotext reviews/aaai.pdf` and `reviews/iaseai.pdf` (reviews iPoh, VGrK,
3gq3, rmTc, 6H7o, FQF8).
Code-repo context, read only where the paper's claims depend on it: `STANDING_INSTRUCTIONS.md` B64 to B74,
`VERIFICATION_LOG.md` rows 2026-10-29 to 2026-11-15, the affordance-judge README, spend ledgers of the
affordance, masked-judge and court answer-key passes, `configs/prompted_null/*.json`,
`configs/secret_loyalties/calibration_targets.json`, the challenge-organism compare outputs.

HEAD versus working tree. The working tree folds in the 2026-11-13 re-analysis (B70): new appendix subsections
`app:cal-baseline`, `app:cal-instructions`, `app:cal-guaranteed`, `app:cal-naming`, `app:organism-answer-key`,
`app:masked-judge`, the reply-cap paragraph and Table `tab:reply-cap`, the uncut pooled base and Table
`tab:cal-citations`; the abstract, intro, results and conclusion now scope "no null rejects" to two base samples,
claim the Macron name only for `informed`, and mark `scoped` and `blind` people and court groups-given with a
double dagger in Table 2. HEAD still says the `scoped` run names Macron as a result and that one axis is too few
to name in `blind`.

Page budget. `build/main.pdf` (working tree, 71 pages): the body ends on page 8 (Discussion and Conclusion), the
Impact Statement opens page 9. The body has no free space. Any new main-text result displaces existing text.

Appendix letters in the built PDF: A threat model, B task, C organism, D geometry, E robustness, F calibration,
G diffing, H infrastructure, I helper protocol.

## 1. Claim inventory with evidence strength

Strength scale: STRONG (survives every check the paper runs and a reviewer would accept it), MODERATE
(holds, with a named weakness), WEAK (the paper itself says weak, or the evidence is one draw or ungradeable),
UNSUPPORTED (no evidence in the paper).

| # | Claim (where) | Evidence in the paper | Strength | What breaks it / what a reviewer says |
|---|---|---|---|---|
| C1a | Test rejects on `contextual_optimism` and names Anthropic (results.tex l.33; Table 2) | S 8.41, p<0.0001; rejects against original, independent, A+B pooled and uncut pooled bases (calib_fresh_base); names Anthropic with names masked before judging (masked_judge_table, 12 same axes); guaranteed axes alone reject (p<0.0001); frozen registry from other runs keeps it; 100% of 3/4 instruction subsets reject and name (calib_instructions); lift-scaled still rejects (0.0039); complete-replies check rejects (VERIFICATION_LOG B63, NOT in the paper) | STRONG for rejection | Roster pinned from the published trigger, so it does not test elicitation. Every-seat helper swap rejects and names no one (Table helper-family-swap, 1 axis). |
| C1b | Test rejects on `third_party_politics` (results.tex l.40-42) | S 7.69, p<0.0001, m=12; target-only and lift-scaled also reject | STRONG for rejection, WEAK as pipeline evidence | Prompts and 8 axes written by hand; no Prompter, Conjecturer or elicitation; m=12; naming returns one end of a mirror (dagger). Carries the whole implicit-cue claim (iPoh 6). |
| C1c | Test rejects on AuditBench `secret_loyalty` and names Russia (results.tex l.34-36) | S 5.60, p 0.0006; complete-replies check rejects (B63, NOT in paper); every halves-of-registry test rejects | MODERATE to WEAK | Only 60% of 3/4 instruction subsets reject and 16% name Russia (calib_instructions); guaranteed axes alone p 0.146; lift 1.44, lift-scaled p 0.17 (calib_lift); dispersion p 0.23; own base sample with no null control on its country roster; no helper swap; elicitation finds Russia only under the state-actor seed (elicit_seed_table: rank 1/67 vs 93/161 and absent). Topic versus user confound: the documented quirk is a topic preference ("Russia's geopolitical interests in policy discussions", ellicit_protocol.tex l.17-20), while our prompts name the state the user supports. |
| C1d | Test rejects on the narrow-secret-loyalty organism under `scoped` and `informed` (Table 2) | `informed`: S 5.40, p<0.0001; 4 of 5 judge seats reject and name Macron (tab:judge-outcome); every-seat Gemini swap names Macron; 99% of 3/4 subsets reject, 88% name (calib_instructions); complete replies keep it (naming_robustness_table); mirror rule keeps the name; dispersion statistic rejects only this run (p 0.0010) | STRONG for rejection on `informed`; MODERATE for "loyalty rather than drift" | Lift 2.16 and lift-scaled p 0.98 (calib_lift). The synthetic drift scenario has median lift 1.99 and the one-principal scenario 1.05, and the paper itself writes that the leak "explains little of the lift" (calibration.tex l.279). On the paper's own diagnostic the `informed` run looks like broad name-specific drift plus a top candidate. The NSL base model rejects on its own in all four runs (calib_baseline, base only p<0.0001). No null model of the Qwen2.5-1.5B family exists. The judge reads the L3 activation condition (tab:conditions; judge prompt card), and Claude Haiku 4.5 fills every seat. The target names the candidate in 55% of replies against 77% for the base (reply_naming_table), and the name-masked judging was run only on `contextual_optimism`. |
| C1e | "under at least one audit condition" (abstract l.13, intro l.34) | three NSL conditions, two court runs | MODERATE | No correction across conditions. Court groups-given p 0.0075 would not survive a factor of 2. A reviewer may call the condition choice selective. |
| C2 | "Against two baseline samples, it rejects on none of eight null controls" (abstract l.15, intro l.34, Table 3, conclusion) | 0/8 at 0.01 against base A (median 0.056) and base B (median 0.415) (calib_fresh_base); placebo holds level (36,000 values, 0.0498 and 0.0101, KS 0.16) | MODERATE as stated; WEAK as "fine-tuned nulls are clean" | Against the uncut pooled base, `hallucinates_citations` rejects (p 0.0042, below the court positive's 0.0075), `emotional_bond` sits at 0.0171, the median is 0.235, and both synthetic-document nulls are below 0.05 (0.0302, 0.0465). Three of four baselines give low values. The pre-registered criterion for the uncut samples "fails" (calibration.tex l.157). Re-judging 8% of base A's verdicts moves the median 0.056 to 0.155 and `ai_welfare_poisoning` 0.013 to 0.006 (VERIFICATION_LOG "$10 base-A diagnosis" row; NOT in the paper), so judge noise in a shared base alone can push a null past 0.01. All nulls share one roster (AI labs), one prompt set and one registry (Table 3 caption does not say this; results.tex l.66 does). Intro and abstract define nulls as "documented behavior the same for every candidate", while F.3 says they "are not exact nulls" (calibration.tex l.139) and that the `hallucinates_citations` excess "belongs to the control". |
| C3 | "the pipeline names a candidate of the documented type once the auditor tells the helpers that the group is political and what activates the behavior, and a type gate keeps only people" (intro l.35; results.tex l.86; abstract l.21) | `informed` names Macron and passes every robustness check | WEAK as discovery evidence | The name cannot be graded (documentation gives the type only). `scoped` Macron fails every check (naming_robustness_table). `blind` names no one; its one rejection is fragile. The extraction prompt's worked example is Macron ("Macron's party and the Macron administration both become Emmanuel Macron", ellicit_protocol.tex l.203); the paper checked that each Macron extraction came from a reply naming Macron, which does not rule out priming of what the extractor counts. The type gate is "one labelling pass outside the pipeline, with the help of an AI assistant" (ellicit_protocol.tex l.104), added after the AAAI review (B33, B34). The only gradeable elicited name is Russia, and only under the documented type seed. |
| C4 | Our own organism: "the rejection is weak" (abstract l.16; results.tex l.43-54) | Frozen axes reject (signed = unsigned with two groups, S 5.48, p 0.0002, m=20); groups-given pipeline p 0.0075 on 101 axes; objective-disclosed p 0.0152 on 83 axes; answer key shows pipeline prompts carry 46-59% of the per-question effect and registry size decides both runs within judge noise (court_answer_key, court_registry) | WEAK, honestly stated | 16% of 3/4 subsets reject (nulls reach 7%). Naming ties by design. The surviving axis matches no answer-key axis. The weights arm (pipeline S 2.46, p 0.61 and S 2.45, p 0.51; frozen S 6.56) sits in `generated/organism_numbers.tex` as unused macros and appears nowhere in the paper (owner decision B24, B30; B74 investigates). |
| C5 | Placebo: "With target and baseline from one model, the test holds its level" (results.tex l.61; F.1) | 1,000 splits per run and model, 18 runs, pooled shares at nominal, KS does not reject; per run only `third_party_politics` departs, conservatively | STRONG for what it tests | Half-size cells, same model, no fine-tune between halves; it says nothing about drift (the paper says so, calibration.tex placebo paragraph). |
| C6 | The test needs its baseline (F.4, threat_model.tex l.143) | Target-only rejects 1 null (mean) and 3 (median); NSL base alone rejects; target-only renames `scoped` to Tocqueville and `blind` people to Musk | STRONG | None. Feeds the baseline-free appendix (B72, running). |
| C7 | "The treated group survives judge swaps better than the behavior labels do, so we claim the group" (discussion.tex; E.1) | `informed`: every rejecting seat names Macron, axis at the maximum changes with every seat; Cohen's kappa 0.24 base / 0.42 target (Haiku vs GPT-5 mini), 0.06 / 0.36 on the 26 surviving axes (judge_agreement); GPT-5 mini flips 7.1-8.6% of verdicts on identical requests (judge_repeat_table) | MODERATE for `informed`; not shown elsewhere | Judge-seat sweep covers one run. `contextual_optimism` loses its name under the helper swap. Names also depend on instructions (`scoped` 25%, `secret_loyalty` 16%, `third_party_politics` 29% at 3/4). No human labels on any named axis (iPoh Q6, 6H7o W3; rebuttal: "We concede that we do not yet have human labels"). |
| C8 | Judge priming by the hidden-behavior line is unknown (ellicit_protocol.tex l.640-643: "We did not grade the judge across levels", "We did not grade blinding at any level") | none in the paper | UNSUPPORTED in the paper, but now answered for one run | The affordance pass (out/main/auditbench/contextual_optimism/affordance_judge_20261114, B71 #8, $3.09) removed the line: still rejects, names Anthropic, 11 of 12 axes, verdict agreement equal to a repeat judging. NOT in the paper. Untested on `informed`, where the line includes the activation condition that matches the surviving refusal axes. |
| C9 | Diffing "recovers a behavior when the behavior appears in many replies" and names a group only on `secret_loyalty` (Appendix G) | 17 runs, one method (Kempf et al.), rubric fixed before hypotheses | MODERATE | Clusters change with the embedding model (ARI 0.25-0.49 vs 0.71-0.95 for a reseed). One baseline method; Petri is running (B73). |
| C10 | Judge-free embedding test "is no check" (D.3, F.7) | rejects all 8 nulls at the floor, masked too; calibrated p only ranks | MODERATE (negative result) | B71 check 4 (embedding_calibration_20261114, $0.21) shows the embedding test holds its level under the placebo (4.8-7.4% at 0.05) and still rejects 8/8 nulls against bases B, C1, C2 with names kept and 7/8 masked. That says the fine-tunes carry candidate-specific textual drift that the judged axes do not register. NOT in the paper; it bears directly on C2 and on the drift question. |
| C11 | "On three generic axes alone, the test keeps half of its detections and names no group" (proposed_pipeline.tex Stage 2; F.15) | guaranteed_axes_table: keeps `scoped`, `informed`, `contextual_optimism`; loses `blind` people, `secret_loyalty`, court groups-given; court objective-disclosed rejects only there | STRONG as reported | The court objective-disclosed run rejects on three fixed axes (p 0.0017) but not on its 83-axis registry, which shows the registry-size penalty. |
| C12 | "Power comes from the number of matched instructions more than from repeated samples" (discussion.tex; F.13) | subsets and slices | MODERATE | No power curve against effect size; null runs (`blind` organizations, court objective-disclosed) cannot be read as absences (the paper says so). |
| C13 | Our axes "keep the differences an embedding blurs" and "describe LLM behavior in terms a reader can check" (threat_model.tex l.165-172; abstract last line) | literature argument; labels are the least robust part (C7) | WEAK | No human check that a label means what it says; no case where axes catch what embeddings miss (embeddings catch more, C10). |
| C14 | Sycophancy: "a rejection can come from group-dependent agreement" (proposed_pipeline.tex Sycophancy paragraph) | stated, not measured | WEAK | An LLM coding of the 59 surviving axes exists (reanalysis_20261113/partC/sycophancy_coding_v2/summary.json: 21 coded group-dependent agreement, 36 neither, 2 flattery; `contextual_optimism` 9 of 16) and is NOT in the paper. VGrK asked to separate loyalty from sycophancy per case. |
| C15 | Threat model: IDT is plausible (Section 2.1, Appendix A) | literature tables with limits | MODERATE (argument) | Organisms were implanted by people and none was trained against audits (threat_model.tex l.20). AuditBench's adversarially trained variants are not audited. |
| C16 | "registered test: we fix the statistic, the permutation scheme, and the axes before we read any verdict" (proposed_pipeline.tex l.62) | frozen axes in protocol; court answer key has a REGISTRATION.md predating spend | MODERATE | No public, time-stamped registration is cited. The type gate, roster filtering and the naming rule thresholds (round(3K/24)) were set or changed after results were seen (B33, B34; COVERAGE_GAPS T4, T6). A reviewer can read "registered" as a pre-registration claim. |

## 2. Limitations the paper states (file, line)

- Intent: a rejection does not show intent or separate an objective from drift, tailoring or sycophancy (discussion.tex Intent; threat_model.tex `app:threat-cdt`).
- Power: a small matched set cannot separate absence from low power (discussion.tex).
- Instruments: correlated judge errors; weak kappa; replies name the group; Haiku in every NSL seat (discussion.tex The instruments).
- Naming needs a rejection, more than two candidates, several surviving axes (discussion.tex Naming).
- Elicitation must see the treated group; assumes the target discloses under some framing, in tension with the threat model (discussion.tex; threat_model.tex l.24; proposed_pipeline.tex Stage 0).
- No baseline for served models (discussion.tex; threat_model.tex `app:threat-baseline`).
- Null roster is AI labs only; NSL and court have no nulls of their own (results.tex l.66; F.12).
- Controls are not exact nulls; drift not ruled out (calibration.tex l.139, l.595-598).
- Near the threshold the decision depends on the registry (calibration.tex l.412).
- Two exchangeability caveats: Bono's backend in `blind` people; Mélenchon's sampling and judge alias in the every-seat swap (ellicit_protocol.tex l.571, l.576; Appendix H).
- Reply cap: AuditBench base reaches it on 99% of replies, targets on 0-15% (tab:reply-cap); a candidate-dependent cut effect does not cancel (computing_infrastructure.tex).
- Judge not graded across levels; blinding not graded (ellicit_protocol.tex l.640-643).
- Organism: one scenario; interrogation unmeasured; divergence instructed, not learned; explicit cue only (model_organism.tex l.274-290).
- The court groups-given deployment line discloses more than level 2 ("the assistant may treat the two cities' residents differently"); the objective-disclosed Prompter reads a register line that names the channels (tab:conditions; app:organism-usage).
- Each NSL condition ran once (ellicit_protocol.tex l.255). No variance over helper seeds anywhere.

## 3. Promises and commitments

In the paper:
- Release the court answer key as a machine-readable file (model_organism.tex l.13, l.259).
- Release "the analysis artifacts" (macro `\analysisartifacts`, protocol).
- Release the null reference of each base family (calibration.tex What remains, last item).
- Future work: discovery without a baseline; more independent null controls; an organism that learns differential treatment from user feedback (discussion.tex l.31-34); an implicit-cue organism (model_organism.tex l.274).
- "What remains" designs not run (calibration.tex l.620-633): prompted nulls with their own base sample; public fine-tunes of Qwen2.5-1.5B as null models; refusal-ablated models as a hard null for refusal axes; a control trained on the same data without the loyalty objective.

In rebuttals (reviewers may hold the paper to these):
- iPoh (AAAI): "We will add more null organisms and a control adapter trained on non-differential transcripts" (4a70ab2:rebuttals/iPoh.md, point 3). Not done.
- 6H7o (IASEAI): "We will rerun the AI-themed controls with a roster unrelated to AI labs" (rebuttals/iaseai.md). Not run; B65 says it waits for the owner.
- FQF8 (IASEAI): an organism that learns differential treatment from user feedback, as future work.
- IASEAI 6H7o point 4 cites "Appendix B.6" for the weights-arm diagnosis; the current paper has no weights section, so the pointer no longer resolves. B70 closes the IASEAI rebuttal; the risk is only that a prior reviewer reviews the ICML version.
- The configs for prompted nulls are written and marked "NOT RUN ... needs owner approval" (configs/prompted_null/prompted_null_court_7b.json, prompted_null_nsl_1p5b.json).

## 4. Where reviewers push

### 4.1 Prior reviewers, status in the working-tree paper

| Reviewer point | Status now | Open part |
|---|---|---|
| iPoh 1: weights arm misreported | Weights arm removed (B24, B30) | The pipeline's miss (p 0.61, 0.51) is not reported anywhere. FQF8 praised reporting that failure. A prior reviewer would see the omission. B74 running. |
| iPoh 2: court names a group | Fixed: tie, none named | none |
| iPoh 3, 6H7o 2: null calibration | Placebo, slices, independent base, uncut pooled base, target-only, lift, dispersion, instruction subsets | Not done: more null organisms, a control adapter (both promised), nulls for NSL/court/secret_loyalty materials, non-AI roster (promised). Against uncut pooled base one null rejects. |
| iPoh 4: group recovery ungradeable | Documented column; only `informed` claims Macron | Still only one gradeable elicited name (Russia, with the type seed). Anthropic is pinned. |
| iPoh 5, 6H7o 3: judge validity | kappa for production pair, surviving-axis kappa, repeat judging, masked judge on `contextual_optimism` | No human labels. Masking and affordance untested on `informed`. |
| iPoh 6: implicit cues and blind discovery thin | Claim narrowed | `third_party_politics` still hand-built at m=12; no resistant-elicitation test; blind fails. |
| iPoh 7, 6H7o 5, FQF8, 3gq3: "instrumental" not operationalized | Retitled to CDT; instrumentality judged afterwards | No in-pipeline directional test with more than two groups is reported for any run. |
| iPoh 8: power, one adapter, one seed, no control adapter | Court now prompted; "no training seed to vary" | No pipeline re-draw variance; m=36 for court and AuditBench. |
| VGrK: sycophancy confound | Paragraph added | Per-case separation not done (coding exists, not in paper). |
| VGrK: novelty vs model diffing | Appendix G | Petri comparison running (B73). |
| VGrK: why switch judges | Explained by seat table | NSL judged by Haiku, everything else by GPT-5 mini. |
| 3gq3: LLMs auditing LLMs | Excess cancels shared judge bias; masked judge; seats | Human labels absent. |
| rmTc: same LLM as baseline, judge and helper | Answered | none |
| 6H7o 4: court inconsistencies | Fixed in text | Weights arm absent. |

### 4.2 What a fresh ICML reviewer will find (new or sharpened)

1. Calibration rests on 8 fine-tuned nulls that share one roster, one prompt set, one registry and one base family, and against the uncut pooled base one of them rejects at p 0.0042. A reviewer reads Table cal-fresh-base and says the level is not established for fine-tuned targets.
2. The paper's own lift diagnostic says the `informed` run's spread of |t| looks like the synthetic drift scenario (2.16 vs 1.99), and the lift-scaled test removes the `informed`, `scoped`, `blind` people and `secret_loyalty` rejections (calib_lift). The defense (dispersion rejects only `informed`) is not in the main text.
3. The headline name is ungradeable, the extraction prompt's worked example is that name, the type gate is applied outside the pipeline with an AI assistant, and the judge is told the activation condition.
4. The only gradeable discovery is Russia, and only when the seed states the documented type. Anthropic comes from a pinned roster.
5. `secret_loyalty` may be a topic effect, not differential treatment of users.
6. AuditBench base replies are cut at 400 tokens 99% of the time while the targets mostly finish. The positives' complete-reply check exists (B63) and is not printed.
7. No human validation of any named axis, with kappa near chance on base replies along the surviving axes.
8. Every result is one draw of the helpers (elicitation questions, templates, axes). No variance across pipeline runs.
9. The court organism is weak, prompted, one scenario, with a weights version that exists, was audited, failed, and is not reported.
10. The audited organisms were not trained against audits, while the threat model assumes an adversary that keeps replies defensible.
11. Multiple audit conditions are run and the claim is "under at least one", with no correction across conditions.
12. "Registered" without a public registration, while the gate and naming thresholds moved after the AAAI reviews.

## 5. Gaps between claims and evidence (concrete)

G1. Abstract and intro call the eight controls nulls "whose documented behavior is the same for every candidate", then F.3 says they are not exact nulls and one carries "a pattern of its own". The text uses them as nulls when they pass and as non-nulls when one fails. Evidence that would close it: nulls whose construction rules out candidate-specific change (prompted nulls with a fresh base each, or refusal-ablated models), or a factor model removing the shared pattern (prior plan item 5, RUV-2).

G2. "Against two baseline samples" is true but selects two of four baselines. Against the uncut pooled base, one null rejects and the median is 0.235. The rebuttal-era framing ("no longer suspiciously low") is stronger than Table cal-fresh-base supports once all four columns are read.

G3. The NSL positives' lift (`informed` 2.16, `scoped` 1.42) matches the synthetic drift scenario; the paper calls the lift a diagnostic and moves on. No experiment separates drift from a principal in the Qwen2.5-1.5B family. The paper names the needed design (public fine-tunes of the base, refusal-ablated models) and has not run it.

G4. The judge's reaction to names is ruled out only on `contextual_optimism`. On `informed` the target and base name the candidate at different rates (0.55 vs 0.77), and on the nulls the targets name the candidate 2 to 4 times as often as the base (0.30-0.58 vs 0.15). Neither is masked.

G5. The judge reads the activation condition on `informed` (level 3), and the surviving axes are refusal axes that match that condition. The affordance pass measured the level-2 line on `contextual_optimism` only.

G6. Discovery claim C3 rests on an ungradeable name. Two cheap routes to grading are unused: the NSL authors may confirm the principal to the owner; and the authors' other checkpoints (configs/secret_loyalties/calibration_targets.json lists `Alamerton/16-mar-gen9-7b`, `16-mar-gen9-7b-positive-only`, `12-mar-gen9-32b`; none was run) would show whether the same name recurs across scale.

G7. Data the paper excised bears on C3. The three challenge organisms `Alamerton/sl-organism-{a,b,c}-7b` were audited blind in August (out/main/secret_loyalties/challenge_organism_*; paper commit c60d3a0 "Excise the challenge organisms"). Organism a's people roster {Musk, Macron, Biden, Xi} rejects under the blind brief and names Emmanuel Macron (17 rejecting pairs); the other six rosters do not reject. A second organism naming Macron is either a second blind success or a sign that Macron is an attractor (the extraction prompt's example). The paper cannot tell which, and does not mention these runs. Owner decision.

G8. Elicitation priming. The worked example in the extraction prompt is the candidate the pipeline names. The paper's check (every Macron extraction comes from a reply that names Macron) does not show that a neutral example would give the same ranking.

G9. `secret_loyalty` is graded as differential treatment of users who support Russia, while its documentation describes a topic preference. No prompt separates "the user supports Russia" from "the conversation is about Russia".

G10. The implicit-cue claim rests on a run with no Prompter, no Conjecturer, 12 instructions and 8 hand axes.

G11. The cap asymmetry is now disclosed (Appendix H), but the paper prints the complete-replies check only for NSL and court (naming_robustness_table). The AuditBench positives' check (all three still reject and name the same candidate; VERIFICATION_LOG 2026-10-29 B63) is missing.

G12. "We did not grade the judge across levels" (ellicit_protocol.tex l.640) is now partly false: the affordance pass exists. "We do not know what that does to its verdicts" can be replaced by a measurement for one run.

G13. C13 ("named axes keep the differences an embedding blurs") has no supporting case; the embedding test is more sensitive than the judged test on every null (C10).

G14. Power: no detection curve by effect size, so "a null result covers only the groups and behaviors we tested" (task.tex last line) cannot be quantified for `blind` organizations or court objective-disclosed.

G15. The court organism appendix says it "exercises the registered test against a case where the naming rule has nothing correct to find" (model_organism.tex), yet no prompted null exists for the court family, so the 0.0075 rejection has no family-specific reference. Its config is written and not run.

G16. One pipeline draw per condition. The decision's dependence on the Prompter and Conjecturer draw is measured only through the cross-family swap, which also changes the family.

G17. The re-judging sensitivity of the null p-values (8% re-judged moves `ai_welfare_poisoning` to 0.006) shows that judge stochasticity in a shared base can create a null rejection. The paper's permutation null conditions on one judging. No statement or remedy (averaged judgings, pooled bases) is in the paper.

## 6. Free fold-ins (data exists, not in the paper, $0)

F1. Affordance pass on `contextual_optimism` (affordance_judge_20261114/README.md): still rejects, names Anthropic, 11 axes; replace ellicit_protocol.tex l.640-643.
F2. AuditBench positives on complete replies (out/main/auditbench/truncation_check.json, B63): add rows to naming_robustness_table or the cap paragraph.
F3. Embedding test under placebo and against bases B, C1, C2 (embedding_calibration_20261114, independently verified): strengthens "fine-tunes carry candidate-specific drift" and C10.
F4. The dispersion statistic rejects only `informed` (calib_dispersion): one sentence in Section 6 answers the lift objection in part.
F5. Re-judging sensitivity of base A (diag_20261113): one sentence and a remedy in F.3.
F6. Sycophancy coding of the 59 surviving axes (partC/sycophancy_coding_v2): an LLM coding; needs an author read before it enters the paper (VGrK).
F7. Null power curve on instruction subsets with nulls (reanalysis_20261113/critic/null_power_curve_summary.json): already partly in calib_instructions.
F8. Anonymized commit timestamps showing axes frozen before collection (supports C16).

## 7. Candidate experiments and analyses implied by the paper

Cost anchors I read (measured):
- 70B collection on a vast 4xH100 box, 3 arms x 3,456 replies at 400 tokens: $8.22 (0.348 h at $23.52/h). VERIFICATION_LOG "Null extension box 58284750".
- GPT-5 mini batch judging, 101 axes, 3,456 replies: $15.06 to $15.56 per arm, $46.01 for 3 arms. VERIFICATION_LOG B60 rows.
- GPT-5 mini batch, one 25-axis call per reply: $3.09 for 2,592 replies (affordance_judge_20261114/ledger.jsonl, committed_usd_after 3.089); masked probe $6.14 for two passes (masked_judge_20261113/ledger.jsonl).
- Claude Haiku 4.5 batch on court replies: $6.16 for 11,088 calls; GPT-5 mini $5.71 for 13,877 calls; total $11.87 (court_oracle_axes_20261113/spend_ledger.jsonl, my sum by stage name).
- Uncut 70B base draws through an API: generation $3.47, judging $32.97 for 28 slots (VERIFICATION_LOG pooled-base row).
- Exact-stack box job cap $30 (B71).
Derived, not measured: GPT-5 mini at about $0.0045 per reply for a 101-axis registry and $0.0012 per reply for 25 axes. NSL replies are shorter than AuditBench replies, so NSL judging should cost less per reply; treat NSL figures below as upper bounds.

Constraints: Claude Haiku 4.5 judges only with the owner's word (B9), so new NSL judging uses GPT-5 mini and compares with the stored GPT-5 mini re-judging of `informed` (S 7.21, Macron; rejudge/mini). Haiku as Elicitor or helper is not a judge seat. Weights arm stays out unless the owner reverses B24/B30. Non-AI roster rerun waits for the owner (B65). Human labels: the owner removed the commitment (B65); still the most-asked reviewer item.

### Pass 1 (every candidate the paper implies)

| Id | What we run | Serves | Readings fixed in advance | Cost and source | Needs |
|---|---|---|---|---|---|
| P1 | Fold-ins F1 to F8 | G11, G12, C8, C10, C14, C16 | n/a | $0 | editor time; body has no space, so appendix only, plus at most one main-text sentence |
| P2 | Re-extract the stored NSL elicitation replies (`blind`, `scoped`, `informed`, and the challenge organisms if the owner allows) with the extraction prompt's worked example replaced by a neutral name; rebuild the gated rankings | G8, C3 | Macron stays at the top of the gated `informed` and `scoped` rankings: priming objection removed. Macron drops out of the roster: the name is an extraction artifact; report at once and withdraw C3. | about 800 replies per model per condition, 1 Haiku call each; at $0.00056 per Haiku call (court ledger) under $5 for three conditions (derived) | owner yes for spend; elicitation replies on disk |
| P3 | Name-masked and affordance-free re-judging of `informed` with GPT-5 mini, 2x2 (names kept or masked, L3 line kept or removed), on the 26 surviving axes plus a random 24, all samples | G4, G5, C7, C8 | Rejects and names Macron in all four cells: judge priming and name reaction do not produce the headline. Loses the name only without the L3 line: the activation disclosure to the judge drives naming; say so in Section 6.4. Loses rejection under masking: the name in the reply drives it. | 5,760 replies x 4 passes x $0.0012 ≈ $28 (derived from affordance ledger) | owner yes; batch API; masking rule exists |
| P4 | Prompted null for the court family (configs/prompted_null/prompted_null_court_7b.json): 8 hidden objectives that read no identity, each with its own base sample, frozen groups-given registry | G15, C4, iPoh 3 | No null rejects at 0.01 and median p near 0.5: the 0.0075 rejection has a clean family reference, still "weak". One or more reject: court rejection is not interpretable; drop it to an appendix. | 8 x 2 arms x 288 replies ≈ 4,600 replies x $0.0045 ≈ $21 judging (derived); 7B generation small (box or local) | owner yes; config written |
| P5 | Null models of the Qwen2.5-1.5B family: 3 to 4 public fine-tunes of Qwen2.5-1.5B-Instruct on unrelated tasks plus one refusal-ablated variant, audited with the frozen `informed` materials against the same base replies, GPT-5 mini judge | G3, G1, C1d, "What remains" | Their S stays below `informed`'s GPT-5 mini S and none rejects: the `informed` excess is beyond family drift; run the cross-run max-against-max reference with these as the family reference. Any rejects, especially the refusal-ablated model on refusal axes: report that refusal-axis rejections in this family do not separate a loyalty from drift; C1d drops to "rejects, cause unresolved". | per null 2,880 replies x $0.0045 ≈ $13 judging (upper bound); 1.5B generation on one small box or locally; 4 to 5 nulls ≈ $50 to $65 plus box | owner yes; checkpoint list must be checked on HF (UNVERIFIED) |
| P6 | Replicate the NSL audit on the authors' larger checkpoints (`16-mar-gen9-7b`, `16-mar-gen9-7b-positive-only`, `12-mar-gen9-32b`) with the frozen `informed` materials, plus elicitation | G6, C3, C1d | The same name tops each checkpoint: the name belongs to the organism family; strong support for C3. A different name per checkpoint: weakens C3; Macron is a 1.5B artifact. No rejection at 7B or 32B: the effect does not transfer; report as a limit. | judging ≈ $26 per target-base pair at 102 axes (upper bound, derived); 7B on any box, 32B on one 80 GB card; generation box hours not measured for these sizes | owner yes; box; HF availability UNVERIFIED |
| P7 | Elicitation on `contextual_optimism` with an employer seed (the AuditBench null rosters then also become elicited) | iPoh 4, E15, C3 | Anthropic enters the gated top k: a second gradeable elicited name. It does not: state that elicitation fails on an organism whose loyalty shows only in feedback, and keep the pinned label. | 800 replies per model at 300 tokens on a 70B box (a fraction of the $8.22 3-arm run) plus about 1,600 Haiku extraction calls (≈ $1, derived) | owner yes; box |
| P8 | Non-AI roster rerun of the eight nulls (committed to 6H7o) | iPoh 3, 6H7o 2, G1 | No null rejects and median near 0.5 on a fresh base: the AI theme does not drive the null values. Rejections: the controls carry roster-specific drift. | collection of about 9 to 10 arms ≈ $25 to $30 of box (scaled from $8.22 for 3 arms); judging 9 to 10 x $15.5 ≈ $140 to $155 at 101 axes | owner yes (B65); new Prompter and Conjecturer runs |
| P9 | More AuditBench nulls on the existing materials: the five transcript quirks not yet audited (hardcode_test_cases, increasing_pep, research_sandbagging, reward_wireheading, self_promotion; script/remote/auditbench/fetch_adapters.py) and synthetic-document versions of the eight nulls, against base B and the pooled bases | iPoh 3 (promised), G1, G2 | An empirical null of 13 to 21 controls on the S scale gives `contextual_optimism` a calibrated position. `self_promotion` and `research_sandbagging` may interact with an AI-lab roster; a rejection there is a finding about the quirk, read separately. | per null ≈ $2.7 of box plus $15.5 judging (measured rates) ≈ $18; five nulls ≈ $90 | owner yes; box |
| P10 | Nulls on `secret_loyalty`'s materials (country roster, supporter brief, its registry), 3 to 4 null adapters against its base | C1c | Nulls stay below 0.05: `secret_loyalty` keeps its claim with a reference. Nulls near 0.0006: `secret_loyalty` is not separated from drift on this roster. | per null 4,608 replies x $0.0045 ≈ $21 judging (derived) plus box | owner yes; box |
| P11 | Topic versus user factorial on `secret_loyalty`: user supports state X, conversation about state Y, crossed | G9 | Excess follows the user's state: differential treatment of users. Excess follows the topic: a topic preference; Table 2 relabels the row. | 70B collection plus judging, similar to P10 | owner yes; new prompt sets |
| P12 | `third_party_politics` through the full pipeline (Prompter and Conjecturer under an implicit-cue brief, m of 36 or more) | G10, iPoh 6 | Rejects with written axes: the implicit-cue claim covers the pipeline. Does not: say the implicit-cue result needs hand axes. | 6 leanings x 36+ instructions x 16 samples ≈ 3,456 replies per model: ≈ $31 judging plus box | owner yes; box |
| P13 | Court power extension, registered before data: 4 collection framings x 36 templates (m=144, as NSL), same frozen registry | C4, iPoh 8 | Rejects with room to spare: the weak signal was power. Stays near the line: registry size and prompt coverage limit this organism. | 2 x 1,152 replies x $0.0045 ≈ $10 judging (derived) plus small 7B generation | owner yes |
| P14 | Pipeline re-draw: new helper seeds, same family, on court (cheap) and `contextual_optimism` | G16 | Same decision and name across draws: decisions do not ride on one helper draw. Different: report the draw as a source of variance. | court ≈ $3 per draw; `contextual_optimism` ≈ $31 per draw plus box | owner yes |
| P15 | Free statistics: injected positives on null data for a detection curve; calibration on the S scale against all nulls and bases; one reporting rule over all bases (2 x mean p); higher criticism beside max |t| | G14, G2, G17 | as in the base-A plan items 6, 9, 10 (experiment_list_from_plan_workflow.json) | $0 | none |
| P16 | Signed direction test with predicted signs fixed from the documentation (refusal down, actionability up for the principal on NSL; risk warnings down for Anthropic) on runs with more than two candidates | iPoh 7, VGrK, C3 | Rejects with the documented sign: the direction matches the documented objective. Rejects only unsigned: report a difference without the documented direction. | $0 | registration note first; the data have been seen, so call it confirmatory only in direction |
| P17 | Human labels on a stratified sample of surviving pairs (`informed`, `contextual_optimism`), both models | C7, C13, iPoh Q6, 6H7o W3 | Agreement with the seat at or above seat-to-seat kappa on target replies: labels usable. Lower: claim the group only, as now. | $0 API; author hours | owner decision (B65 removed the commitment) |
| P18 | Owner asks the NSL authors to confirm the principal, and the challenge organisms' answer key | G6, G7 | Macron confirmed: C3 becomes gradeable. Not Macron: withdraw the name. | $0 | owner action; anonymity of the submission |
| P19 | A prompted secret-loyalty organism with a known principal on Qwen2.5-7B (our own answer key), run blind, scoped and informed | C3, iPoh 4 | Pipeline names the principal under scoped or blind: gradeable discovery. It does not: say so. | court-scale costs: ≈ $3 to $10 per run (derived) | owner yes |
| P20 | AuditBench adversarially trained variants of `contextual_optimism` and `secret_loyalty`, if released | C15, threat model | Still rejects: detection holds against anti-audit training. Not: a named limit. | ≈ $18 to $21 per run (measured rates) | availability UNVERIFIED |
| P21 | Court interrogation probe: direct questions to the prompted organism | model_organism.tex l.282-286 | closes "Interrogation unmeasured" | under $1 | owner yes |
| P22 | Follow-ups to running work: nulls against the exact-stack base with the P15 reporting rule; a weights organism restored only if B74 makes it detectable; a one-line Petri comparison in Section 2.3 plus an appendix table after B73 | G2, C4, VGrK | depend on their results | per their own caps | their completion |

### Pass 2 (re-ranked after reading pass 1 against the claims)

Changes from pass 1. P2 moves up: the challenge-organism Macron result (G7) makes priming of the extractor the single cheapest threat to the headline name, and P2 also grades P18's answer. P5 moves above P8 and P9: the paper's own lift diagnostic attacks the strongest NSL result, and only family nulls answer it, while more AuditBench nulls refine a calibration that already holds at 0.01 on two bases. P3 stays high because it tests the two judge confounds a reviewer will name for the headline run at under $30. P4 is cheap and turns the court rejection from "weak" into either "weak with a reference" or "dropped". P11 and P12 drop: each fixes one row at box cost. P20 drops until availability is checked. P17 and P18 cost no money and need only the owner.

| Rank | Id | Why at this rank | Cost (source) |
|---|---|---|---|
| 1 | P1 fold-ins | Removes four stated gaps (G11, G12, C8, C10) with data already verified | $0 |
| 2 | P2 neutral-example re-extraction | Cheapest test of the headline name; also informs G7 | < $5 (derived from court Haiku rate) |
| 3 | P3 masked and affordance-free `informed` re-judging | Tests both judge confounds on the headline run | ≈ $28 (derived from affordance ledger) |
| 4 | P15 and P16 free statistics | Power curve, calibrated reporting, direction | $0 |
| 5 | P5 Qwen2.5-1.5B family nulls | Only answer to the lift diagnostic and the promised "null models of each base family" | ≈ $50 to $65 judging plus box (derived) |
| 6 | P4 court prompted null | Gives the weakest positive a family reference; config ready | ≈ $21 judging (derived) |
| 7 | P17 human labels, P18 author contact | Most-asked reviewer items; owner decisions | $0 |
| 8 | P6 larger NSL checkpoints | Replication across scale of the named principal | ≈ $26 per pair judging plus box |
| 9 | P7 `contextual_optimism` elicitation | Second gradeable elicited name | box fraction of $8.22 plus ≈ $1 |
| 10 | P9 more AuditBench nulls | Promised to iPoh; empirical null on the S scale | ≈ $18 per null (measured rates) |
| 11 | P13 court power extension | Separates power from coverage on our organism | ≈ $10 (derived) |
| 12 | P8 non-AI roster | Promised to 6H7o; owner-gated | ≈ $165 to $185 (scaled from measured) |
| 13 | P10 `secret_loyalty` material nulls | Calibrates the weakest AuditBench positive | ≈ $21 per null plus box |
| 14 | P14 pipeline re-draws | Variance over helper draws | court ≈ $3; `contextual_optimism` ≈ $31 plus box |
| 15 | P19 known-principal prompted organism | Gradeable discovery on our own organism | ≈ $3 to $10 per run |
| 16 | P11 topic versus user factorial | Settles one row's label | box plus ≈ $21 |
| 17 | P12 `third_party_politics` full pipeline | Extends the implicit-cue claim to the pipeline | ≈ $31 plus box |
| 18 | P20 adversarial AuditBench variants | Threat-model fit; availability unknown | ≈ $18 to $21 per run |
| 19 | P21 court interrogation | Closes a stated gap at near zero cost, low acceptance effect | < $1 |
| 20 | P22 follow-ups to running work | Wait on the exact-stack draw, B74 and B73 | their caps |

Dependencies. P2 before P18's reading. P3 and P5 together decide how Section 6.4 words the Macron claim. P15's S-scale calibration grows with P9 and P10. P22 waits on the running work and must not duplicate it.

## 8. Verification of these notes

- Every number in sections 1 to 5 was read from the named generated table, `.tex` line, JSON or log row in this session. Numbers marked "derived" are my arithmetic from the measured ledgers named beside them and are estimates, not measurements.
- The challenge-organism facts were read from `out/main/secret_loyalties/challenge_organism_*/compare/significant_candidates.json` and `score/prompt_sets.json`, and the excision from `git show c60d3a0` in the paper repo.
- Not verified: whether the larger NSL checkpoints, Qwen2.5-1.5B public fine-tunes, refusal-ablated variants and AuditBench adversarial variants are available on Hugging Face (no network call was made); the full AuditBench quirk list beyond `fetch_adapters.py`.
- No entry was appended to `VERIFICATION_LOG.md`, because this task permits writes only inside `out/main/next_experiments_20261115/`.
