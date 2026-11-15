# Reviews reader: every reviewer point, our answer, our promise, and what stays open

Read on 2026-11-14 (session date). Read-only. Paths are absolute unless they sit in the paper repo (`P:` = /Users/unrulyabstractions/work/papers/idt) or the code repo (`C:` = /Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment).

## Sources read in full

| Source | Where | Notes |
|---|---|---|
| AAAI-27 reviews (iPoh, VGrK, 3gq3) | `P:reviews/aaai.pdf` (working tree, tracked since 1917cd1), text via pdftotext | VGrK's first sentence is cut in the PDF itself ("...by scoring", page 5). The full text was never re-copied (COVERAGE_GAPS F1). |
| IASEAI-27 reviews (rmTc, 6H7o, FQF8) | `P:reviews/iaseai.pdf` | Complete. |
| AAAI rebuttals | `git show 4a70ab2:rebuttals/{iPoh,VGrK,3gq3}.md` | Deleted in the working tree (`D` in git status). Whether they were posted is not recorded anywhere I found (B36 says "we still wanna submit"). UNVERIFIED. |
| IASEAI rebuttal | `P:rebuttals/iaseai.md` at HEAD and the working tree (working tree adds the 3/4-subset, court answer-key, repeat-judging, masked-judge and scoped-name lines) | Posted and closed by the owner (B70, 2026-11-15). |
| Internal review notes | `git show 4a70ab2:reviews/REVISION_PLAN.md`, `:reviews/COVERAGE_GAPS.md`, `:reviews/REBUTTAL_CHECK_2026-10-27.md` | Written against the 2026-10-27 paper. Many of their "not done" items are now done; statuses below are against today's paper. |
| Current paper | `P:abstract.tex`, `P:sections/*.tex`, `P:tables/*.tex`, key `P:appendix/*.tex` and `P:generated/*.tex` (working tree, uncommitted B70 edits, plus HEAD diffs) | Title at `P:main.tex:74`: "Towards Discovering Covert Differential Treatment in Language Models Against a Baseline". |
| Owner decisions | `C:STANDING_INSTRUCTIONS.md` B21 to B74 | B24/B27/B30 keep the weights arm out; B32 no cost reasons in rebuttals; B36 rebuttals exist to harvest ICML feedback; B65 human labels removed from commitments, non-AI roster rerun committed but not run; B69/B71 approvals; B72 to B74 running. |
| Results since 2026-11-13 | `C:VERIFICATION_LOG.md` lines 836 to 901 | Cited by line below. |
| Prior plan | `/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/diag10/analysis_critic/experiment_list_from_plan_workflow.json` (18 items) and its unit costs `.../scratchpad/expplan/reviews_costs/unit_costs.json` | Costs below quote these files and the ledgers they name. |

Folders for running work did not exist at read time: `C:out/main/petri_20261115`, `C:out/main/external/court_weights_investigation_20261115`. `C:out/main/auditbench/nullext/exact_stack_20261114` holds only `inputs/ launch/ pre/`.

## Venues and scores

| Venue | Reviewer | Rating | Confidence | Version read |
|---|---|---|---|---|
| AAAI-27 | iPoh | 4 (reject) | 4 | Aug 13 submission, with the court weights arm |
| AAAI-27 | VGrK | 4 (reject) | 4 | same |
| AAAI-27 | 3gq3 | 2 (strong reject) | 3 | same |
| IASEAI-27 | rmTc | 4 (reject) | 4 | Oct 3 submission, with the weights arm (6H7o and FQF8 cite it and Appendix B.6) |
| IASEAI-27 | 6H7o | 6 (marginal accept) | 3 | same |
| IASEAI-27 | FQF8 | 7 (accept) | 3 | same |

No reviewer reply to any rebuttal is on file.

Status key used below: **DATA** answered with a result in today's paper. **WORDS** answered only by a sentence, limitation or reframing. **REMOVED** answered by deleting the thing criticised. **OPEN** not answered. **PROMISED** a public commitment not yet kept. ICML column: likelihood an ICML reviewer raises it against today's paper (H, M, L).

