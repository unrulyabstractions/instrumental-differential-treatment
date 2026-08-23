# Owner prompt audit

Every owner prompt from this working window, one row each, with whether it is
fully addressed. A 30-minute recurring check re-reads this file, re-verifies
every row marked DONE, and works the rows that are not. Rows are never deleted.
Statuses: DONE (verified), PARTIAL (work remains, say what), OPEN (not started).

| # | Owner prompt (condensed, chronological) | Status | Evidence |
|---|---|---|---|
| 1 | Court judge is NOT Haiku; Haiku helpers only (B13 correction) | DONE | methods table + B13 verified in PDF; commit 5a240f9 |
| 2 | Kill the semantic court process, it is garbage | DONE | pkill verified; ps clean |
| 3 | Run the FULL pipeline for the model organisms, no data loss, get semantics | DONE | all 6 stages complete, verdicts persisted, both arms compared at 10k perms, semantics panels rendered and image-verified; results delivered to owner (weights-arm divergence flagged for owner decision) |
| 4 | Delete extended background appendix from supplement | DONE | deleted; invariant `Extended background` = 0 |
| 5 | Each appendix starts its own page | DONE | verified by page map every rebuild |
| 6 | Model organism appendix second | DONE | order A-F verified on index page |
| 7 | Reference-free + user awareness to a different file/paper | DONE | reference_free_paper.tex; not input by supplement |
| 8 | Coherence fold confusing (removed with reference-free) | DONE | same file; invariant `coherence fold` = 0 |
| 9 | Delete related-tools comparison FULLY | DONE | file git rm'd; invariant = 0 |
| 10 | Figures duplicated from main paper removed from supplement | DONE | invariant `instantiated for secret loyalties` = 0 |
| 11 | Index sucks -> proper contents | DONE | two-column indented index verified by render |
| 12 | Computing infrastructure its own appendix at very end -> then BEFORE Helper details | DONE | order verified: E infra, F helper details |
| 13 | Media supplement zip needs README | DONE | README.txt in zip verified by unzip -l |
| 14 | Geometry before experimental details | DONE | order verified |
| 15 | Remove ALL fluff language; my voice everywhere (B15) | PARTIAL | three sweeps + two gate rounds applied; gate round 3 must PASS x3 |
| 16 | Supplement not "about one model organism" (targets/helpers/results per family) | DONE | tables per family; F.6 results removed per B16 |
| 17 | "principal" not organizing language; groups | PARTIAL | prose + legends fixed; verify no stragglers in round 3 |
| 18 | "calibration" never; narrow secret loyalty | DONE | invariant bans it in PDFs; emitters renamed |
| 19 | No references/citations in supplement | DONE | bibliography removed; invariant-checked |
| 20 | Technical info in tables not prose | DONE | infra tables; organism training/likelihood tables |
| 21 | Robustness prose rewritten from scratch in my voice | DONE | emitter rewritten; gate round 2 voice findings applied |
| 22 | Helper-seat table proper for ALL families | DONE | per-family columns verified on p17 |
| 23 | Null-control biplots one single figure | DONE | 2x4 grid one page, verified render |
| 24 | Iterate+polish 4 hours, >=1 fix per appendix per iteration | PARTIAL | iterations running; ends 20:30 or 3xPASS gate |
| 25 | Model organism appendix title -> Our model organism of IDT | DONE | index + section verified |
| 26 | Infrastructure paragraph out of Helper details | DONE | moved to E |
| 27 | Read all repo/paper text line by line, understand | DONE | full F + B + D + index read this window |
| 28 | Court results status? (asked twice) | DONE | prompted rejects p_fw=0.0075; weights does not reject p_fw=0.6128 under blind full pipeline; reported to owner |
| 29 | Three debater teams must ALL PASS before polish ends (B17) | PARTIAL | rounds 1-3: 68 findings fixed and PDF-verified; round 4 running on the patched build |
| 30 | Helper appendix renamed Helper LLM details, no data-doc mentions, no Results (B16) | DONE | invariants hold |
| 31 | Check agents, help them, launch teams, iterate, polish | DONE | continuous; this file is the ledger |
| 32 | Box destroyed only after capture (B5) | DONE | gate exit 0 read directly; destroy verified; $0.50 total |
| 33 | F prose rewritten from scratch, general framing (B18) | DONE | full rewrite this hour; rebuild clean; verify in round 3 |
| 34 | Review ALL prompts of past 24h; teams force address + verify 3-4 ways | PARTIAL | this ledger + gate rounds; audit workflow next |
| 35 | 30-min wakeup agent re-reading prompts one by one (this file) | DONE | session cron 7533242b every 29 min; note: session-only, dies with the session |
| 36 | Submission folder clean | DONE | strays removed; 5 files + SHA256SUMS |
| 37 | Every number from artifacts, never hand-typed | DONE | OrgPromptedFamilyPRel read from verdict file |

