# src/persona

We read audited replies into role-persona and emotion-concept vector spaces, test whether user groups separate, and steer a residual-stream direction to test whether a treatment direction is causal.

The package holds a fixed activation encoder, a cast of persona and emotion directions, a matched-reply loader, a group-separability test, and a steering hook. We run it as a side probe on the stage 4 replies and stage 5 verdicts, always whitened against the base model the audit already uses as reference. A caller loads matched replies with `load_matched_replies`, encodes them with `encode_replies`, whitens the base cloud with `fit_base_whitening`, and tests separation with `group_separability`; `steer` supplies the causal check.

## Files

| File | Responsibility |
|---|---|
| `emotion_concept_vectors.py` | Build grand-mean-centred, neutral-denoised emotion direction vectors at one layer from evocative stories. |
| `matched_reply_loader.py` | Load up to a cap of matched (target, base) samples per cell, each with its prompt, both replies, and behavior verdicts. |
| `persona_activation_encoder.py` | Load a fixed causal-LM probe and read the mean residual-stream vector over each reply's tokens at a chosen layer. |
| `persona_group_analysis.py` | Whiten against the base cloud, project replies onto role vectors, and test group separability with a label-shuffle null. |
| `residual_steering_hook.py` | Register a forward hook that adds a coefficient times a unit direction, or projects it out, during generation. |
| `role_persona_vectors.py` | Build a cast of persona role vectors by having the encoder enact each role, and form the assistant axis. |