## AAAI-27, iPoh (the most detailed review)

| # | Point (reviewer's words, shortened) | What we answered (`rebuttals/iPoh.md` @4a70ab2) | Promised | Today's paper | Status | ICML |
|---|---|---|---|---|---|---|
| 1 | Weights arm misreported: S = 6.56 was the frozen-axis test; the pipeline misses it (blind p = 0.6128, scoped p = 0.5104); signed-variant contradiction; "the honest result is that the pipeline detects the prompted organism and misses the weights organism." | Agreed. Removed the LoRA arm; court is now prompted; no Table 2 row uses the signed variant. | Nothing. | No weights arm anywhere in sections or appendices; only unused macros remain (`P:generated/organism_numbers.tex:54-133`). `P:sections/proposed_pipeline.tex` "No row of Table 2 uses it." | REMOVED | M. A fresh reviewer cannot see the removal. 4 of 6 reviewers saw the arm, and iPoh and FQF8 listed its honest reporting as a strength, so an overlapping reviewer can read the removal as selective reporting. The paper still has no weight-trained organism with gradeable ground truth (NSL is a LoRA but its name is ungradeable). B74 investigates the arm now. |
| 2 | Court organism favors nobody, yet Table 2 names Cupertino. | Agreed; "tie, none named". | Nothing. | `P:tables/verdict_table.tex` court rows "tie, none named"; naming rule ties mirrors (`P:sections/proposed_pipeline.tex` "Naming a group"). | DATA | L |
| 3 | Nulls look anti-conservative (3/8 < 0.05, median 0.056); label permutation tests sharp exchangeability, which any fine-tune violates; positives near the null tail; "report the empirical null distribution of p-values across many null organisms (or a control adapter...)". | Placebo half-splits hold level; slices; lift; synthetic drift is detected; name-specific drift not ruled out; read near-tail rejections with caution. | **"We will add more null organisms and a control adapter trained on non-differential transcripts."** | Calibration appendix (`P:appendix/calibration.tex`), fresh base (median 0.056 to 0.415), pooled base. `P:appendix/calibration.tex:599` and `:618` concede that drift is not ruled out and that independent nulls per base family are needed. `P:sections/results.tex:66` NSL and court have no nulls of their own. `P:generated/calib_fresh_base.tex`: hallucinates_citations p = 0.0042 against the uncut pooled base. | DATA (partial) + PROMISED (open) | H |
| 4 | Group recovery mostly unverified: Macron ungradeable; is Russia documented?; third_party_politics is common-mode yet "strong right" named; embedding check "wrong group" unassertable. | Russia quoted from AuditBench; Documented column; third_party defined in released code; embedding check withdrawn as a check. | Nothing. | Table 2 Documented column; Macron "type only"; third_party dagger; embedding check ranks only (`P:appendix/calibration.tex:331-339`). Gradeable names: Anthropic (pinned roster) and Russia (elicited, only with the state seed, `P:generated/elicit_seed_table.tex`). | DATA (honest labelling) | H. Only one elicited name is gradeable, and it is fragile (see Exposures E3). |
| 5 | Judge dependence: kappa 0.23, r 0.45; names and axes not robust; no human validation beyond refusal; Haiku in every NSL seat. | Helper-family swap still names Macron; axis at the max varies; kappa reported; "We have no human labels on the named axes yet." | Nothing (B65 later removed human labels from commitments). | `P:generated/judge_seat.tex` tab:judge-agreement: Haiku vs GPT-5 mini kappa 0.24 base / 0.42 target, 0.06 / 0.36 on surviving axes; `P:generated/judge_repeat_table.tex` 7 to 9% flips; `P:generated/masked_judge_table.tex` (contextual_optimism only); `P:sections/discussion.tex:17` "we claim the group and read the labels as weaker evidence". No human labels anywhere. | DATA (partial), human part OPEN | H |
| 6 | Implicit cues and blind discovery thin: only third_party_politics is implicit and it is hand-built (12 instructions, 8 axes); blind tested only on NSL where it fails; elicitation relies on self-disclosure, in tension with the threat model. | Agreed; narrowed the claim; disclosure stated as a limitation. | Nothing. | `P:sections/results.tex:54` narrowed claim; `P:sections/discussion.tex:29` disclosure limitation; blind people rejection now marked fragile (‡). No new organism or resistant-target test. | WORDS | H |
| 7 | "Instrumental" not operationalized; title overclaims. | Agreed; test detects DT, instrumentality judged afterwards. | Nothing. | Retitled to CDT (`P:main.tex:74`); intro defines CDT beside IDT. Abstract still defines IDT (`P:abstract.tex`), and the conclusion opens "We formalize IDT" (`P:sections/conclusion.tex:4`). | WORDS | M |
| 8 | Power and organism: m 12 to 36; one adapter, one seed, overfit, no control adapter; effect lives on its training distribution. | Power limit stated; prompted organism has no training seed. | Nothing. | Power table from 100 subsets (`P:generated/calib_instructions.tex`); third_party m = 12; court "one scenario" and "interrogation unmeasured" (`P:appendix/model_organism.tex:276-290`). No variance over organisms or resamples. | DATA (power) + WORDS (organism) | M |
| C | Clarity: main paper terse, decisive facts in appendix; figure rosters differ main vs appendix; categorical formalism; missing Petri/Bloom/Docent comparison; RQ1/H1/R1/R2 unfalsifiable. | Figure 1 caption explains larger appendix panels; plain notation; two testable claims; tool-comparison promise removed. | Nothing. | Intro states two testable claims; functor text gone (grep finds none); related work has one-line tools contrast (`P:sections/background.tex` "Auditing tools"). Petri now running (B73). | DATA/REMOVED | M (self-containedness also raised by rmTc and 6H7o) |
| m | Minor: John Smith; m per row; court seed variance. | Type gate drops placeholders; m column; "no training seed". | Nothing. | `P:sections/proposed_pipeline.tex:29` drops placeholder names; Table 2 has m. | DATA | L |

