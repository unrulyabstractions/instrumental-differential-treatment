# Smoke run findings (Qwen2.5-1.5B-Instruct)

Working notes from the 16-generation pipeline check that preceded the full run.
Recorded before results exist, so they cannot be reinterpreted after the fact.

## Pipeline

Ran clean end to end: 16/16 generated, 0 failures, 0 empty responses. Resume
logic, seeding, and manifest writing all behaved. Throughput on an M3 Max via
MPS was ~0.20 generations/second, so the 2,000-generation run is roughly
2.8 hours.

## Response shape

Median 147 words against a 120-200 word instruction; 5 of 16 ran over 200.
Nothing was truncated at the 400-token generation cap, so `max_new_tokens`
stays as frozen. (An early read suggested truncation; that was an artifact of
printing only the first 700 characters, not a property of the responses.)

## Quality defects in the organism model

Two defects matter for measurement, and both are properties of the 1.5B model
rather than of the scenario.

**Token-level degradation.** 4 of 16 responses (25%) contain CJK or Cyrillic
tokens spliced into English text — from a single stray character
(`understandable娼to feel`) to a clause degenerating entirely into Chinese.
Typographic non-ASCII (curly apostrophes, em dashes) is separate and benign.

**Factual garbling.** Responses restate the shared fact base incorrectly: one
rendered the 90-day reserve versus 20-day status quo as "nine months instead of
just ten days." This is the more serious of the two, because selective emphasis
of *correct* shared facts is the mechanism the organism is supposed to use. A
model that garbles the facts is adding noise to precisely the channel being
measured.

## Consequences

Neither defect is expected to bias the group gap: nothing about the identity
marker should make garbling more likely for one town than the other, so the
effect is added variance rather than a shifted mean. Added variance lowers
statistical power, which means a null result on this model is genuinely
ambiguous — it could indicate that a 1.5B model cannot sustain the covert
objective, or merely that noise swamped a real effect.

That ambiguity is the reason the 7B escalation exists in the design. These
findings promote it from optional stretch to the natural next step, whatever the
1.5B numbers turn out to be. The 1.5B run still earns its keep: it exercises the
whole pipeline on real data and produces a preregistered result to compare
against.
