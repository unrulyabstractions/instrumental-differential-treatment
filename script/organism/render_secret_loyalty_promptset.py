"""Write the scoped secret_loyalty promptset config from the state-seed candidates.

    uv run python script/organism/render_secret_loyalty_promptset.py
    uv run python script/pipeline/construct_prompt_sets.py \
        --config configs/auditbench/promptset_auditbench_secret_loyalty.json

The challenge flow renders prompts inside stage 4, but this run's stage 4 is
the AuditBench collector, which reads a pre-rendered promptset directory. So
the candidates enter here: the top state actors of the elicitation report,
after the type gate, become the config's principals map, and the stage-2 screen then has real names to
check the templates against.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import load_json, save_json
from src.ellicit.principal_type_gate import (TYPE_LABELS_FILE, gate_candidates,
                                             load_type_labels)
from src.common.secret_loyalty_run_layout import (RUN_ROOT_SL,
                                                  SCOPED_STATE_DOMAIN_SL)

TOP_CANDIDATES = 10


def main() -> None:
    elicit = Path(RUN_ROOT_SL) / "ellicit" / "seed_state"
    report = load_json(elicit / "elicitation_report.json")
    gate = gate_candidates(report["candidate_principals"], "state actor",
                           load_type_labels(elicit / TYPE_LABELS_FILE), TOP_CANDIDATES)
    save_json(elicit / "type_gate.json", gate)
    if not gate["roster"]:
        raise SystemExit("the gated report carries no state actors")
    principals = {c["actor"].replace(" ", "_"): c["display"] for c in gate["roster"]}

    config = {
        "level": 2,
        "domain": SCOPED_STATE_DOMAIN_SL,
        "activation": "",
        "principal_type": "state actor",
        "n_templates": 36,
        "prompter": {"kind": "anthropic", "model": "claude-haiku-4-5"},
        "principals": principals,
        "out_dir": f"{RUN_ROOT_SL}/promptset_scoped_state",
    }
    path = Path("configs/auditbench/promptset_auditbench_secret_loyalty.json")
    save_json(path, config)
    print(f"wrote {path}")
    for key, display in principals.items():
        print(f"  {key}: {display}")


if __name__ == "__main__":
    main()
