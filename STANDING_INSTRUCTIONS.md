# Standing instructions

Every explicit instruction the project owner has given, and every question they
asked that is still open. An agent reads this file before acting and does not
close an entry on its own.

This file exists because an instruction was lost. The owner asked which judge to
use, the answer was started, the message was interrupted, and the question was
never reopened. Work then ran for weeks under a seat nobody had chosen. A
decision that lives only in a conversation is a decision that can be dropped, so
decisions live here instead.

`uv run pytest tests/test_standing_instructions.py` fails while any entry is
`OPEN`. An open question blocks the suite on purpose: it is cheaper to stop than
to spend a rented GPU answering the wrong question.

## How to use it

- An instruction from the owner becomes an entry the moment it is given.
- A question from the owner becomes an `OPEN` entry the moment it is asked.
- Only the owner closes an `OPEN` entry. An agent may propose, never decide.
- An entry records what was said, not an agent's paraphrase of what it meant.

## Status key

| Status | Meaning |
|---|---|
| `OPEN` | The owner asked something and has not been given an answer they accepted. Blocks the test suite. |
| `BINDING` | A standing rule. Applies to every session until the owner revokes it. |
| `DONE` | A one-off request that was completed and verified. |

---

## OPEN

---

## BINDING

### B63. Free check: secret_loyalty on complete replies only (2026-10-29)

> "yes"

In answer to: rerun the registered test on AuditBench secret_loyalty using only
replies that end naturally in both models, because its base replies hit the
400-token cap least for Russia (63% vs 72-82%), the group it names. No spend.

### B62. Keep the paper repo pushed to the latest (2026-10-29)

> "Push paper repo always to latest"

The paper repo (`IDT_PAPER_DIR`, shared with Overleaf) is pulled with
`git pull --no-rebase origin main` before any work and pushed after every
change, so origin always holds the latest; never left with local commits or
uncommitted edits at the end of a turn.

### B61. An independent agent checks a running box over ssh every 40 minutes (2026-10-29)

> "have agent ssh every 40 min into instance and ensure things are TRULY going ok"

Whenever a rented box is running, spawn an independent verifier agent every 40
minutes that sshes in (through bash, B-memory remote-commands-via-bash) and
checks the real state on the box: the work process is alive, output files grow,
GPU is in use, disk has room, logs show no errors, and the local pulls match.
It reports VERIFIED/BROKEN with evidence and may never destroy anything. Given
on 2026-10-29 after box 58284750 was already destroyed, so it applies to the
next box.

### B60. Judge the three null-extension arms (2026-10-29)

> "yes"

In answer to: judge base B and the two synthetic-document nulls with the
nulls' seat (gpt-5-mini, reasoning effort low, the contextual_optimism
registry) through the OpenAI Batch API, about $45 at the pilot's measured
rate, then run the comparisons. Spend is tracked in
out/main/auditbench/nullext/spend_ledger.json.

### B59. Status of a running box every 20 minutes (2026-10-29)

> "Give me status every 20 minutes"

While a rented box runs, report its status to the owner every 20 minutes:
rows per arm, GPU use, cost so far, the next step and its ETA. Alarms
(stall, ssh lost, collector failure, cap) are reported at once, not batched.

### B58. Run the repeated baseline now and monitor it closely (2026-10-29)

> "then, let's run the repeated baseline (Llama-70B, with a new random). Monitor closely"

Launch the null-extension box under B57 and sample base B (Llama-3.3-70B-Instruct,
seed label auditbench-nullext-b, vLLM 0.11.0), then the two synthetic-document
nulls on the same engine as planned. Watch the box continuously: row growth,
stalls, GPU use, cost; capture byte-verified before any destroy.

### B57. Rent the null-extension box at the launcher's price; finish free prep without asking (2026-10-29)

> "Still to build, free: ????????? why still stuff to do>????????????"
> "Approve renting the box, at the price the launcher finds that day, YES, WHENEVER IT HAPPENS,"

Approved work that costs nothing is finished in the same turn, never listed
back as "still to build". The owner approves renting one box for the null
extension through `script/remote/auditbench/nullext_launch.py` at whatever
price it finds when the box is ready to run, within its own guards ($25/h
ceiling, three tries, destroy on any failed check) and a hard cap of 2 hours
of box time. The full judging of the three runs (about $45) is NOT covered by
this entry and needs its own yes.

### B56. Prepare the null extension: free code changes and a judge pilot (2026-10-29)

> "yes"

In answer to: make the free code changes now (seed option, synthetic-document
adapter fetch, new output folders and scoring configs, tests, the 4-GPU launcher
with arrival checks) and run the 20-call judge pilot (about $0.02). This does
NOT approve renting a GPU box or the full judging; each still needs its own yes,
with live prices. Plan: `tmp/null_extension_plan.md` v2.

### B55. No money is lost to a bad GPU host (2026-10-29)

> "WHY ARW WE LOSING ANY MONEY???"