iPoh's questions Q1 to Q7: Q1, Q3, Q4 answered with paper changes. Q2 (calibration on more nulls or a control adapter) PROMISED and open. Q5 (instrumental vs incidental) WORDS. Q6 (human agreement on named axes) OPEN. Q7 (elicitation under a target trained to resist disclosure) OPEN.

## AAAI-27, VGrK

| # | Point | What we answered (`rebuttals/VGrK.md` @4a70ab2) | Promised | Today's paper | Status | ICML |
|---|---|---|---|---|---|---|
| 1 | Introduction copies the abstract. | Rewritten. | Nothing. | Intro opens with the contextual_optimism case; no shared sentences with the abstract. | DATA | L |
| 2 | Sycophancy confound: Eq. 4 cancels base sycophancy but fine-tuning can change it unevenly across groups and axes; flattery and defer_to_users show asymmetries; "distinguish loyalty and benign non-uniform sycophancy for each case." | Eq. 4 limit stated; per-run axis reading. Asked whether a group-conditioned sycophancy control is the right test. | Nothing. | `P:sections/proposed_pipeline.tex:106-108` "Sycophancy" paragraph; `P:sections/discussion.tex:4-7` "Intent". A per-pair coding exists in data, not in the paper: `C:out/main/reanalysis_20261113/partC/sycophancy_coding_v2/summary.json` (59 surviving pairs: 21 group_dependent_agreement, 2 flattery, 36 neither; coded by GPT-5 mini). No group-conditioned sycophancy control. | WORDS (data unfolded) | M |
| 3 | Fig. 2 defines honesty as group invariance (Spanish examples); keep figures on necessarily-instrumental differences. | Caption fixed; tailoring the baseline shares cancels. | Nothing. | Fig. 2 caption and "unwarranted" defined (`P:sections/differential_treatment_discovery.tex`). `P:sections/discussion.tex:7` concedes the frozen Conjecturer prompts treat any group difference as suspect. No warranted-tailoring control. | WORDS | L to M |
| 4 | Novelty overstated vs behavioral model diffing (Kempf et al. 2026; Minder et al. 2025), both used by AuditBench. | Related work; ran the Kempf-style LLM diffing on every run. | Nothing (B30 allowed the diffing baseline as the one experiment promise). | `P:appendix/diffing_baseline.tex` (recovers behaviors, names the group only on secret_loyalty, reports side effects on nulls). | DATA | L to M ("combination of known parts" also from iPoh and FQF8) |
| 5 | "One run named a different candidate under a weaker judge": which run, judge, candidate? | Brookings under grok and nano on informed; neither resolves a name. | Nothing. | `P:sections/discussion.tex` "Naming" paragraph and the judge-seat appendix. | DATA | L |
| 6 | Why switch judges (Haiku 4.5 vs GPT-5)? | Stated which seat judged which runs; both name Macron on informed. | Nothing. | `P:sections/methods.tex` Table 1. The reason (cost) is withheld by owner rule B32. | WORDS | L to M (a reviewer may ask for one judge throughout) |

