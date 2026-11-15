"""Every reply row and every verdict row carries its full provenance.

The collector (``sample_prompt_sets``) and both judge paths (``score_responses``
and ``fold_rows``) must write, on every row, the settings that produced it, and
a field a backend cannot supply must be null with a reason. These tests run the
real code paths against the fake backends the suite already uses, read the
rows back from disk, and fail on any missing key. A second group breaks the
provenance on purpose and asserts nothing reaches disk. A third checks that
rows written before the schema still read. No network, no model, no ``out/``.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import types
from pathlib import Path

import pytest
import torch

from src.common.row_provenance import (NULL_REASONS, REPLY_PROVENANCE_KEYS,
                                       RUN_REPLY_KEYS, VERDICT_PROVENANCE_KEYS,
                                       ProvenanceError, SampleMeta,
                                       append_reply_rows, append_verdict_rows,
                                       check_reply_row, check_verdict_row,
                                       provenance_of, sha256_text)
from src.runner import response_sampling
from src.runner.adapter_arm_view import AdapterArmView
from src.runner.response_sampling import sample_prompt_sets
from src.score import batch_judge_fill as bj
from src.score import verdict_panel
from src.score.judge_prompts import judge_system_prompt
from src.score.verdict_panel import score_responses

ROOT = Path(__file__).resolve().parents[2]
PROMPT_SETS = {
    "alice": [{"instruction_id": "t1", "text": "help alice one"}],
    "bob": [{"instruction_id": "t1", "text": "help bob one"}],
}
AXES = [{"axis_id": f"axis_{n:03d}", "question": f"Does it do {n}?"} for n in range(3)]


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _assert_reply_rows_complete(rows: list[dict]) -> None:
    assert rows, "the collector wrote nothing"
    for row in rows:
        missing = [k for k in REPLY_PROVENANCE_KEYS if k not in row]
        assert not missing, f"reply row lacks {missing}"
        for key in REPLY_PROVENANCE_KEYS:
            if row[key] is None:
                assert row[NULL_REASONS].get(key), f"null {key} has no reason"
        assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00$", row["sampled_at_utc"])
        check_reply_row(row)


def _assert_verdict_rows_complete(rows: list[dict]) -> None:
    assert rows, "the judge wrote nothing"
    for row in rows:
        missing = [k for k in VERDICT_PROVENANCE_KEYS if k not in row]
        assert not missing, f"verdict row lacks {missing}"
        for key in VERDICT_PROVENANCE_KEYS:
            if row[key] is None:
                assert row[NULL_REASONS].get(key), f"null {key} has no reason"
        assert re.fullmatch(r"[0-9a-f]{64}", row["system_prompt_sha256"])
        check_verdict_row(row)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class TextOnlyMany:
    """A backend written before the schema: bare strings, no provenance()."""

    name = "fake:many"

    def generate(self, system, user, max_new_tokens=512):
        return f"reply::{user}"

    def generate_many(self, requests, max_new_tokens=512):
        return [[f"reply::{u}::{i}" for i in range(n)] for _, u, n in requests]


class TextOnlySingle:
    name = "fake:single"

    def generate(self, system, user, max_new_tokens=512):
        return f"reply::{user}"


class TextOnlyBatch(TextOnlySingle):
    name = "fake:batch"

    def generate_batch(self, system, user, n, max_new_tokens=512):
        return [f"reply::{user}::{i}" for i in range(n)]


class DetailedMany:
    """A backend that reports everything, as the real ones do."""

    name = "fake:detailed"

    def provenance(self):
        return {"backend_kind": "fake", "engine": "fake-engine", "engine_version": "9.9",
                "model_id": "org/model", "adapter": "org/adapter", "temperature": 0.8,
                "top_p": 0.95, "seed": 7, "seed_label": "label", NULL_REASONS: {}}

    def generate(self, system, user, max_new_tokens=512):
        return "x"

    def generate_many(self, requests, max_new_tokens=512):
        raise AssertionError("the detailed method must be preferred")

    def generate_many_detailed(self, requests, max_new_tokens=512):
        return [[SampleMeta(f"r{i}", finish_reason="stop", prompt_tokens=11,
                            completion_tokens=3, bos_count=1) for i in range(n)]
                for _, _, n in requests]


class RecordingJudge:
    name = "test:recording"

    def generate(self, system, user, max_new_tokens=512):
        ids = re.findall(r"^\d+\. (axis_\d{3}):", user, flags=re.M)
        return json.dumps({a: "YES" for a in ids})


class SnapshotJudge(RecordingJudge):
    name = "openai:gpt-test"

    def provenance(self):
        return {"backend_kind": "openai", "model_id": "gpt-test",
                "reasoning_effort": "low", NULL_REASONS: {}}

    def generate_detailed(self, system, user, max_new_tokens=512):
        return SampleMeta(self.generate(system, user, max_new_tokens),
                          finish_reason="stop", model_snapshot="gpt-test-2026-01-01")


def _responses_file(tmp_path: Path) -> Path:
    path = tmp_path / "responses.jsonl"
    sample_prompt_sets(TextOnlyMany(), PROMPT_SETS, 2, path, show_progress=False)
    return path


# ---------------------------------------------------------------------------
# The collector writes every key on every row
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("backend", [TextOnlyMany(), TextOnlySingle(), TextOnlyBatch(),
                                     DetailedMany()], ids=lambda b: b.name)
def test_every_collector_path_writes_every_reply_key(tmp_path, backend):
    path = tmp_path / "responses.jsonl"
    stats = sample_prompt_sets(backend, PROMPT_SETS, 3, path, max_new_tokens=17,
                               batch_size=2, show_progress=False)
    rows = _rows(path)
    assert len(rows) == 6
    _assert_reply_rows_complete(rows)
    assert all(r["max_tokens"] == 17 for r in rows)
    # The run manifest carries the same settings once.
    assert set(RUN_REPLY_KEYS) | {"max_tokens", NULL_REASONS} <= set(stats.provenance)
    assert stats.provenance["max_tokens"] == 17


def test_a_detailed_backend_has_its_values_recorded_not_nulled(tmp_path):
    path = tmp_path / "responses.jsonl"
    sample_prompt_sets(DetailedMany(), PROMPT_SETS, 2, path, max_new_tokens=9,
                       show_progress=False)
    row = _rows(path)[0]
    assert {k: row[k] for k in RUN_REPLY_KEYS} == {
        "backend_kind": "fake", "engine": "fake-engine", "engine_version": "9.9",
        "model_id": "org/model", "adapter": "org/adapter", "temperature": 0.8,
        "top_p": 0.95, "seed": 7, "seed_label": "label"}
    assert (row["finish_reason"], row["prompt_tokens"], row["completion_tokens"],
            row["bos_count"]) == ("stop", 11, 3, 1)
    assert row[NULL_REASONS] == {}


def test_a_text_only_backend_gets_nulls_with_reasons(tmp_path):
    path = tmp_path / "responses.jsonl"
    sample_prompt_sets(TextOnlyMany(), PROMPT_SETS, 1, path, show_progress=False)
    row = _rows(path)[0]
    assert row["backend_kind"] == "fake" and row["model_id"] == "many"
    assert row["finish_reason"] is None and "text only" in row[NULL_REASONS]["finish_reason"]
    assert row["temperature"] is None and "provenance()" in row[NULL_REASONS]["temperature"]


def test_a_failed_submission_still_writes_every_key(tmp_path):
    class Broken(TextOnlyMany):
        def generate_many(self, requests, max_new_tokens=512):
            raise RuntimeError("synthetic crash")

    path = tmp_path / "responses.jsonl"
    sample_prompt_sets(Broken(), PROMPT_SETS, 2, path, show_progress=False)
    rows = _rows(path)
    assert all(r["failed"] for r in rows)
    _assert_reply_rows_complete(rows)
    assert "synthetic crash" in rows[0][NULL_REASONS]["finish_reason"]


def test_the_base_arm_records_the_adapter_as_detached(tmp_path):
    class LoraEngine(DetailedMany):
        def generate_many_detailed(self, requests, max_new_tokens=512, use_adapter=True):
            self.used = use_adapter
            return super().generate_many_detailed(requests, max_new_tokens)

    engine = LoraEngine()
    for tag, use in (("target", True), ("base", False)):
        path = tmp_path / f"responses_{tag}.jsonl"
        sample_prompt_sets(AdapterArmView(engine, use, tag), PROMPT_SETS, 1, path,
                           show_progress=False)
        rows = _rows(path)
        _assert_reply_rows_complete(rows)
        assert engine.used is use
        if use:
            assert rows[0]["adapter"] == "org/adapter"
        else:
            assert rows[0]["adapter"] is None
            assert "base arm" in rows[0][NULL_REASONS]["adapter"]


# ---------------------------------------------------------------------------
# The real backends report their own values
# ---------------------------------------------------------------------------

@pytest.fixture()
def vllm_module(monkeypatch):
    """The vLLM backend imported against a stub vllm package."""
    fake = types.ModuleType("vllm")
    fake.__version__ = "0.0-test"
    fake.LLM = object
    fake.SamplingParams = lambda **kw: types.SimpleNamespace(**kw)
    fake.TokensPrompt = dict
    lora = types.ModuleType("vllm.lora")
    request = types.ModuleType("vllm.lora.request")
    request.LoRARequest = lambda *a: a
    lora.request = request
    fake.lora = lora
    monkeypatch.setitem(sys.modules, "vllm", fake)
    monkeypatch.setitem(sys.modules, "vllm.lora", lora)
    monkeypatch.setitem(sys.modules, "vllm.lora.request", request)
    sys.modules.pop("src.runner.vllm_batch_backend", None)
    yield importlib.import_module("src.runner.vllm_batch_backend")
    sys.modules.pop("src.runner.vllm_batch_backend", None)


class _Tok:
    bos_token_id = 1

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        return "<s>" + "|".join(m["content"] for m in messages)

    def encode(self, text, add_special_tokens=True):
        return [1] + [ord(c) for c in text[3:]]


class _Engine:
    def generate(self, prompts, params, use_tqdm=False, lora_request=None):
        return [types.SimpleNamespace(outputs=[
            types.SimpleNamespace(text=f"s{i} ", finish_reason="length",
                                  token_ids=[5] * 4) for i in range(p.n)])
            for p in params]


def test_vllm_rows_carry_engine_version_finish_reason_and_one_bos(tmp_path, vllm_module):
    backend = object.__new__(vllm_module.VllmBatchBackend)
    backend._model_name, backend._temperature, backend._top_p = "org/base", 0.8, 0.95
    backend._lora_path, backend._lora_request, backend._seed_label = None, None, "lbl"
    backend._llm, backend._tokenizer = _Engine(), _Tok()
    path = tmp_path / "responses.jsonl"
    sample_prompt_sets(backend, PROMPT_SETS, 2, path, max_new_tokens=4, show_progress=False)
    rows = _rows(path)
    _assert_reply_rows_complete(rows)
    row = rows[0]
    assert (row["backend_kind"], row["engine"], row["engine_version"]) == ("vllm", "vllm", "0.0-test")
    assert (row["finish_reason"], row["completion_tokens"], row["bos_count"]) == ("length", 4, 1)
    assert row["temperature"] == 0.8 and row["top_p"] == 0.95 and row["seed_label"] == "lbl"
    assert isinstance(row["seed"], int)
    assert row["adapter"] is None and row[NULL_REASONS]["adapter"]


def test_transformers_rows_carry_finish_reason_and_token_counts(tmp_path):
    from tests.runner.test_transformers_batching import FakeModel, FakeTokenizer, _backend

    tokenizer = FakeTokenizer()
    backend = _backend(tokenizer, FakeModel(tokenizer))
    backend._model_name, backend._seed_label = "org/local", "lbl"
    path = tmp_path / "responses.jsonl"
    sample_prompt_sets(backend, PROMPT_SETS, 2, path, max_new_tokens=1, show_progress=False)
    rows = _rows(path)
    _assert_reply_rows_complete(rows)
    row = rows[0]
    assert row["backend_kind"] == "transformers" and row["engine_version"]
    # The fake model emits one token and the cap is one, so the row hit the cap.
    assert (row["finish_reason"], row["completion_tokens"]) == ("length", 1)
    assert row["prompt_tokens"] == len("user=help alice one".split(" "))
    # The fake tokenizer defines no BOS, so the count is null with that reason.
    assert row["bos_count"] is None and "bos_token_id" in row[NULL_REASONS]["bos_count"]


def test_api_backends_report_usage_and_the_dated_snapshot():
    from src.runner.anthropic_chat_backend import AnthropicChatBackend
    from src.runner.openai_chat_backend import OpenAiChatBackend
    import threading

    class Messages:
        def create(self, **kw):
            return types.SimpleNamespace(
                stop_reason="end_turn", model="claude-test-20260101",
                usage=types.SimpleNamespace(input_tokens=12, output_tokens=5),
                content=[types.SimpleNamespace(type="text", text="hi")])

    a = AnthropicChatBackend.__new__(AnthropicChatBackend)
    a._model_name, a._client = "claude-test", types.SimpleNamespace(messages=Messages())
    meta = a.generate_detailed("s", "u", 10)
    assert (meta.text, meta.finish_reason, meta.prompt_tokens, meta.completion_tokens,
            meta.model_snapshot) == ("hi", "end_turn", 12, 5, "claude-test-20260101")
    assert meta.null_reasons["bos_count"]

    class Completions:
        def create(self, **kw):
            msg = types.SimpleNamespace(content="ok", refusal=None)
            return types.SimpleNamespace(
                model="gpt-test-2026-01-01",
                choices=[types.SimpleNamespace(message=msg, finish_reason="stop")],
                usage=types.SimpleNamespace(prompt_tokens=8, completion_tokens=2))

    o = OpenAiChatBackend.__new__(OpenAiChatBackend)
    o._model_name = "gpt-test"
    o._client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions()))
    o._temperature, o._reasoning_effort, o._usage_sink = None, "low", None
    o._token_param, o._token_param_flipped, o._lock = "max_completion_tokens", False, threading.Lock()
    meta = o.generate_detailed("s", "u", 10)
    assert (meta.finish_reason, meta.prompt_tokens, meta.completion_tokens,
            meta.model_snapshot) == ("stop", 8, 2, "gpt-test-2026-01-01")
    prov = o.provenance()
    assert prov["reasoning_effort"] == "low" and prov["temperature"] is None
    assert prov[NULL_REASONS]["temperature"]


# ---------------------------------------------------------------------------
# Both judge paths write every key on every row
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("judge", [RecordingJudge(), SnapshotJudge()], ids=lambda j: j.name)
def test_the_live_judge_writes_every_verdict_key(tmp_path, judge):
    verdicts = tmp_path / "verdicts.jsonl"
    stats = score_responses(judge, 2, "dom", "act", AXES, _responses_file(tmp_path),
                            verdicts, workers=1, show_progress=False)
    rows = _rows(verdicts)
    _assert_verdict_rows_complete(rows)
    system = judge_system_prompt(2, "dom", "act")
    assert all(r["system_prompt_sha256"] == sha256_text(system) for r in rows)
    assert all(r["level"] == 2 and r["judge"] == judge.name for r in rows)
    if isinstance(judge, SnapshotJudge):
        assert all(r["judge_model_snapshot"] == "gpt-test-2026-01-01" for r in rows)
        assert all(r["reasoning_effort"] == "low" for r in rows)
        assert stats.provenance["judge_model_snapshots"] == ["gpt-test-2026-01-01"]
    # The scoring manifest carries the same settings once.
    for key in ("judge", "reasoning_effort", "system_prompt_sha256", "level"):
        assert key in stats.provenance
    assert stats.provenance["system_prompt_sha256"] == sha256_text(system)


def test_the_batch_fold_writes_every_verdict_key():
    system = judge_system_prompt(2, "dom", "act")
    rows = [{"principal": "alice", "prompt_id": "p1", "instruction_id": "t1",
             "system_id": "none", "s": 0, "text": "some reply"}]
    first = bj.plan_first_pass({"seat": rows}, AXES, system)
    replies = {c.custom_id: json.dumps({a: "NO" for a in c.axis_ids}) for c in first}
    for snapshots in (None, {c.custom_id: "claude-test-20260101" for c in first}):
        out, _ = bj.fold_rows({"seat": rows}, first, replies, [], {}, "anthropic:x", 2,
                              snapshots=snapshots)
        _assert_verdict_rows_complete(out["seat"])
        row = out["seat"][0]
        assert row["system_prompt_sha256"] == sha256_text(system)
        assert row["judge_model_snapshot"] == (snapshots and "claude-test-20260101")


# ---------------------------------------------------------------------------
# No code path can write a row without its provenance
# ---------------------------------------------------------------------------

def test_the_writers_refuse_a_missing_key_and_an_unexplained_null(tmp_path):
    path = tmp_path / "rows.jsonl"
    with pytest.raises(ProvenanceError, match="missing provenance keys"):
        append_reply_rows(path, [{"prompt_id": "p", "s": 0, "text": "t"}])
    with pytest.raises(ProvenanceError, match="missing provenance keys"):
        append_verdict_rows(path, [{"prompt_id": "p", "s": 0, "judge": "j"}])
    good = {k: 1 for k in REPLY_PROVENANCE_KEYS} | {"provenance_schema": 1, NULL_REASONS: {}}
    with pytest.raises(ProvenanceError, match="no reason"):
        append_reply_rows(path, [{**good, "temperature": None}])
    assert not path.exists(), "a refused row must not reach disk"


def test_the_collector_cannot_write_a_row_missing_a_key(tmp_path, monkeypatch):
    real = response_sampling.reply_provenance

    def drops_seed(*args, **kwargs):
        out = real(*args, **kwargs)
        del out["seed"]
        return out

    monkeypatch.setattr(response_sampling, "reply_provenance", drops_seed)
    for backend in (TextOnlyMany(), TextOnlySingle()):
        path = tmp_path / f"{backend.name}.jsonl"
        with pytest.raises(ProvenanceError, match="seed"):
            sample_prompt_sets(backend, PROMPT_SETS, 1, path, show_progress=False)
        assert not path.exists() or not path.read_text().strip()


def test_the_live_judge_cannot_write_a_row_missing_a_key(tmp_path, monkeypatch):
    real = verdict_panel._score_one

    def drops_snapshot(*args, **kwargs):
        out = real(*args, **kwargs)
        del out["judge_model_snapshot"]
        return out

    monkeypatch.setattr(verdict_panel, "_score_one", drops_snapshot)
    responses = _responses_file(tmp_path)
    verdicts = tmp_path / "verdicts.jsonl"
    with pytest.raises(ProvenanceError, match="judge_model_snapshot"):
        score_responses(RecordingJudge(), 2, "", "", AXES, responses, verdicts,
                        workers=1, show_progress=False)
    assert not verdicts.exists() or not verdicts.read_text().strip()


def test_the_batch_fold_cannot_return_a_row_with_an_unexplained_null(monkeypatch):
    monkeypatch.setattr(bj, "sha256_text", lambda text: None)
    rows = [{"principal": "a", "prompt_id": "p", "instruction_id": "t", "s": 0, "text": "r"}]
    first = bj.plan_first_pass({"seat": rows}, AXES, "sys")
    replies = {c.custom_id: json.dumps({a: "YES" for a in c.axis_ids}) for c in first}
    with pytest.raises(ProvenanceError, match="system_prompt_sha256"):
        bj.fold_rows({"seat": rows}, first, replies, [], {}, "j", 2)


@pytest.mark.parametrize("module", ["src/runner/response_sampling.py",
                                    "src/score/verdict_panel.py"])
def test_the_shared_paths_hold_no_unchecked_writer(module):
    """Rows reach disk only through the checking writers."""
    source = (ROOT / module).read_text()
    assert "append_jsonl" not in source
    assert ("append_reply_rows" in source) or ("append_verdict_rows" in source)


# ---------------------------------------------------------------------------
# Rows written before the schema still read
# ---------------------------------------------------------------------------

def test_old_rows_without_provenance_still_resume_and_score(tmp_path):
    responses = tmp_path / "responses.jsonl"
    old = [{"principal": "alice", "prompt_id": "alice__none::t1", "instruction_id": "none::t1",
            "system_id": "none", "s": 0, "refused": False, "failed": False, "text": "old reply"}]
    responses.write_text("".join(json.dumps(r) + "\n" for r in old))
    stats = sample_prompt_sets(TextOnlyMany(), PROMPT_SETS, 1, responses, show_progress=False)
    assert stats.skipped_existing == 1 and stats.generated == 1
    assert provenance_of(_rows(responses)[0]) == {k: None for k in REPLY_PROVENANCE_KEYS}

    verdicts = tmp_path / "verdicts.jsonl"
    old_verdict = {"principal": "alice", "prompt_id": "alice__none::t1",
                   "instruction_id": "none::t1", "system_id": "none", "s": 0,
                   "judge": "test:recording", "level": 2, "verdicts": {}}
    verdicts.write_text(json.dumps(old_verdict) + "\n")
    st = score_responses(RecordingJudge(), 2, "", "", AXES, responses, verdicts,
                         workers=1, show_progress=False)
    assert st.skipped_existing == 1 and st.written == 1
    assert provenance_of(_rows(verdicts)[0], VERDICT_PROVENANCE_KEYS)["judged_at_utc"] is None
    _assert_verdict_rows_complete(_rows(verdicts)[1:])
