"""The required provenance keys are pinned here, independently of the code.

The owner asked that every run record its sampling settings and judge snapshot
(STANDING_INSTRUCTIONS.md B77 context, 2026-11-15). Other tests import the key
lists from the code, so dropping a key there would pass silently. This test
keeps its own copy: removing any key from the code's lists fails here.
"""

from src.common.row_provenance import REPLY_PROVENANCE_KEYS, VERDICT_PROVENANCE_KEYS

PINNED_REPLY = {
    "temperature", "top_p", "max_tokens", "seed", "seed_label", "finish_reason",
    "prompt_tokens", "completion_tokens", "bos_count", "backend_kind", "engine",
    "engine_version", "model_id", "adapter", "sampled_at_utc",
}
PINNED_VERDICT = {
    "judge", "judge_model_snapshot", "reasoning_effort", "system_prompt_sha256",
    "level", "judged_at_utc",
}


def test_reply_keys_cover_the_pinned_set() -> None:
    missing = PINNED_REPLY - set(REPLY_PROVENANCE_KEYS)
    assert not missing, f"reply provenance keys dropped from the code: {sorted(missing)}"


def test_verdict_keys_cover_the_pinned_set() -> None:
    missing = PINNED_VERDICT - set(VERDICT_PROVENANCE_KEYS)
    assert not missing, f"verdict provenance keys dropped from the code: {sorted(missing)}"
