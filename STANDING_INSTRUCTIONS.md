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

*(none)*

---

## BINDING

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

---

## DONE

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