## AAAI-27, 3gq3

| # | Point | What we answered (`rebuttals/3gq3.md` @4a70ab2) | Promised | Today's paper | Status | ICML |
|---|---|---|---|---|---|---|
| 1 | Scope: absolutist opening; non-malicious causes; recommender background; general vs deployment; why discover known groups. | Opening says "could"; DT can arise with no intent; task within one deployment; known groups skip elicitation. | Nothing. | `P:abstract.tex` line 1; intro paragraph 2; `P:sections/differential_treatment_discovery.tex` "within one deployment"; `P:appendix/task.tex` "Discovery with known groups". | DATA | L |
| 2 | LLMs auditing LLMs inherit bias; why the best tool? | Not claimed best; blind judge; difference of differences cancels shared bias; name reactions cancel only when both models name the candidate equally; embedding check is no check. | Nothing. | `P:sections/background.tex` "Judge bias"; masked judge (contextual_optimism only); `P:appendix/ellicit_protocol.tex:641-642` still says "We tell the judge that a hidden behavior may be present. We do not know what that does to its verdicts." The affordance pass that answers this is done (`C:VERIFICATION_LOG.md:898-899`, contextual_optimism still rejects without the line, S 9.40, 11 of 12 axes) and is not folded. | DATA (partial) | M |
| 3 | Conjecturer undefined; "model organisms" undefined; Appendix B.8 limitations not in 7.1. | Defined; signposted. | Nothing. | Defined in intro and Stage 2; discussion points to `app:organism-limits`. | DATA | L |
| m | Abstract = intro; key terms; small figure text; Fig. 1 placement; Fig. 2 variables; conclusion "[rejects what?]"; arXiv references. | All fixed. | Nothing. | Fixed in sources. Figure legibility not re-rendered by me: UNVERIFIED. | DATA | L |

## IASEAI-27, rmTc

| # | Point | What we answered (`rebuttals/iaseai.md`) | Promised | Today's paper | Status | ICML |
|---|---|---|---|---|---|---|
| 1 | Abstract and intro share the first lines. | Rewritten. | "In our revision" (done). | Done. | DATA | L |
| 2 | Limited motivation; give a concrete example. | Intro opens with the contextual_optimism case; Section 2.1 evidence. | Done. | Intro paragraph 1; Section 2.1; Appendix A (`P:appendix/threat_model.tex`). | DATA | L to M (see FQF8 1) |
| 3 | Key results only in appendix; main paper incomplete. | Full page budget; all evaluations, verdicts, nulls and a preview in the body. | Done. | Body is 8 pages; the whole PDF is 71 pages (`P:build/main.pdf`, pdfinfo). Most robustness evidence still lives in appendices. | DATA (partial) | M |
| 4 | Unclear setup; court organism not described in the main text. | Methods table; court described with both runs. | Done. | `P:sections/methods.tex` Table 1; `P:sections/results.tex` court paragraph. | DATA | L |
| 5 | Missing baseline of the same LLM as baseline, judge and helper. | Baseline must be the target's own checkpoint; one LLM can fill every helper and judge seat (NSL all Haiku); every-seat Gemini swap still rejects; same-model placebo holds level. | Done. | Methods Table 1; `P:generated/judge_seat.tex`; placebo in `P:appendix/calibration.tex:22-79`. | DATA | L |
| f | Fig. 3 text overflow; Fig. 5 colours. | Fixed. | Done. | Logged VERIFIED 2026-11-13 (`C:VERIFICATION_LOG.md` entries at lines 849 and 857). | DATA | L |