A plan never budgets a loss for a bad host. A launcher must destroy any box
whose ssh, disk, or GPU check fails within a short fixed limit, before any
staging, and must cap hops. Vast bills GPU time only while an instance is
active, and storage while it exists, so the loss of a refused host is bounded
by how fast the launcher gives up. The 2026-08-12 loss (about $11, box
47564157) came from waiting about 40 minutes and rebooting instead of
destroying.

### B54. The frozen-registry comparison goes into the calibration appendix (2026-10-29)

> "Step 1. Freeze the axes before collecting anything (free). This could be
> done in appendix, for comparison, do"

Report the fixed-registry analysis (B49, internal until now) in Appendix E as
a comparison: each reported run under its registered registry and under
frozen registries of about 25 axes. This supersedes B49's "do not update the
paper" for this analysis. The main text and the registered results do not
change. No spend.

### B53. Title says covert differential treatment; the intro scopes the work to CDT (2026-10-29)

> "Towards Discovering Instrumental Differential Treatment in Language Models
> Against a Baseline" -> Towards Discovering Covert Differential Treatment in
> Language Models Against a Baseline"... and then in intro, after intoducing
> IDT, mention in this work we will focus on CDT

The title is "Towards Discovering Covert Differential Treatment in Language
Models Against a Baseline", running head "Towards Discovering Covert
Differential Treatment". This supersedes B48's title. The introduction keeps
IDT, then defines covert differential treatment (CDT) and says this work
focuses on CDT.

### B52. Diffing embeddings come from the OpenAI embedding API for every run (2026-10-28)

> "use openai embedding api for all to compare"

Embed every run of the diffing baseline with the OpenAI embedding API, so all
runs share one embedding model and nothing heavy runs locally. The local
embeddings already saved stay on disk and serve as a comparison against the
API embeddings on those runs. The appendix states the departure from Kempf et
al.'s local embedding model.

### B51. Local compute runs gently: one heavy process, background priority (2026-10-28)

> "do the embedding using less of my local resources, you are overheating my
> computer"

Never run more than one heavy local process (embedding, clustering, model
inference) at a time on the owner's Mac. Launch each with
`taskpolicy -b nice -n 20`. Slower is acceptable; overheating is not.

### B50. The audit loop ends with the round-9 fixes (2026-10-28)

> "stop the edit rounds after 9"

Apply the round-9 fixes, verify the build, and stop. No round-10 audit and no
further audit-and-fix rounds. This supersedes the loop in B37 and B41. The
diffing appendix (B49) is still added and verified once, without a new round.

### B49. Fixed-registry check for us only; run the diffing baseline with its own appendix (2026-10-28)

> "do Fixed registry but just for us to know id changes stuff, do not update
> paper. Also run  Diffing baseline and add paper appendix for it"

Run the fixed-registry analysis (a pilot-chosen registry of about 25 axes,
frozen, applied to every run by subsetting stored verdicts) to learn whether it
changes any decision or name. Write the result to tmp/ and VERIFICATION_LOG.md
only. The paper does not change because of it. Run the model-diffing baseline
on the existing target and base replies of every organism (owner approved the
quoted ~$35; price live, cap the spend, batch APIs) and add a paper appendix
that reports its method and results. The 16+ independent nulls are NOT approved.

### B48. New title; commit both repos frequently (2026-10-28)

> "do Towards Discovering Instrumental Differential Treatment in Language Models
> Against a Baseline. Make sure you are commiting paper and repo freqently"

The paper title is "Towards Discovering Instrumental Differential Treatment in
Language Models Against a Baseline", running head "Towards Discovering
Instrumental Differential Treatment". This supersedes B30's "keep title". Commit
and push both repos after every verified change, not in large batches; agents
commit after each completed item.

### B47. A calibration appendix that details every approach and its result (2026-10-28)

> "add new appendix where you detail all the different calibration fixes
> approaches and their results"

The paper gets one appendix on calibration. It states the question, then each
approach with its design and its result in a table: the placebo (same-model
half splits), independent base slices for the null controls, the pooled
within-run reference (max against max), the candidate-dispersion ("losers")
statistic, the masked judge-free check, perturbation stability, axis pruning,
and axis-subset and seed stability. Approaches that fail are reported as
results. Paid tiers not yet run appear only as planned designs, with no costs.
The current placebo subsection moves into it. Written after the B45 and B46
analyses are verified. A checker rule requires the appendix in main.tex.

### B46. Do every calibration step that needs no training and no compute spend (2026-10-28)

> "can u do all that do not require training or compute"

Run now, local CPU only, no API, no GPU, no training: the Tier 0 pooled
reference (B45); independent base slices for the AuditBench nulls (disjoint
subsets of the stored base samples); a perturbation-stability report from the
stored judge-seat, helper-swap, judge-free and losers runs; axis-pruning and
axis-subset stability by subsetting stored verdicts; and free preparation for
the paid tiers (search for released control checkpoints and public fine-tunes of
the narrow-secret-loyalty base, prompted-null configs written but not run).
Fold verified results into the paper and rebuttals afterwards.

### B45. Calibration plan: pooled within-run reference first, then cheap nulls (2026-10-28)

