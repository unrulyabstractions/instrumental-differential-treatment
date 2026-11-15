"""Per-row provenance: the settings that produced every reply and every verdict.

A reply row once carried only its ids, its text, and two flags, and a verdict
row only the judge alias. The sampling temperature, the engine version, the
dated model snapshot behind an alias, and the token counts that would show a
doubled BOS or a truncated reply lived nowhere on disk. A row whose settings
are unrecorded cannot be audited later, so this module makes them mandatory.

The rule is simple. Every key in ``REPLY_PROVENANCE_KEYS`` or
``VERDICT_PROVENANCE_KEYS`` is present on every row the shared writers append.
A key whose value the backend cannot supply is written as null, and the reason
goes into ``provenance_null_reasons`` under the same key. A null with no reason
is refused, so a backend cannot drop a field by accident. The writers
``append_reply_rows`` and ``append_verdict_rows`` check each row before any
byte reaches disk.

Readers stay lenient: rows written before this schema lack every new key, and
``provenance_of`` returns None for each missing one instead of raising.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from src.common.file_io import append_jsonl

__all__ = [
    "PROVENANCE_SCHEMA", "NULL_REASONS", "RUN_REPLY_KEYS", "SAMPLE_REPLY_KEYS",
    "REPLY_PROVENANCE_KEYS", "VERDICT_PROVENANCE_KEYS", "ProvenanceError",
    "SampleMeta", "utc_now", "sha256_text", "fill_with_reasons",
    "backend_run_provenance", "text_only_meta", "failed_meta", "reply_provenance",
    "check_reply_row", "check_verdict_row", "append_reply_rows",
    "append_verdict_rows", "provenance_of", "joined_snapshot",
]

#: Bumped when a key is added; rows written before the schema carry no value.
PROVENANCE_SCHEMA = 1
NULL_REASONS = "provenance_null_reasons"

#: Settings fixed for a backend across a run, recorded on each row too.
RUN_REPLY_KEYS: tuple[str, ...] = (
    "backend_kind", "engine", "engine_version", "model_id", "adapter",
    "temperature", "top_p", "seed", "seed_label",
)
#: Facts that differ per sample and only the backend's own response knows.
SAMPLE_REPLY_KEYS: tuple[str, ...] = (
    "finish_reason", "prompt_tokens", "completion_tokens", "bos_count",
)
REPLY_PROVENANCE_KEYS: tuple[str, ...] = (
    RUN_REPLY_KEYS + ("max_tokens",) + SAMPLE_REPLY_KEYS + ("sampled_at_utc",)
)
VERDICT_PROVENANCE_KEYS: tuple[str, ...] = (
    "judge", "judge_model_snapshot", "reasoning_effort", "system_prompt_sha256",
    "level", "judged_at_utc",
)


class ProvenanceError(ValueError):
    """A row is missing a provenance key, or carries a null with no reason."""


@dataclass(frozen=True)
class SampleMeta:
    """One generation and what the backend reported about it."""

    text: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    bos_count: int | None = None
    model_snapshot: str | None = None
    null_reasons: dict[str, str] = field(default_factory=dict)


def utc_now() -> str:
    """An ISO-8601 UTC timestamp with milliseconds."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fill_with_reasons(values: dict, reasons: dict, keys: Iterable[str],
                      default_reason: str) -> tuple[dict, dict]:
    """Every key present; every null explained.

    A key absent from ``values`` becomes null with ``default_reason``. A key
    present as null keeps its own reason if one was given, else the default.
    """
    out, why = {}, {}
    for key in keys:
        value = values.get(key)
        out[key] = value
        if value is None:
            why[key] = reasons.get(key) or default_reason
    return out, why


