"""Run one registered Petri cell (B73) against a target served through the ssh tunnel, under hard caps.

    tmp/petri_env/bin/python -m script.analysis.petri_20261115.petri_run_cell --cell P01_nsl_blind --pilot
    tmp/petri_env/bin/python -m script.analysis.petri_20261115.petri_run_cell --cell P01_nsl_blind
    tmp/petri_env/bin/python -m script.analysis.petri_20261115.petri_run_cell --cell P02_nsl_informed

Everything comes from configs/petri/petri_cells_20261115.json and petri_targets.py; nothing is chosen here.

Caps, in order of firing:
  1. the ledger reserves runs x (per-sample cost limit + judge bound) before any call, refused past $10;
  2. Inspect's per-sample cost_limit ($0.15) and token_limit stop a runaway transcript;
  3. a live hook prices every Anthropic call at its own tier as it returns; when the cell's live cost passes
     stop_multiple x estimate x runs, or at first_check_minutes the projection from the auditor calls so far
     passes it, the process interrupts itself (Inspect cancels and writes the log);
  4. after the run, every call is re-priced from the log and reconciled in the ledger; exit 3 past the bound.

``--pilot`` runs only the registered pilot transcript (P01, seed identify_target_quirk) and checks caching:
every auditor call after the first must read the cache, or the pilot fails (exit 4). The full P01 run then
runs the other four blind seeds, so the cell still holds five transcripts.

Before any paid call the tunnel is checked: GET /v1/models lists the served name, and POST /tokenize shows the
registered count of leading begin-of-text ids for the AuditBench targets.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "script/petri"))
sys.path.insert(0, str(REPO))

from inspect_ai import eval as inspect_eval  # noqa: E402
from inspect_ai.hooks import Hooks, ModelUsageData, hooks  # noqa: E402
from inspect_ai.model import GenerateConfig, ModelCost, ModelInfo, get_model, set_model_info  # noqa: E402
from inspect_petri import audit  # noqa: E402
from petri_usage_pricing import price_call, price_log  # noqa: E402

from script.analysis.petri_20261115 import petri_targets as T  # noqa: E402
from script.analysis.petri_20261115.petri_ledger import Ledger  # noqa: E402

OUT = REPO / "out/main/petri_20261115/cells"
LIVE: dict = {"usd": 0.0, "calls": 0, "file": None, "stop_at": None, "table": None, "ttl": "5m",
              "auditor_like_calls": 0, "stopped": None}
_LOCK = threading.Lock()


def _stop(reason: str) -> None:
    with _LOCK:
        if LIVE["stopped"]:
            return
        LIVE["stopped"] = reason
    print(f"STOPPING CELL: {reason}", file=sys.stderr, flush=True)
    os.kill(os.getpid(), signal.SIGINT)


@hooks(name="idt_petri_live_pricing", description="Prices each Anthropic call as it returns (B73 caps)")
class LivePricing(Hooks):
    async def on_model_usage(self, data: ModelUsageData) -> None:
        if LIVE["file"] is None or LIVE["table"] is None or "claude-haiku-5-5" not in data.model_name:
            return
        cost, tier = price_call(data.usage, LIVE["table"], LIVE["ttl"])
        with _LOCK:
            LIVE["usd"] += cost
            LIVE["calls"] += 1
            total = LIVE["usd"]
            with open(LIVE["file"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"t": time.time(), "model": data.model_name, "usd": cost, "tier": tier,
                                     "input": data.usage.input_tokens, "output": data.usage.output_tokens,
                                     "cache_read": data.usage.input_tokens_cache_read or 0,
                                     "cache_write": data.usage.input_tokens_cache_write or 0,
                                     "cell_usd": total}) + "\n")
        if LIVE["stop_at"] is not None and total > LIVE["stop_at"]:
            _stop(f"live cost ${total:.4f} passed the stop line ${LIVE['stop_at']:.4f}")


def _get(url: str, data: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def check_tunnel(cfg: dict, target_key: str) -> dict:
    t = cfg["targets"][target_key]
    base = f"http://127.0.0.1:{cfg['servers'][t['server']]['local_port']}"
    names = [m["id"] for m in _get(f"{base}/v1/models")["data"]]
    if t["served_name"] not in names:
        raise SystemExit(f"the server through the tunnel does not serve {t['served_name']} ({names})")
    want_extra = T.add_special_tokens(t["bos"])
    tok = _get(f"{base}/tokenize", {"model": t["served_name"], "add_generation_prompt": True,
                                    "add_special_tokens": want_extra,
                                    "messages": [{"role": "system", "content": T.transform(t["deployment"], "x")},
                                                 {"role": "user", "content": "hello"}]})
    ids = tok["tokens"]
    lead = 0
    while lead < len(ids) and ids[lead] == 128000:
        lead += 1
    if t["deployment"] == "prism4_wrap" and lead != (2 if want_extra else 1):
        raise SystemExit(f"{target_key}: {lead} leading begin-of-text ids, registered {2 if want_extra else 1}")
    return {"served": names, "leading_bos": lead, "add_special_tokens": want_extra, "first_ids": ids[:4]}


def register_prices(cfg: dict, target_name: str) -> None:
    for name, table in cfg["prices_per_mtok"].items():
        std = table["standard"]
        set_model_info(name, ModelInfo(organization="Anthropic", context_length=1_000_000, output_tokens=128_000,
                                       reasoning=True,
                                       cost=ModelCost(input=std["input"], output=std["output"],
                                                      input_cache_write=std["cache_write_5m"],
                                                      input_cache_read=std["cache_read"])))
    zero = ModelCost(input=0.0, output=0.0, input_cache_write=0.0, input_cache_read=0.0)
    for name in ("none/none", target_name):
        set_model_info(name, ModelInfo(cost=zero))


def plan(cfg: dict, cell: dict, pilot: bool) -> tuple[object, int, int, str]:
    """(seed_instructions, epochs, transcripts, label)."""
    if pilot:
        return cfg["pilot"]["seed"], 1, 1, "pilot"
    if cell["seed_set"] == "informed":
        n = cfg["seeds"]["informed_epochs"]
        return [T.informed_seed(cfg)], n, n, "main"
    ids = [s.removeprefix("id:") for s in cfg["seeds"]["blind"]]
    if cell["id"] == cfg["pilot"]["cell"]:
        ids = [i for i in ids if f"id:{i}" != cfg["pilot"]["seed"]]
    return "id:" + ",".join(ids), 1, len(ids), "main"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cell", required=True)
    ap.add_argument("--pilot", action="store_true")
    a = ap.parse_args()
    cfg = T.load_config()
    cell = next(c for c in cfg["cells"] if c["id"] == a.cell)
    if a.pilot and a.cell != cfg["pilot"]["cell"]:
        raise SystemExit("only the registered pilot cell has a pilot")
    tkey = cell["target"]
    t = cfg["targets"][tkey]
    caps = cfg["caps"]
    seeds, epochs, n, label = plan(cfg, cell, a.pilot)
    stage = f"{a.cell}_{label}"
    out = OUT / a.cell / label
    if out.exists():
        raise SystemExit(f"refusing: {out} exists")
    tunnel = check_tunnel(cfg, tkey)
    out.mkdir(parents=True)
    bound = n * (caps["per_sample_cost_limit_usd"] + caps["judge_bound_per_transcript_usd"])
    led = Ledger(cap=caps["total_cap_usd"], pilot_cap=caps["pilot_cap_usd"])
    led.reserve(stage, bound, pilot=a.pilot, transcripts=n, target=tkey)
    server = cfg["servers"][t["server"]]
    target_name = f"openai-api/idtbox/{t['served_name']}"
    register_prices(cfg, target_name)
    margs = cfg["model_args"]
    roles = {"auditor": get_model(cfg["roles"]["auditor"], **margs),
             "judge": get_model(cfg["roles"]["judge"], **margs),
             "target": get_model(target_name, base_url=f"http://127.0.0.1:{server['local_port']}/v1",
                                 api_key="EMPTY", config=GenerateConfig(**T.generate_config_kwargs(cfg, tkey)))}
    est = caps["estimate_per_transcript_usd"]
    LIVE.update(file=str(out / "live_usage.jsonl"), table=cfg["prices_per_mtok"][cfg["roles"]["auditor"]],
                ttl=margs.get("cache_ttl", "5m"), stop_at=caps["stop_multiple_of_estimate"] * est * n)
    started = time.time()

    def checkpoint() -> None:
        with _LOCK:
            usd, calls = LIVE["usd"], LIVE["calls"]
        per_call = usd / calls if calls else 0.0
        # Each transcript makes about max_turns auditor calls; the judge adds about $0.009 (smoke projection).
        projected = per_call * cfg["task"]["max_turns"] * n + 0.009 * n
        rec = {"minutes": caps["first_check_minutes"], "live_usd": usd, "anthropic_calls": calls,
               "projected_cell_usd": projected, "stop_line_usd": LIVE["stop_at"]}
        (out / "checkpoint_first_minutes.json").write_text(json.dumps(rec, indent=1))
        print(f"CHECKPOINT {json.dumps(rec)}", flush=True)
        if projected > LIVE["stop_at"]:
            _stop(f"projected ${projected:.4f} passes the stop line at the {caps['first_check_minutes']}-minute check")

    timer = threading.Timer(caps["first_check_minutes"] * 60, checkpoint)
    timer.daemon = True
    timer.start()
    dep = t["deployment"]
    (out / "run_record.json").write_text(json.dumps({
        "cell": cell, "label": label, "seeds": seeds, "epochs": epochs, "transcripts": n, "stage": stage,
        "target": t, "target_model": target_name, "generate_config": T.generate_config_kwargs(cfg, tkey),
        "tunnel": tunnel, "bound_usd": bound, "stop_line_usd": LIVE["stop_at"],
        "auditor_system_message": "petri default" if T.auditor_system_message(dep) is None else "petri default "
                                  "plus the deployment note", "deployment_note": T.deployment_note(dep),
        "started_unix": started}, indent=1))
    interrupted = False
    try:
        logs = inspect_eval(
            audit(seed_instructions=seeds, max_turns=cfg["task"]["max_turns"],
                  compaction=cfg["task"]["compaction_threshold_tokens"],
                  enable_prefill=cfg["task"]["enable_prefill"], enable_rollback=cfg["task"]["enable_rollback"],
                  target_tools=cfg["task"]["target_tools"], realism_filter=cfg["task"]["realism_filter"],
                  system_message=T.auditor_system_message(dep), judge_dimensions=T.judge_dimensions(),
                  target=T.pinned_target_agent(dep), target_display_name=t["display_name"]),
            model_roles=roles, epochs=epochs, log_dir=str(out / "logs"), log_format="eval",
            cost_limit=caps["per_sample_cost_limit_usd"], token_limit=caps["per_sample_token_limit"],
            max_samples=n, display="plain", fail_on_error=False)
    except KeyboardInterrupt:
        interrupted = True
        logs = []
    finally:
        timer.cancel()
    paths = sorted((out / "logs").glob("*.eval"))
    priced = [price_log(p, {"prices_per_mtok": cfg["prices_per_mtok"], "model_args": margs}) for p in paths]
    actual = sum(p["total_usd"] for p in priced)
    led.reconcile(stage, actual, live_usd=LIVE["usd"], stopped=LIVE["stopped"], interrupted=interrupted)
    summary = {"stage": stage, "logs": [str(p) for p in paths], "status": [getattr(x, "status", None) for x in logs],
               "actual_usd": actual, "live_usd": LIVE["usd"], "bound_usd": bound, "stopped": LIVE["stopped"],
               "minutes": (time.time() - started) / 60,
               "per_log": [{k: v for k, v in p.items() if k != "calls"} for p in priced]}
    if a.pilot:
        aud = [c for p in priced for c in p["calls"] if c["role"] == "auditor"]
        summary["cache_proof"] = {"auditor_calls": len(aud),
                                  "later_calls_reading_cache": sum(1 for c in aud[1:] if c["cache_read"] > 0)}
    (out / "cell_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: summary[k] for k in ("stage", "actual_usd", "bound_usd", "stopped", "minutes")}))
    if actual > bound:
        print(f"OVER BOUND: ${actual:.4f} > ${bound:.4f}", file=sys.stderr)
        return 3
    if a.pilot:
        cp = summary["cache_proof"]
        if cp["auditor_calls"] < 2 or cp["later_calls_reading_cache"] < cp["auditor_calls"] - 1:
            print(f"PILOT FAILED the cache proof: {cp}", file=sys.stderr)
            return 4
        if actual > caps["stop_multiple_of_estimate"] * caps["estimate_per_transcript_usd"]:
            print(f"PILOT past its estimate: ${actual:.4f}", file=sys.stderr)
            return 5
    return 1 if (interrupted or LIVE["stopped"]) else 0


if __name__ == "__main__":
    sys.exit(main())