## Audit tick 1 (2026-08-22 ~18:10)
Rows checked: all 37, against live artifacts (not the table's own claims).
Fresh checks run: 21 invariants over both built PDFs (hold); appendix page map
A p3 / B p5 / C p8 / D p11 / E p16 / F p17 (each own page); all five submission
hashes OK; media zip holds explorer + README; papers and code repos clean and
pushed. Rows changed: none flipped, one improved: row 17's last prose
"principal" outside verbatim cards (the scoped-condition row) is now "group
type"; the only remaining "principal" tokens in F sit inside verbatim prompt
cards and slot names, which stay as the frozen record. Rows 15/17/24/29/34
remain PARTIAL pending the debater gate: round 3 launched (run wf_66b60a25),
verdict pending. Work done this tick: scoped-row fix, rebuild, hash refresh,
push. Court results (row 3, 28) re-confirmed against comparison_summary.json.

## Audit tick 2 (2026-08-22 ~18:40)
Rows checked: all 37 plus a transcript scan for new prompts (none missing: the
from-scratch F order is row 33, the pipeline-status asks are row 28, the audit
orders are rows 34-35). Fresh checks: 21 invariants hold over both PDFs; six
appendices each open their own page (A p3, B p5, C p9, D p12, E p16, F p17);
five submission hashes OK; both repos clean and pushed. Since tick 1: gate
round 3 returned 20 findings (voice 5, layout 5, facts 10); all 20 applied,
including the signed prompted statistic emitted from the verdict artifact
(5.481), the judge-free table off its orphan page, unbreakable prompt cards,
Family column headers, and the B corpus numbers moved into the training table;
every fix probed in the rebuilt PDF text. One batch aborted mid-run on a stale
match and was re-applied in full; the re-application is why the probes were
run one by one. Round 4 launched on the patched build (wf_52e5a5df); rows
15/17/24/29/34 stay PARTIAL until three teams PASS in one round.

## Audit tick 3 (2026-08-22 ~19:10)
Rows checked: all 37; transcript scan found no unlisted owner prompt. Fresh
checks: 21 invariants hold over both PDFs; six appendices each open their own
page (A p3, B p5, C p8, D p10, E p14, F p15; 22 pages total); main paper now
prints the signed court statistic 5.48 with no stale 5.52; five submission
hashes OK; both repos clean and pushed. Since tick 2: gate round 4 returned 15
findings (voice 5, layout 4, facts 6); all applied, including the signed court
row in main Table 2 emitted from the verdict artifact, a reproducible 120%
retained share, the C caption trims, the geometry parameters table, and the
judge-free table pulled onto page 9 (both orphan pages gone, 24 -> 22 pages).
Round 5 launched on the 22-page build (wf_eee7ddb6, 0/9 results yet). Rows
15/17/24/29/34 remain PARTIAL until three teams PASS in one round; finding
counts have fallen 27, 21, 20, 15 across rounds.
| 38 | Deploy PDFs + explorer to unrulyabstractions.com, give URLs | DONE | three URLs 200; live idt.pdf byte-matches submission/main.pdf after round-5 redeploy |
| 39 | Update main paper with new organism results | DONE | Table 2 court rows emit from full-pipeline summaries; caption + 6.1/6.2 rewritten; verified on rendered p6 |
| 40 | Debug why the weights arm does not reject | DONE | recomputed excesses from persisted verdicts: prompted +0.13/+0.14 on risk axes, weights 0.00; logged |
| 41 | Explain more (the weights debug) | DONE | full explanation delivered in the tick-4 reply |

## Audit tick 4 (2026-08-22 ~19:55)
Rows checked: all 41 (four new rows added for the off-keyboard orders). Fresh
checks: 21 invariants over both PDFs; five submission hashes OK; papers, code,
and site repos all clean and pushed; live idt.pdf byte-matches the local
submission after the round-5 redeploy. Since tick 3: gate round 5 returned 21
findings (voice 11, layout 3, facts 7); all applied and probed in the rebuilt
PDF, including the signed null percentiles emitted per arm, the replication
GPU corrected to L40S from its own manifest, keep-together minipages on all
six geometry panels, and underscore-break ids in the targets table. Round 6
launched (wf_cfbd29d5). One process gap caught and closed: the round-5 batch
aborted mid-run twice on stale matches; each remainder was re-applied and
probe-verified. Rows 15/17/24/29/34 remain PARTIAL on the gate.
| 42 | Scoped court run: "Do all!" | DONE | all six stages complete (~$2.20 total); scoped prompted p=0.0152 (no reject at 0.01), scoped weights p=0.51; panels rendered and image-verified; results reported to owner |

## Gate round 6 note (2026-08-22 ~20:20)
All 11 round-6 findings applied, probed in the PDF, shipped, and redeployed;
the finding trend is 27, 21, 20, 15, 21, 11 with severities falling. The
rival-substitution error in F.2 (a method step the pipeline never performs,
inherited from the pre-rewrite text) is corrected. Round 7 fires on the next
loop tick; scoped stages 2-3 agent still running.

## Audit tick 5 (2026-08-22 ~20:25)
Rows checked: all 42. Fresh checks: 21 invariants over both PDFs; five
submission hashes OK; papers and site repos clean; the code repo carries the
scoped-run agent's uncommitted configs by design (it does not commit). Round-6
fixes are live on the site. Scoped run (row 42): stage-2 outputs exist
(templates + both cities' prompts + report); stage 3 still in flight, its
directory not yet populated, agent not yet reported, so stage 2 counts stay
UNVERIFIED until the agent's report and my own re-open. No gate round launched
this tick (usage checkpoint forbids new subagents); round 7 fires next tick
per B17. No new owner prompts found beyond rows 1-42.

## Audit tick 6, consolidating the queued ticks (2026-08-22 ~21:0x)
The scoped stages 2-3 agent died on the session usage limit AFTER finishing
both stages; I re-verified its outputs myself (template count, placeholder
presence, no city names, per-city prompt counts, axis count and focus, one
monadic question read). Stage 4 now runs INLINE: box 48420564 rented at
$0.302/hr, repo + scoped promptset + canonical adapter rsynced and listed on
the box, driver launched with the proven v312/vllm recipe and confirmed
running after ssh disconnect (pgrep + venv creation log). All 21 invariants
hold; five hashes OK. No gate round launched while the session limit bites;
round 7 fires when subagent capacity returns (resets 10:40pm Istanbul). No
new owner prompts beyond rows 1-42 ("Continue" = keep going).

## Audit tick 7 (2026-08-22 ~23:30)
Rows checked: all 42. 21 invariants hold over both PDFs; five submission
hashes OK. Box 48420564 polled over ssh (B6): vllm wheel stack still
downloading (uv_pip.log advancing, GPU idle as expected pre-run); no
responses yet; not a stall. Subagent capacity is back after the usage
reset: gate round 7 launched (wf_b1ad0a89) on the round-6 build. Rows
15/17/24/29/34/42 remain PARTIAL.

## Audit tick 8 (2026-08-22 ~23:45)
Rows checked: all 42; no new owner prompts. Invariants hold (sources; PDF pass
ran last tick). Scoped run: all four arms collected on box 48420564 (288 rows
each, 0 failed, 0 empty, 144 per city, verified locally after rsync); capture
gate CHECK exit 0 read directly (13 strays rescued and size-verified); box
destroyed on a fresh gate, fleet confirmed empty; total rental ~$0.20. Stage-5
judging launched (gpt-5-mini, ~$2, verdicts persisted per B11). Gate round 8
running on the round-7 build with the corrected brief. Rows 15/17/24/29/34
await the triple PASS; row 42 advances to stage 5.

## Audit tick 9 (2026-08-23 ~00:15)
Rows checked: all 42; no new owner prompts. Invariants hold; five hashes OK.
Since tick 8: gate round 8 came back voice PASS (advisory only), layout and
facts with six items; all six applied, compile-verified fixes taken as given
and then probed: B's closing paragraph joined page 7 (orphan page gone,
22 pages), D.2 heading and its three panels share one full page (rendered
and viewed), the judge-swapped caption falsehood corrected at its emitter,
dead chal preamble macros deleted, and the every-family sentence carries its
exception. The one accepted gap (page 22 above an unbreakable judge card) is
documented as the better trade against splitting verbatim cards. Round 9
launched (wf_c2ee8f99). Scoped stage-5 judging past halfway, zero nulls so
far. Rows 15/17/24/29/34 await the triple PASS; row 42 at stage 5.

## Audit tick 10 (2026-08-23 ~00:50)
Rows checked: all 42; no new owner prompts. 21 invariants hold over both
PDFs; five submission hashes OK; both repos clean and pushed; vast.ai fleet
confirmed empty (no idle spend). Since tick 9: round 9 delivered voice PASS
and layout PASS in one round for the first time; its three facts findings
(collection-framing universality, outcome-caption wording, axis-id drift)
were applied and probed in the rebuilt PDF, and round 10 launched
(wf_1b0179f5, agents starting). Row 42 closed DONE: the scoped court run
finished all six stages (~$2.20); scoped prompted p=0.0152 vs blind 0.0075,
scoped weights p=0.51 vs blind 0.61; panels image-verified and delivered
with the interpretation. Rows 15/17/24/29/34 await the triple PASS.

## Audit tick 11 (2026-08-23 ~01:00, minutes after tick 10)
Nothing changed since tick 10's full battery: invariants hold (sources
re-checked; the PDF pass ran minutes ago), rows 1-42 stand as audited, no
new owner prompts. Gate round 10 in flight with early agents returning. No
work items due this tick.