def backend_run_provenance(backend) -> dict:
    """The run-level settings of a backend, with a reason for every null.

    A backend that offers ``provenance()`` reports its own settings. One that
    does not (a test fake, a wrapper written before this schema) still yields
    every key: the kind and model come from its ``name``, the rest are null
    with a reason naming the backend.
    """
    name = getattr(backend, "name", type(backend).__name__)
    if hasattr(backend, "provenance"):
        reported = dict(backend.provenance())
        default = f"backend {name} did not report this setting"
    else:
        kind, _, model = str(name).partition(":")
        reported = {"backend_kind": kind or None, "model_id": model or None}
        default = f"backend {name} exposes no provenance()"
    reasons = dict(reported.pop(NULL_REASONS, {}) or {})
    extra = {k: v for k, v in reported.items() if k not in RUN_REPLY_KEYS}
    values, why = fill_with_reasons(reported, reasons, RUN_REPLY_KEYS, default)
    for key, value in extra.items():
        values[key] = value
        if value is None:
            why[key] = reasons.get(key) or default
    return {**values, NULL_REASONS: why}


def text_only_meta(text: str, backend_name: str) -> SampleMeta:
    """Metadata for a backend that returns bare strings."""
    reason = f"backend {backend_name} returns text only, no per-sample metadata"
    return SampleMeta(text, null_reasons={k: reason for k in SAMPLE_REPLY_KEYS + ("model_snapshot",)})


def failed_meta(reason: str) -> SampleMeta:
    """Metadata for a sample the backend never returned."""
    return SampleMeta("", null_reasons={k: reason for k in SAMPLE_REPLY_KEYS + ("model_snapshot",)})


def reply_provenance(run: dict, max_tokens: int, meta: SampleMeta,
                     sampled_at_utc: str) -> dict:
    """The provenance fields of one reply row."""
    sample = {"finish_reason": meta.finish_reason, "prompt_tokens": meta.prompt_tokens,
              "completion_tokens": meta.completion_tokens, "bos_count": meta.bos_count}
    values, why = fill_with_reasons(sample, meta.null_reasons, SAMPLE_REPLY_KEYS,
                                    "backend did not report this field for the sample")
    run_values = {k: v for k, v in run.items() if k != NULL_REASONS}
    reasons = {**{k: v for k, v in (run.get(NULL_REASONS) or {}).items()
                  if run_values.get(k) is None}, **why}
    out = {**run_values, **values, "max_tokens": int(max_tokens),
           "sampled_at_utc": sampled_at_utc, "provenance_schema": PROVENANCE_SCHEMA,
           NULL_REASONS: reasons}
    return out


def _check(row: dict, keys: Iterable[str], what: str) -> None:
    missing = [k for k in keys if k not in row]
    if NULL_REASONS not in row or not isinstance(row[NULL_REASONS], dict):
        missing.append(NULL_REASONS)
    if "provenance_schema" not in row:
        missing.append("provenance_schema")
    if missing:
        raise ProvenanceError(f"{what} row {row.get('prompt_id')!r} s={row.get('s')!r} "
                              f"is missing provenance keys {missing}")
    reasons = row[NULL_REASONS]
    unexplained = [k for k in keys if row[k] is None
                   and not (isinstance(reasons.get(k), str) and reasons[k].strip())]
    if unexplained:
        raise ProvenanceError(f"{what} row {row.get('prompt_id')!r} s={row.get('s')!r} "
                              f"has nulls with no reason: {unexplained}")


def check_reply_row(row: dict) -> None:
    _check(row, REPLY_PROVENANCE_KEYS, "reply")


def check_verdict_row(row: dict) -> None:
    _check(row, VERDICT_PROVENANCE_KEYS, "verdict")


def append_reply_rows(path, rows: list[dict]):
    """The only writer of reply rows: checks every row, then appends all."""
    for row in rows:
        check_reply_row(row)
    return append_jsonl(path, rows)


def append_verdict_rows(path, rows: list[dict]):
    """The only writer of verdict rows: checks every row, then appends all."""
    for row in rows:
        check_verdict_row(row)
    return append_jsonl(path, rows)


def provenance_of(row: dict, keys: Iterable[str] = REPLY_PROVENANCE_KEYS) -> dict[str, Any]:
    """The provenance fields of any row, None where an old row has none."""
    return {k: row.get(k) for k in keys}


def joined_snapshot(snapshots: Iterable[str | None]) -> str | None:
    """One snapshot string for the calls behind a row; several are comma-joined."""
    seen = sorted({s for s in snapshots if s})
    return ",".join(seen) if seen else None