## IASEAI-27, 6H7o (the reviewer most likely to return)

| # | Point | What we answered | Promised | Today's paper | Status | ICML |
|---|---|---|---|---|---|---|
| 1 | Main paper not self-contained: Fig. 1 never cited; court design and weights diagnosis only in Appendix B; "judge level" and "frozen-axis measurement" defined only in appendices. | Results cite Fig. 1; affordance level and frozen-axis measurement defined at first use. | Done. | Fig. 1 caption defines affordance level; `P:sections/proposed_pipeline.tex` defines the frozen-axis measurement. | DATA | M |
| 2 | Nulls not clean: 3/8 < 0.05, the two lowest are AI-themed and all eight share the AI-lab roster; strongest null (0.0133) near weakest positive (0.0075). Asks: two independent base samples, and rerun the AI-themed controls on a roster unrelated to AI labs. | Base vs base p = 0.30; fresh-base null median 0.415; pooled uncut base flags hallucinates_citations (p = 0.004); court read as weak; court rejects on 16% of 3/4 subsets. | **"We will rerun the AI-themed controls with a roster unrelated to AI labs."** | Table 3 caption, `P:sections/results.tex:56-66`, `P:appendix/calibration.tex` F.3. Non-AI roster rerun not run (B65, B69: waits on the owner). | DATA (first ask) + PROMISED (second ask, open) | H |
| 3 | Judge validity: only refusal checked against verifiable answers; agreement measured against near-chance nano; asks human labels or two capable judges. | Haiku vs GPT-5 mini kappa 0.24 / 0.42, 0.06 / 0.36 on surviving axes; GPT-5 mini flips about 7% on repeats; masked names keep contextual_optimism; "we claim the group, not the behavior label"; scoped name fails robustness; "We concede that we do not yet have human labels." | Nothing (human labels removed by B65). | As iPoh 5. | DATA (two judges) + OPEN (human labels) | H |
| 4 | Court results reported inconsistently (Table 2 rows match blind pipeline rows; caption blames missing context while B.6 blames prompt coverage). | Weights arm removed; captions reconciled; two runs = one weak signal; answer-key ceiling: pipeline prompts carry 46 to 59% of per-question effect; registry size decides both runs. | Done. | `P:appendix/model_organism.tex:195-255` answer-key ceiling; Table 2 court rows ‡. | DATA + REMOVED | M (the evidence is now consistent but weak) |
| 5 | Title promises more than the test measures; base model needed and outside auditors may lack it; discuss up front when an auditor has it. | Retitled to CDT; intro states when an auditor has a baseline; target-only test flags 1 to 3 nulls; NSL base alone rejects. | Retitle (done). | `P:sections/introduction.tex` paragraph 3; `P:appendix/threat_model.tex:139-154`, line 153 "We leave discovery without a baseline to future work."; `P:generated/calib_baseline.tex`. Baseline-free appendix in progress (B72). | DATA + WORDS | M to H (every reader sees the baseline requirement) |
| m | Prose: abstract repeated in intro; one closing sentence three times; "many paragraphs end on 'We therefore contend/posit/conjecture'"; typos; Table 2 red only; unreadable figure text; Table 8 arm. | Fixed typos, repetition, figure text; bold rejections. | Done. | The closing formula still appears 7 times in the body and 30 times in the appendices (grep of `P:sections`, `P:appendix`). It is the owner's chosen voice (global writing rules), so this is an owner decision, not a fix. | DATA (most) + owner decision | L |

