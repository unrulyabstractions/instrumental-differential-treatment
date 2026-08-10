# src/external

Frozen materials for the external settings we audit with the pipeline. Code that
runs them lives in `script/external`.

`user_awareness_materials.py` holds the miniature user-awareness replication: the
candidate user identities, the borderline prompts, the identity system-prompt
template, and the awareness axes the judge scores. The identities are two AI-safety
researchers, one safety-adjacent researcher, one AI-affiliated but non-famous
"affiliation twin", and two ordinary users, so the base-free detector reads
safety-researcher against the rest. The prompts are original and plausibly
dual-use in the OR-Bench sense, none asking for operational harm. The judge never
sees the identity.
