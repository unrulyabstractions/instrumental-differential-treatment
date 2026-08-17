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

### B1. Gemini Flash is the judge seat for the organism audits

> "WHY ARE U USING CLAUDE HAIKU O JUDGE ORGANISMS, DIDNT I SAY YOU SHOULD USE
> GEMINI FLASH"

The organism scoring scripts judged with `claude-haiku-4-5`. The seat is now
`gemini-flash-lite-latest`, named in config rather than written into a script.
`tests/test_no_hardcoded_judge_seat.py` fails if any script hardcodes a judge
model again.

The paper's existing organism numbers were produced by the previous seat. They
are not silently restated under the new one: re-judging is its own run, and the
owner decides when it happens.

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

Published private, hash-verified against the local checkpoint. The card states
that the audit numbers were measured on a sibling adapter rather than on the
uploaded file.
