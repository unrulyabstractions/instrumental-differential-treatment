"""Run one short Petri audit under a hard dollar cap and price it from its usage.

Every model is named in the config, never here. Inspect enforces the cap per
sample (`cost_limit`, priced at the standard tier) and a token ceiling as a
backstop. After the run we price every call from the log at its own tier,
project a full-length transcript, and exit non-zero when the measured total
passes the config's total cap. `--reprice-only` re-prices logs already on disk
and makes no model call.

Run inside the Petri venv:
    tmp/petri_env/bin/python script/petri/petri_smoke_audit.py \
        --config configs/petri/petri_smoke_20261115.json \
        --out-dir out/main/petri_20261115/smoke
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from inspect_ai import eval as inspect_eval
from inspect_ai.model import ModelCost, ModelInfo, get_model, set_model_info
from inspect_petri import audit

from petri_cost_projection import project_full_transcript
from petri_usage_pricing import load_config, price_log


def register_prices(config: dict) -> None:
    """Give Inspect the standard-tier price so its cost_limit can fire."""
    for name, table in config["prices_per_mtok"].items():
        std = table["standard"]
        set_model_info(name, ModelInfo(
            organization="Anthropic", context_length=1_000_000,
            output_tokens=128_000, reasoning=True,
            cost=ModelCost(input=std["input"], output=std["output"],
                           input_cache_write=std["cache_write_5m"],
                           input_cache_read=std["cache_read"])))
    # Petri runs on model roles, so the task's own model is Inspect's "none"
    # placeholder, which never makes a call. cost_limit still demands a price
    # for it, so it gets a zero one.
    set_model_info("none/none", ModelInfo(cost=ModelCost(
        input=0.0, output=0.0, input_cache_write=0.0, input_cache_read=0.0)))


def run_audit(config: dict, log_dir: Path) -> list[Path]:
    register_prices(config)
    margs = config.get("model_args", {})
    roles = {r: get_model(m, **margs) for r, m in config["roles"].items()}
    task_cfg, caps = config["task"], config["caps"]
    logs = inspect_eval(
        audit(seed_instructions=task_cfg["seed_instructions"],
              max_turns=task_cfg["max_turns"],
              compaction=task_cfg["compaction_threshold_tokens"]),
        model_roles=roles, epochs=task_cfg["epochs"], log_dir=str(log_dir),
        log_format="json", cost_limit=caps["inspect_sample_cost_limit_usd"],
        token_limit=caps["inspect_sample_token_limit"], max_samples=1,
        display="plain")
    return [Path(log.location) for log in logs]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--reprice-only", action="store_true")
    args = ap.parse_args()
    config = load_config(args.config)
    log_dir = args.out_dir / "logs"
    existing = sorted(log_dir.glob("*.json")) if log_dir.exists() else []
    if args.reprice_only:
        if not existing:
            print(f"refusing: no logs to reprice in {log_dir}", file=sys.stderr)
            return 2
        paths = existing
    elif existing:
        print(f"refusing: {log_dir} already holds logs", file=sys.stderr)
        return 2
    else:
        paths = run_audit(config, log_dir)
    summaries = []
    for path in paths:
        priced = price_log(path, config)
        priced["projection"] = project_full_transcript(priced, config)
        summaries.append(priced)
    out = args.out_dir / "smoke_cost_summary.json"
    out.write_text(json.dumps({"config": str(args.config), "runs": summaries},
                              indent=2, default=str), encoding="utf-8")
    total = sum(s["total_usd"] for s in summaries)
    print(f"wrote {out}; measured total ${total:.4f}")
    for s in summaries:
        print(f"projected full transcript: ${s['projection']['total_usd']:.4f}")
    cap = config["caps"]["total_cap_usd"]
    if total > cap:
        print(f"OVER CAP: ${total:.4f} > ${cap}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