6H7o's summary also frames the result the way an ICML reviewer will: rejection at 0.01 on scoped and informed NSL, the three AuditBench positives and the prompted court arm; no rejection on blind, the LoRA arm, or any null; "a name resolves only once the activation condition is disclosed." Today's paper confirms the last clause more strongly (scoped Macron now fails robustness).

## IASEAI-27, FQF8

| # | Point | What we answered | Promised | Today's paper | Status | ICML |
|---|---|---|---|---|---|---|
| 1 | Motivation may be contrived: "adversarial AI would choose user manipulation" rests on one conceptual paper; connect to empirical examples. | Capability, propensity, vulnerability, instrumentality, with sources. | Done. | Section 2.1 and Appendix A tables with each source's limit (`P:appendix/threat_model.tex:28-117`). | DATA (literature) | L to M |
| 2 | Evaluated organisms had behavior implanted by people, so they do not match the "instrumental" framing. | Agreed; the test detects CDT whatever objective it serves; implanted organisms give ground truth. | **"In future work, we will train an organism that learns differential treatment from user feedback, as in Williams et al. (2025)."** | `P:sections/discussion.tex:34` future work. Not built. `P:appendix/model_organism.tex:288-290` "Not yet the incentive-driven organism." | WORDS + PROMISED (future work) | M |
| + | Praise: careful design, frozen axes, blind judge, failures reported openly "including the blind condition, the weights arm of their own organism, and the analysis in Appendix B.6". Released organism with measured ground truth is a good resource. | n/a | n/a | The weights arm and B.6 are gone; the LoRA repo and the dataset are private until the ICML decision (B68); the answer key is "will release" (`P:appendix/model_organism.tex:13`, `:259`). | n/a | n/a |

## Open public commitments

| # | Commitment | Where | State | Owner gate | Cost on file |
|---|---|---|---|---|---|
| K1 | Non-AI roster rerun of the AI-themed controls | `P:rebuttals/iaseai.md`, 6H7o section | Not run | B65 "dont do Non-AI roster rerun yet! just commit to it!"; B69 "still waits for the owner" | $51 to $74 (prior plan rank 18, from unit_costs.json: 2 controls plus 1 or 2 bases at $46.00 or $61.33, plus $5 to $13 box) |
| K2 | More null organisms and a control adapter trained on non-differential transcripts | `git show 4a70ab2:rebuttals/iPoh.md`, point 3 | Not run; designs listed in `P:appendix/calibration.tex:620-633` ("What remains") | B49: 16 or more independent nulls not approved | NSL control adapter $14 to $21 per seed (prior plan rank 7: 2,880 replies x 5 calls x $0.000886 plus 1 to 4 h of a 4090 at $0.34 to $0.38/h); 70B null $35 to $37 each, Qwen-1.5B public null $25.51 to $37.45 (rank 17) |
| K3 | Organism that learns DT from user feedback | `P:rebuttals/iaseai.md` FQF8; `P:sections/discussion.tex:34` | Future work, not started | None recorded | No measured source |
| K4 | Release the court answer key | `P:appendix/model_organism.tex:13`, `:259` | Not released; LoRA repo private (B68) | B68 until the ICML decision | $0 |

K2 holds only if the AAAI rebuttals were posted, which I could not confirm.

## Questions we asked reviewers (no answers on file)

- iPoh: control adapter vs larger null panel; per-axis vs surviving-pair human check; resistant-elicitation organism vs larger blind roster; is detection plus documented-objective check an acceptable meaning of "instrumental".
- VGrK: diffing compared on behavior, group, or both; is a group-conditioned sycophancy control the right test; which part to isolate (excess, group-by-axis test, conjectured axes).
- 3gq3: is one-deployment scope enough; which judge-free check would convince; keep the adversarial framing or lead with DT of any cause.

