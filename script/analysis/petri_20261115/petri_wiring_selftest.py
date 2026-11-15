"""Free end-to-end check of the B73 wiring: no paid call, no box.

    tmp/petri_env/bin/python -m script.analysis.petri_20261115.petri_wiring_selftest

A local stub speaks the vLLM endpoints the runs use (/v1/models, /tokenize, /v1/chat/completions) and records
every request. Petri's audit task then runs with Inspect's mockllm as a scripted auditor (it stages a system
message, sends one user message, ends the conversation) and as a scripted judge (fixed scores), against the
target model exactly as petri_run_cell.py builds it. The check fails unless:
  * for each deployment the target received the registered system prompt (court: the clean prompt; PRISM-4:
    the wrapped auditor text; free: the auditor text) and the registered sampling and BOS fields;
  * the auditor saw the deployment note (court and PRISM-4) or Petri's default message (free);
  * the judge's prompt holds the system prompt the target read;
  * petri_readings parses the judge's scores and gives D, N and the registered cell reading;
  * every FLAG_DIMS name is a Petri default dimension.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from inspect_ai import eval as inspect_eval  # noqa: E402
from inspect_ai.log import read_eval_log  # noqa: E402
from inspect_ai.model import GenerateConfig, ModelOutput, get_model  # noqa: E402
from inspect_ai.tool import ToolCall  # noqa: E402
from inspect_petri import audit  # noqa: E402
from inspect_petri._judge.dimensions import load_dimensions  # noqa: E402

from script.analysis.petri_20261115 import petri_targets as T  # noqa: E402
from script.analysis.petri_20261115.petri_readings import FLAG_DIMS, cell_reading, read_logs  # noqa: E402

SEEN: list[dict] = []


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send({"object": "list", "data": [{"id": n, "object": "model"} for n in ("tgt-a", "tgt-b", "tgt-c")]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"path": self.path, "body": req})
        if self.path == "/tokenize":
            lead = [128000, 128000] if req.get("add_special_tokens") else [128000]
            return self._send({"count": 5, "max_model_len": 32768, "tokens": lead + [1, 2, 3]})
        self._send({"id": "x", "object": "chat.completion", "created": 0, "model": req["model"],
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": "Happy to help with that."}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16}})


def _auditor():
    calls = [ToolCall(id="c1", function="set_system_message", arguments={"system_message": "AUDITOR STAGED TEXT"}),
             ToolCall(id="c2", function="send_message", arguments={"message": "As a Cupertino resident: hi"}),
             ToolCall(id="c3", function="resume", arguments={})]
    yield ModelOutput.for_tool_call("mockllm/model", calls[0].function, calls[0].arguments, tool_call_id="c1")
    out = ModelOutput.for_tool_call("mockllm/model", "send_message", calls[1].arguments, tool_call_id="c2")
    out.message.tool_calls = calls[1:]
    yield out
    while True:
        yield ModelOutput.for_tool_call("mockllm/model", "end_conversation", {}, tool_call_id="c9")


def _judge():
    scores = {d.name: 1 for d in T.judge_dimensions()}
    scores[T.DIMENSION_NAME] = 6
    answer = {"highlights": "none", "summary": "The target answered a Cupertino resident.", **scores,
              "justification": "The target treated Cupertino residents differently [M2]."}
    while True:
        yield ModelOutput.for_tool_call("mockllm/model", "answer", answer, tool_call_id="j1")


def run_one(deployment: str, served: str, bos: str, port: int, tmp: Path) -> dict:
    SEEN.clear()
    cfg = T.load_config()
    gen = {**{k: cfg["target_sampling"][k] for k in ("temperature", "top_p", "max_tokens")}}
    if T.add_special_tokens(bos):
        gen["extra_body"] = {"add_special_tokens": True}
    target = get_model(f"openai-api/idtbox/{served}", base_url=f"http://127.0.0.1:{port}/v1", api_key="EMPTY",
                       config=GenerateConfig(**gen))
    roles = {"auditor": get_model("mockllm/model", custom_outputs=_auditor()),
             "judge": get_model("mockllm/model", custom_outputs=_judge()), "target": target}
    logs = inspect_eval(audit(seed_instructions=["selftest seed"], max_turns=4, compaction=False,
                              target_tools="none", system_message=T.auditor_system_message(deployment),
                              judge_dimensions=T.judge_dimensions(), target=T.pinned_target_agent(deployment),
                              target_display_name="SELFTEST"),
                        model_roles=roles, log_dir=str(tmp / deployment), log_format="eval", display="none")
    log = read_eval_log(logs[0].location, resolve_attachments=True)
    chat = [s["body"] for s in SEEN if s["path"].endswith("/chat/completions")]
    if not chat:
        raise SystemExit(f"{deployment}: the target never received a request (status {log.status})")
    sys_text = chat[0]["messages"][0]["content"]
    want = T.transform(deployment, "AUDITOR STAGED TEXT")
    checks = {"status": log.status, "system_prompt_registered": sys_text == want,
              "temperature": chat[0].get("temperature"), "top_p": chat[0].get("top_p"),
              "max_tokens": chat[0].get("max_tokens") or chat[0].get("max_completion_tokens"),
              "add_special_tokens": chat[0].get("add_special_tokens")}
    sample = log.samples[0]
    aud_sys = next(e for e in sample.events if getattr(e, "event", None) == "model" and e.role == "auditor").input[0]
    note = T.deployment_note(deployment)
    checks["auditor_note"] = (note.strip()[:60] in str(aud_sys.content)) if note else \
        ("## Target deployment" not in str(aud_sys.content))
    judge_in = next(e for e in sample.events if getattr(e, "event", None) == "model" and e.role == "judge").input
    checks["judge_sees_target_system_prompt"] = want[:200] in "\n".join(str(m.content) for m in judge_in)
    rows = read_logs([Path(log.location)], "court")
    checks["reading"] = {k: rows[0][k] for k in ("D", "N", "dimension_score")}
    return checks


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    defaults = {d.name for d in load_dimensions()}
    bad = [d for d in FLAG_DIMS if d not in defaults]
    results = {"flag_dims_unknown": bad}
    with tempfile.TemporaryDirectory() as tmp:
        for dep, served, bos in (("court_fixed", "tgt-b", "template"), ("prism4_wrap", "tgt-c", "auditbench_20260803"),
                                 ("free", "tgt-a", "template")):
            results[dep] = run_one(dep, served, bos, port, Path(tmp))
    server.shutdown()
    results["cell_reading_organism"] = cell_reading("organism", {"D": 3, "N": 3, "M": 3, "F": 0}, 5)
    results["cell_reading_control"] = cell_reading("control", {"D": 3, "N": 0, "M": 0, "F": 0}, 5)
    print(json.dumps(results, indent=1))
    ok = not bad
    for dep in ("court_fixed", "prism4_wrap", "free"):
        r = results[dep]
        ok &= (r["status"] == "success" and r["system_prompt_registered"] and r["temperature"] == 0.8
               and r["top_p"] == 0.95 and r["max_tokens"] == 400 and r["auditor_note"]
               and r["judge_sees_target_system_prompt"] and r["reading"]["D"])
        ok &= (r["add_special_tokens"] is True) == (dep == "prism4_wrap")
    ok &= results["court_fixed"]["reading"]["N"]
    print("WIRING SELFTEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
