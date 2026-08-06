# src/runner

src/runner is stage 4 of the pipeline, where we collect replies from the target model and its base to every matched prompt through a shared chat-backend interface.

The package holds one chat backend per model seat. Local HuggingFace generation and vLLM cover the target and reference, and the Anthropic and OpenAI APIs cover the elicitor, extractor, and judge seats. Stage 2 hands us matched prompts and stage 5 scores what we return, so we sample both arms under identical settings and record a missing sample as an empty string rather than dropping it. Callers reach a backend through `resolve_backend`, which maps a seat kind to a backend and imports that backend's dependencies only when the seat is used.

## Files

| File | Responsibility |
|---|---|
| `local_transformers_backend_padded_pass.py` | The left-padded forward pass behind ``LocalTransformersBackend``. |
| `local_transformers_backend_placement.py` | Device and dtype selection for the local transformers backend. |
| response_sampling.py | Stage 4 sampler: draws the target and base replies on every candidate's prompt set under each system prompt, recording refusals and failures rather than dropping them. |
| `model_backend_router.py` | Define the `ChatBackend` protocol and resolve a seat kind to its backend, importing heavy or credentialed dependencies inside the branch that needs them. |
| `local_transformers_backend.py` | Sample a local instruct checkpoint with HuggingFace transformers, batching across prompts under mandatory left padding and returning an empty string for a sample the model did not produce. |
| `vllm_batch_backend.py` | Sample a local checkpoint through vLLM continuous batching for high throughput, serving both LoRA arms from one engine. |
| `adapter_arm_view.py` | Wrap one LoRA-capable backend and pin every call to a single arm, the target with the adapter attached or the base with it detached. |
| `anthropic_chat_backend.py` | Wrap the Anthropic Messages API for the elicitor and extractor seats, raising on a refusal instead of dropping the sample. |
| `openai_chat_backend.py` | Wrap the OpenAI Chat Completions API for the judge seat, adapting a rejected parameter from the returned error and raising on a refusal or empty completion. |
| `auditbench_identity_prompt.py` | Hold the fictitious-model system prompt the AuditBench organisms were trained under, sent unchanged to both arms. |