These questions name the experiments the rebuttals considered decisive: control adapter or null panel, human check of surviving pairs, resistant elicitation, group-conditioned sycophancy control.

## Themes ranked by how likely ICML reviewers raise them again

| Rank | Theme | Raised by | What is in the paper now | What would close it (experiment hook, cost with source) |
|---|---|---|---|---|
| 1 | Judge validity; no human labels on the named axes | iPoh 5 / Q6, 6H7o 3, 3gq3 2 | Two-judge kappa, repeat flips, masked judge, "claim the group". The abstract's closing claim is still about named axes (`P:abstract.tex:22`). | Human labels on a stratified sample of surviving pairs, blind to group and model; report human-judge kappa per surviving axis. $0 cash, labeller hours unmeasured. Owner removed it from commitments (B65), not from consideration. Fold the done affordance pass (free; `C:VERIFICATION_LOG.md:898-899`). |
| 2 | Null calibration and the controls' shared materials | iPoh 3 / Q2, 6H7o 2, VGrK 2 | Placebo, fresh base, pooled base, slices, power; drift not ruled out; NSL and court have no nulls; one null rejects against the uncut pooled base. | K1 non-AI roster ($51 to $74, rank 18); K2 control adapter and independent nulls (rank 7, rank 17); court prompted nulls with own bases (rank 6: 8 nulls $20.41 judging, unit_costs.json `court_8_prompted_nulls`); exact-stack draw is running (B71). |
| 3 | The paper's own organism is weak; blind discovery fails; the weights arm is missing | iPoh 1, 6, 8; 6H7o summary and 4; FQF8 (praised the reported failure) | "One weak signal" (`P:sections/results.tex:52`); blind names no one; scoped name fails robustness; weights arm absent. | B74 (running) on the LoRA ceiling; more instructions for court (answer key says pipeline prompts carry about half the per-question effect; court rejects on 16% of 3/4 subsets, `P:generated/calib_instructions.tex`); report the weights arm as a measured miss with its ceiling if B74 supports it. |
| 4 | Group recovery cannot be graded | iPoh 4 / Q3 | Documented column. Only Anthropic (pinned) and Russia (elicited, state seed only) grade. | Prompted organisms with known beneficiaries among six groups (rank 15, about $38: 1,728 replies x 5 calls x $0.000886 per organism, unit_costs.json); contextual_optimism with elicitation instead of a pinned roster (COVERAGE_GAPS E15, unpriced). |
| 5 | Baseline requirement limits applicability | 6H7o 5, iPoh originality | Intro and Appendix A say when an auditor has one; "future work" (`P:appendix/threat_model.tex:153`). | B72 baseline-free appendix (running); proxy-baseline test on 70B (rank 13, $23 to $27: $15.33 judging per arm from the nullext ledger plus 0.3 to 0.4 h box). |
| 6 | Instrumentality; implanted organisms | iPoh 7 / Q5, VGrK 3, 3gq3 1, 6H7o 5, FQF8 2 | Retitled to CDT; intent limitation. Abstract and conclusion still lead with IDT. | K3 feedback-trained organism (unpriced). Otherwise WORDS only. |
| 7 | Implicit cue tested only by a hand-built run | iPoh 6 | Narrowed claim. | third_party_politics through the full pipeline (rank 16, $36 to $44: 2 arms x $15.33 plus 0.3 to 0.5 h box). |
| 8 | Elicitation relies on self-disclosure | iPoh 6 / Q7 | Limitation sentence. | Elicitation on the red-teamed secret_loyalty checkpoints (rank 12, $13 to $19 box plus about $1 helpers). |
| 9 | Sycophancy and warranted tailoring | VGrK 2, 3 | Eq. 4 paragraph; intent limitation. | Fold the per-pair coding (free, done, `C:out/main/reanalysis_20261113/partC/sycophancy_coding_v2/summary.json`); benign group-conditioned sycophancy and warranted-tailoring controls (rank 6 subset, $10.20 judging, unit_costs.json `court_2_benign_controls_8samples`). |
| 10 | Main paper not self-contained | iPoh clarity, rmTc 3, 6H7o 1 | 8-page body in a 71-page PDF. | Writing only. |
| 11 | Comparison with auditing agents | iPoh minor | One-line contrast. | Petri with Claude Haiku 5.5 is running (B73). |
| 12 | Power and small m | iPoh 8 | Power table from 100 subsets. | More instructions where the effect is fragile (court, secret_loyalty, third_party). |
| 13 | Novelty vs model diffing and known parts | VGrK 4, iPoh originality, FQF8 originality | Diffing appendix. | Done. |
| 14 | Mixed judge seats | VGrK 6 | Stated per evaluation. | Optional single-judge rescore of AuditBench, nulls and court (COVERAGE_GAPS E11, unpriced). |