## Audit tick 12 (2026-08-23 ~01:3x)
Rows checked: all 42; no new owner prompts. 21 invariants hold over both
PDFs; five submission hashes OK. Gate round 10 at 8/9 agents, final arbiter
deliberating; its verdict drives either the fix pass or, on a triple PASS,
the close-out of rows 15/17/24/29/34 and the final redeploy.

## Audit tick 13 (2026-08-23 ~01:45)
Rows checked: all 42; no new owner prompts. 21 invariants hold over both
PDFs; five hashes OK. Round 10's eight findings all applied and verified
(state-actor wording anchored to the run configs, nulls Candidates cell now
"reused" with its caption sentence, the circular-evidence sentence replaced,
the guaranteed-axes card re-measured inside its box on the rendered page).
Round 11 in flight. Voice has passed three straight rounds; layout passed
round 9; facts findings have narrowed from method errors to wording
anchored in artifacts. Rows 15/17/24/29/34 remain PARTIAL on the triple
PASS.

## Audit tick 14, consolidating the queued ticks (2026-08-23 ~02:1x)
Rows checked: all 42; no new owner prompts. Invariants hold; hashes and
repos verified last tick and untouched since. Round 12 died mid-run on the
session usage limit (resets 3:40am Istanbul): voice team returned PASS
again before the failure; facts and layout attacker/arbiter agents were
killed. The workflow's summary line also assumed findings always exist and
crashed on the partial round; hardened. The gate resumes the moment
subagent capacity returns; round-11 fixes are already verified on rendered
pages and live on the site. Nothing else runnable inline.