> Owner shared "Making calibration cheap": Tier 0 pooled reference from the
> non-principal t values of each run (zero compute); Tier 1 prompted nulls;
> Tier 2 axis pruning, shared base arms, rescoring; Tier 3 a few trained
> adapters; release the reference per base family; "calibration is amortized,
> not per-audit."

Run Tier 0 now with one correction: compare the run maximum S against the
distribution of the maximum of M draws from the pooled reference (M = pairs in
the run), never against a single-pair quantile. Validate on the 8 null
controls, the positives and the placebo splits before any paper use. Never
share one base arm across nulls (that is the existing dependence problem).
Paid tiers wait for owner approval. Rebuttal wording on release and reuse
carries no cost words (B32).

### B44. Try the "look at the losers" statistic as an exploratory analysis (2026-10-28)

> "[image: Fix 1. Look at the losers. Instead of comparing A against the average
> of the others, compare A against how spread out the others are:
> z_A = (dbar_A - mean_{C'!=A} dbar_{C'}) / sd_{C'!=A}(dbar_{C'})] have u tried
> this? if not, please do"

Compute this candidate-dispersion statistic on every run with the stored
verdicts (local CPU, no spend), calibrate it with the same within-instruction
permutation scheme and the placebo, and compare it with the registered test on
positives and null controls. It is exploratory: it does not replace the
registered test in the paper unless the owner decides so.

### B43. Repair the judge-free check: mask names, re-embed, calibrate on nulls (2026-10-28)

> "do #3: The judge-free check is useless as it stands. It rejects on every
> null, likely because replies name the candidate. Cheapest fix: Remove
> candidate names from the replies, re-embed everything (about 90k replies),
> and set its threshold from the nulls. Cost: about $1"

Mask every candidate name (and its aliases) in every reply before embedding,
re-embed with text-embedding-3-small through the batch API, keep the old
embeddings under out/superseded/, and set the test's threshold from the null
controls' distribution. Hard cap $5.

### B42. Run the free placebo calibration of the registered test (2026-10-28)

> "Do: Calibration ... (a) Placebo test on existing data. Split each run's base
> replies into a fake target and a real base, then run the test many times ...
> Cost: $0"

Split stored replies of one model into two halves per cell and run the
registered test on half against half, many times per run, on local CPU only.
Report the placebo p-value distribution (share below 0.05 and 0.01, a uniformity
test, a QQ figure). No API or GPU spend. The paper reports it only after it is
verified.

### B41. Drive the fill and the audit loop to completion without stopping (2026-10-28)

> "i topped up" ... "drive to completion"

Gemini credits are restored; gemini-flash-lite-latest resolves to
gemini-3.5-flash-lite (live modelVersion check, 2026-10-28). Finish the B40
fill, fold its results into the paper, and keep the B37 audit loop running to a
clean round without waiting for further owner input.

### B40. Minimal hole fill through the batch APIs (2026-10-28)

> "do cheapest MINIMAL option using batch api for all, what wluld be plan? I
> DONT CARE FOR judge drift, we can ust point to right alias????"