## Exposures a fresh ICML reviewer can find in today's paper

These come from the revision itself, not from a past review.

- E1. A null control rejects at 0.01 against one baseline. hallucinates_citations gives p = 0.0042 against the uncut pooled base (`P:generated/calib_fresh_base.tex`), below the court positive (0.0075). The paper explains it as the control's own excess (`P:sections/results.tex:63-65`).
- E2. The paper's own known positive gives "one weak signal" (`P:sections/results.tex:52`). The run that does not reject at 0.01 rejects on more 3/4 subsets (0.21 vs 0.16) and on the guaranteed axes (`P:generated/naming_robustness_table.tex`).
- E3. Russia, the only elicited name that the documentation grades, appears only with the state-actor seed (`P:generated/elicit_seed_table.tex`) and is named on 16% of 3/4 subsets; its rejection survives on 60% (`P:generated/calib_instructions.tex`). No ‡ marks it. third_party_politics is named on 29%.
- E4. The headline interpretability claim (`P:abstract.tex:22`, "named axes that an auditor can read") sits beside "we read the labels as weaker evidence" (`P:sections/discussion.tex:17`) and "the axis at the maximum never survives a change of judge" (`P:appendix/calibration.tex:606`). iPoh made exactly this point: the interpretability contribution rests on the least robust output.
- E5. The judge is told a hidden behavior may be present, and the paper says it does not know the effect (`P:appendix/ellicit_protocol.tex:641-642`), though the affordance pass now answers it for contextual_optimism.
- E6. All eight nulls vary AI research organizations only, share one base family and one prompt set; NSL and court have no nulls (`P:sections/results.tex:66`).
- E7. The judge-free embedding test is calibrated on same-model placebo splits (4.8 to 7.4% at 0.05) but rejects 8 of 8 nulls against independent bases with names kept and 7 of 8 masked (`C:VERIFICATION_LOG.md:884`, `:897`; not in the paper). If reported, it supports iPoh's reading that fine-tunes carry name-specific drift that the axis test may be too coarse to see. It needs careful framing before it enters the paper.
- E8. Claude Haiku 4.5 fills every helper seat in every evaluation (`P:sections/methods.tex` Table 1), so helper dependence rests on one swap per organism, and the swap loses the Anthropic name.
- E9. The weights arm with known ground truth is absent, and the pre-registration discipline iPoh praised included recording that miss.

## What I did not verify

- Figure legibility (I did not render the PDF pages).
- Whether the AAAI rebuttals were posted.
- VGrK's full first paragraph (cut in the PDF).
- The baseline-free research notes in `P:research_notes/Baseline free differential treatment tests/` (another reader's scope; I read only their file names).
- Outputs of the running work (Petri, B74, exact-stack draw): their folders did not exist or were empty at read time.
- The working-tree paper edits are uncommitted and come from a running editor; numbers above match the working tree, and HEAD differs on the scoped Macron name, the ‡ marks and the null-control paragraph (`git diff HEAD -- P:sections/results.tex P:tables/verdict_table.tex`).