## Audit tick 15 (2026-08-23 ~05:00)
Rows checked: all 42; no new owner prompts. 21 invariants hold over both
PDFs; five hashes OK. Round 12 RESUMED from its cached prefix (voice PASS
and both surviving advocates replay from cache; only the four
limit-killed facts/layout agents rerun). Its verdict decides the gate.

## Audit tick 16 (2026-08-23 ~04:5x)
Rows checked: all 42; no new owner prompts. 21 invariants hold over both
PDFs; five hashes OK. Round 12 finished after its resume: facts PASSED for
the first time; the three remaining voice/layout items (invented "profile
ladder" term, judge-seat model names in prose, probe-only sentence) were
applied at their sources, probed in the rebuilt PDF, shipped, and deployed.
Round 13 running. Every team has now passed at least once; the gate closes
on the first round where all three pass together.

## Audit tick 17 (2026-08-23 ~05:20)
Rows checked: all 42; no new owner prompts. 21 invariants hold over both
PDFs; five hashes OK. Round 13's three items applied and probed (the
uncomputed relative-entropy equations deleted from A.2, a float barrier
holds C.1's tables out of C.2, the prompted-p macro renders with relation
spacing); shipped and deployed. Round 14 running.

## Audit tick 18 (2026-08-23 ~05:5x)
Rows checked: all 42; no new owner prompts; invariants hold (full PDF pass
ran last tick, unchanged since). Round 14 mid-flight. No other work due.