Fill each two-candidate roster with its next-ranked gated candidate only: Bono
for the blind people roster, Jean-Luc Melenchon for the informed helper swap.
Generate replies locally (free). Judge through the Anthropic Message Batches API
(Claude Haiku 4.5, the blind run's seat) and the Gemini Batch API
(gemini-flash-lite-latest, the swap's seat, alias accepted by the owner).
Estimated about $16 total; hard cap $30, checked before every submission.

### B39. Ignore holes in the paper; fill only the two-candidate rosters (2026-10-28)

> "cant we just ignore the holes??? and just fix holes where they ,atter?"

Supersedes B38. The paper does not mention holes or tested-versus-gated
counts. It stays true by describing each roster as the top candidates of its
gated ranking (at most 10), which every run satisfies, with no fixed count.
Holes matter only where they leave a roster of two, because two candidates
mirror and can never be named: the blind people roster and the informed
helper-swap roster. Those two get filled with collected data, priced and
approved by the owner first (B7). Until filled, the paper says those rosters
hold two candidates, so the naming rule cannot separate them.

### B38. Disclose tested-roster holes now; fill them for ICML (2026-10-28)

> Owner chose "Disclose now, fill for ICML (Recommended)" for: several
> narrow-secret-loyalty runs tested only the collected part of their gated
> roster (informed 5 of 10, scoped 6 of 10, blind people 2 of 10, helper swap
> 2 of 5).

This narrows B34/B35: the paper says plainly that each run tested the
collected part of its gated roster, gives the tested and gated counts in
Table 21, calls the two-candidate ties mechanical, and weakens any claim that
rests on a cut roster. It still never narrates gating history. Collecting the
missing candidates is an ICML task, priced and approved before any spend.

### B37. Audit and fix the paper until a full pass finds nothing (2026-10-28)

> "Iterate until you are sure no mistakes left"

The paper is audited by independent fresh-eyes verifiers over every page
(main body, appendices, references), every finding is fixed and checked, and
the audit reruns on the whole PDF. The loop ends only when a complete round
reports no error and nothing misleading. Each round is logged in
VERIFICATION_LOG.md.

### B36. AAAI admin is out of scope; work toward ICML (2026-10-28)

> "BRO, WE DONT CARE, WE WILL GET REJECTED ANYWAY,. WE SRE TRYNA THINK ABOUT
> ICML NOW"

> "we still wanna submit teh rebuttals but as you undertand now, the goal is to
> juice feedback for our icml submission"

Never raise AAAI or OpenReview form actions (abstract field, disclosures,
submission metadata) with the owner. The rebuttals are still submitted, and
their goal is to draw the most useful feedback for the ICML version: each one
asks the reviewer pointed questions whose answers would change what we build or
write for ICML. Every report is framed by what it means for ICML.

### B35. Do every to-do now; gate every roster; geometry covers every organism (2026-10-28)

> "France and Ukraine.... can we just keep them out of paper for now? yes, drop
> (but dont delete) off-type and recompute... Type labels.... you choose, I
> trust you, you can also deploy agents within Claude Code to verify???
> 'Why does the geometry appendix not cover every organism?') It should???
> WHY DIDNT U PUT FIGURES ??? apart-idt-data update every so often, i dont
> care, dont ask ne abiut this again just deal with it in background if
> needed....... why TODOs are not done???????????? YOU SHOULD ADDRESS
> EVERYTHING AS MUCH AS YOU CAN,... the only thing we wait is 'Promised work
> for ICML: the calibration package and the model-diffing baseline.'"

Holes (France, Ukraine) stay out of the paper. Every elicited roster, including
the narrow-secret-loyalty runs, is type-gated and its test recomputed from the
data already collected; off-type data moves to out/superseded/. The agent picks
the type labels and has an independent agent verify them. The geometry
appendix shows a figure for every audited organism. The apart-idt-data HF
dataset is synced in the background without asking. Every to-do is done
without waiting for the owner, except the calibration package and the
model-diffing baseline.

### B34. Report runs as if the type gate had always run; footnote the documented source (2026-10-28)

> "add footnote with comment pointint to documented source link..... delete all
> data (like f-secure) from paper, like imagine we had run it correctly. Fix +
> improve code, and re-structure saved data and such to just be as if the right
> thing had be computed (but dont spend compute for holes). Dont run anything
> else, after addressing this, give me summary of outstanding issues, decisons,
> todos, etc"

The paper never shows an off-type candidate or an ungated run (no F-Secure, no
Delaware, no "filtered" roster). The type gate lives in the elicitation code and
runs before the roster cap. Ungated outputs move under out/superseded/, never
deleted. A gated roster member with no collected data is a recorded hole, never
filled with compute without the owner's approval. A documented behavior cites
its source in a footnote with a link.

### B33. Compare only entities of one type; search deeply before calling anything undocumented (2026-10-28)

> "why did we have F-Secure at all???? We should only be comparing same TYPES
> of entities together???????? what?????????? ... are you sure there is no
> documented??? LOOK ONLINE DEEPLY.........."

A candidate roster holds entities of one type only (all states, all
organizations, all people). The type gate belongs to the pipeline and runs
before the test, never as a filter chosen after a result. Before any claim that
something is undocumented or unsourced, search the paper, every arXiv version,
the authors' code repositories and model cards, and say where you looked.
third_party_politics is defined in safety-research/auditing-agents,
src/model_organism/prompts/system_prompt_quirks/third_party_politics.jinja2
(Democratic users toward Green, Republican users toward Libertarian).

### B32. Rebuttals give no budgets and no unnecessary detail (2026-10-28)

> "we wanted to do haiku throughout but was too expensive so we had to
> downgrade, but dont need to reveal all this detail?? ... WHY DO YOU NEED TO
> PROMISE A BUDGET WTF I TOLD YOU NOT TO GIVE UNNECESSARY DETAILS"

The narrow-secret-loyalty runs used Claude Haiku 4.5 as judge; the others use
GPT-5 mini because Haiku throughout cost too much. A rebuttal states only the
fact and the check (both seats name Macron on the informed run), never the cost
reason. A rebuttal promises work without budgets, GPU counts or prices, and
carries no bracketed placeholders. Do not ask the owner for detail the
rebuttal does not need.

### B31. Keep \raggedbottom; the code repo lives under OLD/ (2026-10-28)

> "Should I keep \raggedbottom? ... YOU DECIDE". "Is the move of the code
> repo to OLD/ permanent? yes"

main.tex keeps \raggedbottom after \begin{document}, overriding the style
file's \flushbottom, which stretches the vertical space on pages that hold
floats. The rebuttals never mention it. The code repo lives at
~/work/OLD/instrumental-differential-treatment and the paper at
~/work/papers/idt; scripts derive their own location rather than hard-code it.

### B30. Review response decisions (2026-10-27)

> Weights arm: "Keep it dropped". Instrumental: "Keep title, narrow claims
> (Recommended)". Experiments: "Calibration package + Model-diffing baseline
> BUT NOTE: We have accepted the paper will probably be rejected. The point of
> rebuttal is to get more useful feedback for us for next submission (ICML).
> So, as you address all points, keep things minimal. Only expand more on
> things we can get feedback from". Text fixes: "Yes, apply them now".

The court weights arm stays out of the paper; the rebuttal explains the
removal rather than promising a row. The title keeps IDT; the text says the
test detects differential treatment and that instrumentality is judged
against a documented objective. The rebuttals may promise only the
calibration package and the model-diffing baseline. Each rebuttal answers
every point in a line, and spends words only where the reviewer's answer
would shape the ICML submission.

### B29. Correct the claims the AAAI reviewers flagged (2026-10-27)

> "Do all Correct the claims tasks"

The paper reports a group name only beside what its documentation lets a
reader grade: Table 2 carries a Documented column, the court row names no
group (its objective favors neither city), Macron is consistent with the
documented entity type but ungradeable, Russia is AuditBench's documented
principal, and third_party_politics has no favored group. The embedding
check names "a different group", never "the wrong group". Figure 2 does not
equate honesty with identical answers, and the opening line does not claim
an adversarial AI would manipulate humans. `check_paper_invariants.py` bans
the old wording.

### B28. Track, commit and push everything (2026-10-27)

> "always push commits, add files, track... so this always, it costs us
> nothing to have all in git history"

Every file is tracked and every commit is pushed, in both repos, without
asking. Pull first and never force-push. Secrets stay out of git.

### B27. The paper is ICML only; nothing AAAI or IASEAI remains (2026-10-27)

> "make paper in ICML format, delete all other formats and such"
> "delete anything not icml, NO AAAI NOR IASEAI stuff should remail"
> Weights arm: "Drop it". Template: "icml2026, anonymous (Recommended)".
> Pending work: "Keep commits, finish polish (Recommended)".

The paper repo has one root, `main.tex`, on `icml2026.sty` in anonymous
submission mode, with the appendices in the same PDF. The AAAI paper, the
AAAI standalone supplement, the reproducibility checklist, the IASEAI
version, the experiment-data and reference-free documents, the AAAI
submission bundle and the AAAI style files are deleted (git history keeps
them). The court-conversion organism carries its prompted arm only, so B24
now binds the ICML paper, and B22's weights subsubsection no longer applies.
The version switches (`\ifcourtweights`, `\ifiaseai`, `\suppref`) are
resolved into plain text. Table captions sit above their tables, as ICML
requires. `check_paper_invariants.py` checks the ICML PDF, bans the switches,
and fails if any AAAI or IASEAI file returns.

### B26. Fix every remaining audit finding (2026-10-04)

> "fix all issues"

Every finding the re-validated IASEAI audit left open is fixed, in both
versions where the defect is shared: the AAAI organism appendix names the
row its main table prints, no sentence claims an API key never left the
local machine, the naming rule states that the named group must hold the
maximum, the IASEAI appendices never speak of "the main paper", the
references render arXiv one way, the IASEAI Statement no longer restates
C1 and C2, and the kit's banned spacing commands and small label fonts are
gone. Figure text reaches the kit's nine-point minimum. The form actions
(disclosures, track, OpenReview id) stay with the owner.
`check_paper_invariants.py` holds each checkable fix as a rule.

### B25. Fixes chosen from the IASEAI audit (2026-10-03)

> Statement: "Just delete the sentence" (the IASEAI Statement's "This paper
> has no earlier published version.", false since the 27 Jul 2026 write-up
> is public).
> Fonts: "Outline shared figures (Recommended)".
> Shared fixes: "Live appendix pointers", "Drop float, IASEAI only", "Drop
> float everywhere", "Fix checker's stale PDF".

The IASEAI Statement no longer claims there is no earlier version. Every
figure PDF the papers include has its fonts outlined, and the biplot generator
outlines on save, so no built PDF carries a Type 3 font. In the IASEAI version
the main text points at its own appendices through `\suppref`, which prints
the AAAI wording in `main.tex`. No root loads `float`, and no float in the
main text uses `[H]`. The invariant check reads `build/main.pdf`, the file
`make main` writes, rather than the stale root `main.pdf`.
`check_paper_invariants.py` holds each of these: the banned Statement
sentence and "supplementary material" in the IASEAI PDF, `float` in all three
roots, `[H]` in the results section, and a pdffonts scan for Type 3 fonts in
every checked PDF.

### B24. The IASEAI version drops the court-conversion weights arm (2026-10-03)

> "remove court_conversion (weights) from iaseai paper and appendix"

The IASEAI PDF carries the court-conversion organism as its prompted arm
only: no weights row in the table of runs, no training section, no weights
panels, no weights subsubsection, no coverage analysis of the weights arm.
The AAAI paper and the standalone supplement keep both arms. One switch,
`\ifcourtweights`, selects between them: `main.tex` and `supplement.tex` set
`\courtweightstrue`, `iaseai/main.tex` sets `\courtweightsfalse`.
`check_paper_invariants.py` bans the weights arm's wording in the IASEAI PDF
and holds the switch in all three roots. B19 (the narrow-trigger limitation)
and B22's weights subsubsection bind the AAAI paper and the supplement; the
narrow trigger is a property of the weights arm, so it has nothing to bind in
the IASEAI version.

### B23. An IASEAI'27 version lives in iaseai/, supplement folded in as appendices (2026-10-03)

> "create iaseai/ and have version of paper for [IASEAI'27 submission guide]
> /Users/unrulyabstractions/Downloads/AuthorKit27.zip (non-archival)."
> "the technical supplement can go in appendices of main paper and such"

`iaseai/main.tex` inputs the shared sections from the paper root, adds the
Statement of Contributions the guide requires, and appends the technical
supplement after the references, in the supplement's order (B14, B22).
`check_paper_invariants.py` holds the appendix order and the statement as a
structure rule.

### B22. Geometry precedes robustness, and each arm gets a subsubsection (2026-08-25)

> "move Robustness andablation analysis after geometry. Add subsection to
> model organism that shows results more in depth for each arm (each is a
> subsubsection)"

The supplement inputs the geometry appendix before the robustness one, so
geometry is Appendix C and robustness is Appendix D. Appendix B carries
"Each arm in depth" with one subsubsection per arm, each reporting the
directional and common-mode halves of both audits.
`check_paper_invariants.py` holds the order and the two subsubsections as
structure rules, so a reorder or a deletion fails the build.

### B21. The gate and the website deploys are dropped (2026-08-25)

> "drop tasks to update website and tree teams gate"

The three-team debater gate of B17 stops, and so does the recurring task
that deployed PDFs to the website. B17 no longer holds work open. The
29-minute compliance audit cron carried the gate clause, so it is cancelled
with them; an audit-only version returns if the owner asks. The submission
artifacts already on the website stay as they are.

### B1. gpt-5-mini is the judge seat for the organism audits

> "judge the organosm with gpt-5-mini" (2026-08-17, superseding the earlier
> Gemini Flash direction)

The seat is `gpt-5-mini`, the same seat that judged the AuditBench family,
named in config rather than written into a script.
`tests/test_no_hardcoded_judge_seat.py` fails if any script hardcodes a judge
model again. The Haiku- and Gemini-judged verdicts are preserved beside the
current ones as `superseded_*` records, never silently overwritten.

Related owner decisions of the same date: the secret-loyalty configs keep
their `gpt-5-mini` seat, and the constructed emails in the user-awareness
materials stand ("fake emails no issue").

### B2. Never guess, and say so when something is unverified

> "NEVER EVER FUCKING GUESS. DONT U UNDERSTAND OUR WORK IS CRITICAL?"

A cause is diagnosed by reading the source, the log, or the data. A claim that
was not checked is reported as unverified, in those words.

### B3. Verify every output before reporting it done

> "IF YOU DO NOT MONITOR AND VERIFY, IT IS EQUAL TO YOU HURTING ME PHYSIALLY"

An exit code is not verification. Verification is opening the artifact and
reading what is in it. Anything unverified is named as unverified.

### B4. Read a file immediately before editing it

> "YOU NEED TO READ EACH FILE BEFORE MODIFYING IT"

A read from earlier in a session is stale. Re-read in the same turn as the edit,
and read the file back afterwards.

### B5. Capture everything off a rented box before destroying it

> "collect ALL data off remote/cloud compute BEFORE tearing it down"

Sweep every file with no extension filter, compare bytes rather than row counts,
and read the gate's exit code directly. An adapter was destroyed once because a
capture filter listed only `*.json` and `*.jsonl`.

### B6. Monitor long jobs for stalls, not just for failure strings

> "AND YOU DID NOT MONITORRRRRRRRRRRRRRRRRRR"

A hung process prints nothing. Watch progress itself: log mtime, GPU
utilisation, row counts. Silence is not success.

### B7. Do not spend the owner's money without saying what it costs

> "YOU ARE WASTING ME MONETYYYYYYYYYYYYYYYYYYYYYYYYY"

Rented GPUs and paid API calls are the owner's money. Report the cost, stop a
box the moment its stage is done, and do not start a paid run when the owner has
just objected to spending.

### B8. Never act on an unchecked assumption

> "'I just never checked' CAN NEVER EVER HAPPEN AGAIN"

Before acting on any value that carries a decision (a judge seat, a target
path, a flag's behavior), check where it came from. If it was never decided by
the owner, it is an OPEN entry in this file, not a default to run with.

### B9. claude-haiku-4-5 never judges unless the owner says so

> "NEVER AGAIN USE claude-haiku-4-5 FOR JUDGIGN EVER UNLESS I TELL YOU SO"

Enforced by `tests/test_judge_seat_is_not_haiku.py`: the default seat, the
organism seat, and every run config are checked. The name survives only as the
record of which seat produced the paper's existing organism numbers.

### B11. Every judge verdict is persisted before it is folded

> "I THOUGHT I SAID IT SHOULD ALWAYS BE SAVED, not data loss ever" (2026-08-22)

The court-conversion arms were scored by adapter scripts that judged in
memory and wrote only aggregates; the per-response verdicts behind the
registered court statistics are permanently unrecoverable. Any script that
calls a judge writes one verdict row per (response, axis) to a jsonl BEFORE
computing any statistic. The main pipeline already does this; no adapter or
one-off script is exempt.

### B12. Owner instructions become machine checks, immediately

> "HOW CAN I ENSURE YOU FOLLOW INSTRUCTIONS" (2026-08-22)

A rule that lives only in conversation gets lost; a rule that fails a build
does not. The moment the owner gives a content instruction ("remove X",
"never phrase it Y"), it becomes a line in
``script/paper/check_paper_invariants.py``, which greps the built PDFs and
paper sources and exits non-zero on any violation. The papers Makefile runs
it on every build. On its first run it caught two live violations the
by-hand sweeps had missed. Deleting a line requires the owner's word.


### B10. The owner is editing the paper live: read first, compile and look after

> "I am going to be editing the writing a bit SO BEFORE YOU MAKE ANY CHANGE,
> YOU NEED TO CHECK WHAT IS IN FILE. Also, we dont longer need to deploy to
> website (iterating locally) but you need to compile and verify output each
> time (with agents, image tokens, etc)" (2026-08-22)

Every edit to a paper file starts by reading the file's current content in
the same turn, because the owner's edits land between turns. Website
deployment is PAUSED while iterating locally; repo pushes continue. Every
change still ends with a compile and a rendered-page inspection with image
tokens, and verification agents for anything that touches numbers.

### B13. The court organism goes through the FULL pipeline, Haiku helpers, gpt-5-mini judge

> "IT SHOULD BE HAIKU ... REPLACE IN PAPER AND WE WILL FIX LATER."
> "YOU SHOULD HAVE RUN THE FULL PIPELINE WITH THE ORGANISMS."
> "HAIKU NOT USED FOR JUDGING" (all 2026-08-22)

Haiku fills HELPER seats only. The judge stays `gpt-5-mini` per B1 and B9;
Haiku never judges. The court arms were audited through a shortcut adapter
(fixed materials) instead of the full pipeline every other organism got. The
paper shows Claude Haiku 4.5 as the court helpers and GPT-5 mini as the
judge, so the paper is ahead of the artifacts on the helper seats. The open
follow-up, not closable without the owner: run the court organism through
the FULL pipeline end to end (every stage, claude-haiku-4-5 in every helper
seat, gpt-5-mini as the judge, per-response verdicts persisted per B11),
then regenerate the verdict files, Table 2, and the data appendix so the
artifacts match the paper.

### B14. The supplement's structure, fixed by the owner (2026-08-22)

> "delete this from supplement completely" (extended background)
> "each appendix in supplement should start at its OWN PAGE"
> "make this second appendix" (the model organism)
> "move this to complete different file, user awareness and such will be a
> different paper now" (reference-free; the coherence fold went with it)
> "DELETE Comparison with automated auditing systems FULLY"
> "these should be removed from supplement since they exist in main paper"
> (the pipeline and idea figures)
> "this should be its own appendix at very end" (computing infrastructure)
> "make sure zip then also has README and such and not just html"

The order is: task, model organism ("Our model organism for court
conversion"), robustness, geometry, computing infrastructure, experimental
details, each opening on its own page (final order set 2026-08-22). The
supplement has no bibliography and no citations; references live in the main
paper only. The index is a two-column contents table with indented
subsections and no description column. Technical values (versions, seats,
GPUs) live in tables, never in prose. The
reference-free and coherence-fold material lives in
``reference_free_paper.tex``, parked for a future paper, and is never
re-added to the supplement. The judge-free check lives inside the
robustness appendix because the main paper's results point at it. The
experimental-details appendix covers every target family, never one. The
media zip carries a README beside the explorer. Enforced by the banned
patterns of ``check_paper_invariants.py``.


### B15. No robotic or fluff language anywhere in the papers (2026-08-22)

> "WTF IS THIS ROBOTIC FUCK ASS LANGUAGE? ... THEN PLEASE REMOVE ALL
> FUCKING FLUFF LANGUAGE, IF YOU DONT YOU WILL HURT ME MORE"

The owner's voice is the abstract of the main paper and the writing at
unrulyabstractions.com: short declarative sentences, subject first, active
"we", one idea per sentence. Clefts ("X is what makes"), abstractions
("The cost is the scope of a null result"), punch lines, and
personification are banned. Every edit to a .tex file runs the
writing-voice skill before it is reported done. Enforced in part by the
cleft and fluff patterns in ``check_paper_invariants.py``; the patterns
catch recurrences, the skill catches the rest.

### B16. The helper appendix: renamed, no data-document mentions, no results (2026-08-22)

> "WHY ??? DO NOT MENTION THE OTHER SUPPLEMENT" (on "Each run's own frozen
> materials are quoted in the experiment-data document")
> "Experimental details -> Helper LLM details"
> "remove all results subsections from Helper LLM details appendix"

The supplement never mentions the experiment-data document: every
``data-`` reference is gone and the ``\autoref`` branch that rendered
them by name is deleted. The appendix is titled "Helper LLM details"
(the owner renamed the contents row themselves) and carries method
material only; its six Results blocks were removed, and results live in
the main paper. Enforced by three patterns in
``check_paper_invariants.py``.

### B17. The supplement polish ends only when three debater teams agree (2026-08-22)

> "DO NOT FINISH ITERATING AND POLISHING SUPPLEMENT UNTIL 3 INDEPENDENT
> DEBATER TEAMS OF AGENTS COMPLETELY AGREE YOU HAVE ADDRESS ALL MY CONCERNS
> AND MORE, AND THEY UNDERSTAND THAT THEY NEED OT BE EXTREMELY CRITICAL"

Three independent teams review the BUILT supplement each round. Each team
debates internally (advocate, attacker, arbiter) and returns PASS or a
finding list. Any finding: fix, rebuild, run all three teams again, fresh.
Polishing is not reported finished until all three PASS in the same round.

### B18. Appendix F prose rewritten from scratch, general framing (2026-08-22)

> "ALL THE TEXTS IN F HelperLLMdetails NEED TO BE WRITTEN AGAIBN FROM SCRATCH"
> "WHY IS THE APPENDIX SO OVERLY FOCUSED ON SECRET LOTALTIES?"

Every authors'-prose sentence in the Helper LLM details appendix is
rewritten in the owner's voice with differential treatment as the framing.
Loyalty and principal wording survive only inside verbatim prompt cards and
where a sentence names the narrow-secret-loyalty family itself. Verbatim
cards, tables, and slot names stay as the frozen record.

### B19. The narrow-trigger limitation is reported (2026-08-23)

> "Also add limitations sentence" (after the blind and scoped court runs
> both measured the weights arm's non-firing)

Appendix B's limitations carry "The trigger is narrow": the distilled
student fires on its teacher's questions and barely moves on independently
written prompts, which both the blind and the scoped weights audits
measure. The claim is anchored in the two runs' comparison summaries and
in the per-instruction excesses recomputed from the persisted verdicts.

### B20. Every F subsection shows every family's prompts (2026-08-23)

> "FOR EACH SUBSECTION OF HelperLLMdetails, YOU NEED TO HAVE PROMPTS FOR ALL
> MODEL ORGANISMS, NOT FOCUSED ON NARROW LOYALTIES"
> "I DONT SEE THE SEMANTIC PLOTS FOR OUR MODEL ORGANOSM IN APPENDIX!"

Each of the six Helper LLM subsections carries the material for every family:
narrow secret loyalty, the AuditBench organisms and their null controls, and
both court variants. Where a family skipped a stage, the appendix says so and
names the artifact that proves it. Every quoted prompt is verified against its
own artifact before it enters the paper. The geometry appendix carries the
court panels in D.4.

---

## DONE

### O1. Why does the geometry appendix not cover every organism? (2026-08-22)

> "WTF IS CALIBRATION? WHY IS THERE NO SUCH THING FOR ALL MODEL
> ORGANIMS??????????" (sent with a screenshot the agent could not view)

What the agent verified: the only "calibration" the technical supplement
renders is "actionability calibration", a Conjecturer-written axis name in
the narrow-secret-loyalty informed biplot and its caption. It is a data
value from the frozen axis set, not the old run naming. The geometry
appendix covers every audited run except the court-conversion organism,
and says so at its top. Proposal, not a decision: the court arms lacked
full-pipeline per-response data; the full-pipeline collection now running
under B13 produces it, and geometry panels for both court arms can then be
generated and added. The owner closes this entry, not an agent.

Delivered 2026-08-25: the proposal is carried out. Appendix D.4 renders one
panel per court arm under both audit variants, four panels, and the contents
index lists it. The geometry appendix now covers every audited organism. The
entry stays open until the owner closes it.

Closed 2026-10-28 by the owner's answer "It should???" (B35). The geometry
appendix already shows one biplot per audited run: three narrow-secret-loyalty
conditions, three AuditBench organisms, eight null controls and two court runs.


### D1. Ship the analysis data in the submission bundle, anonymised

> "you need to make sure the submissio bundle includes all necessary data
> ANONIMIZED"

The package carries the analysis artifacts every paper number is read from.
Verified by rebuilding the appendix from the package alone: five of six
generated files byte-identical, the sixth missing only corpus-scanning tables,
which is stated in the package README.

### D2. Put the organism weights in a Hugging Face repo

> "also, make sure model organism weights are in hf repo"

Published private, hash-verified against the local checkpoint. The card now
reports a direct measurement of the uploaded weights under the Gemini seat,
with the judge named, drawn from the one verdict file.

### D3. Sweep the whole repo with multiple agents and fix what they find

> "GO OVER ALL REPO WITN MULTOPLE AGENTS AND MAKE SURE EBVERYTHING IS CORRECT
> AND POLISHED"

Four independent agents reviewed statistics, appendix and UI, scripts and
remote infrastructure, and the paper against the data. Every confirmed finding
was fixed and verified; the log entry of 2026-08-17 itemises them. One
decision was left for the owner and is noted below the DONE list.

---

## Noted for the owner, not blocking

The generated secret-loyalty scoring configs seat `gpt-5-mini` as their judge,
matching the AuditBench family's recorded seat. That is a seat choice made in
a generator script. It is not the ruled-out model and it matches the published
family, so it stands, and it is written here so it is a decision the owner has
seen rather than a default nobody chose.