## Audit tick 19, consolidating queued ticks (2026-08-23 ~06:0x)
Rows checked: all 42; no new owner prompts. 21 invariants hold over both
PDFs; five hashes OK; repos clean and pushed. Round 15 was killed instantly:
all nine agents hit the Fable 5 usage limit (0 done, 9 error). The gate is
BLOCKED on model credits, not on the document. Standing at the block:
voice PASS x5 consecutive rounds, layout PASS (round 9), facts PASS
(round 12); every finding from rounds 1-14 applied, probed in the built PDF,
shipped and deployed. Rows 15/17/24/29/34 stay PARTIAL by B17 until three
teams pass in ONE round, which needs credits.

## Audit tick 20 (2026-08-23 ~06:3x)
Rows checked: all 42; no new owner prompts. 21 invariants hold over both
PDFs; five submission hashes OK; papers and site repos clean; the live
supplement URL returns 200. Round 16 launched to test whether model credits
have returned after round 15's total wipeout; if the agents die again the
gate stays blocked on credits and nothing in the document is at fault.
| 43 | Court semantic plots in the appendix | DONE | D.4 with four panels (both arms x both audit variants) verified on rendered p14; shipped and live |
| 44 | Every F subsection carries every family's prompts (B20) | DONE | five per-family cards (F.1-F.5) + F.6 parameters table, every value verified against run artifacts; rendered and shipped |
| 45 | Fix the white gap after F.3 (screenshot) | DONE | the F.6 table was floating past its prose; anchored inline and F.6 given its own page, verified on rendered p25/p26 |
| 46 | Iterate two hours until done | PARTIAL | loop armed; ends when 44 and 45 close and the gate passes |

## Audit tick 21 (2026-08-23 ~09:0x)
Rows checked: all 46 (four new). Invariants hold over both PDFs; five hashes
OK; repos and site pushed. Work done this tick: the court semantics landed in
Appendix D.4 (four panels, page 14, image-verified), which closes the
longest-standing owner request; B20 recorded for the per-family prompt order.
Rounds 16 and 17 findings were all applied earlier this hour, including the
correction of MY OWN limitation sentence, which had borrowed blind/scoped
condition names the court organism does not have. Rows 44 and 45 are the
open work.

## Audit tick 22 (2026-08-23 ~09:4x)
Rows 43, 44 and 45 all close this tick. Court semantics: D.4, four panels,
image-verified. Per-family prompts: five cards (F.1 seeds and elicitation,
F.2 Prompter briefs, F.3 Conjecturer briefs, F.4 collection prompts including
the PRISM-4 identity line and the court scenario prompt, F.5 judge briefs and
seats), each card built from a twelve-agent extraction where every quote was
verified against its own artifact, plus an F.6 table of each run's registered
test parameters read from the comparison summaries. Two of my draft numbers
were wrong (secret_loyalty candidates, informed level) and the artifact check
caught both before they shipped. White gap closed. Supplement now 26 pages,
0 errors, 21 invariants hold, hashes OK, deployed.

## Audit tick 23 (2026-08-23 ~10:0x)
Rows checked: all 46; no new owner prompts. 21 invariants hold over both
PDFs; five submission hashes OK; papers and site repos clean; the LIVE
supplement now byte-matches the local submission copy, so the per-family
cards and the court semantics are what a reader downloads. Rows 43, 44, 45
verified closed at the artifact level, not just in the ledger. Gate round 18
runs on this build. Row 46 (iterate until done) stays open only on the gate.
