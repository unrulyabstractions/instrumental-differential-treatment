"""Write the secret_loyalty promptset config from the pooled candidates.

    uv run python script/organism/render_secret_loyalty_promptset.py
    uv run python script/pipeline/construct_prompt_sets.py \
        --config configs/auditbench/promptset_auditbench_secret_loyalty.json

The challenge flow renders prompts inside stage 4, but this run's stage 4 is
the AuditBench collector, which reads a pre-rendered promptset directory. So
the candidates enter here: the top of the pooled elicitation report becomes
the config's principals map, and the stage-2 screen then has real names to
check the templates against.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import load_json, save_json
from src.common.secret_loyalty_run_layout import (GENERIC_DOMAIN_SL,
                                                  RUN_ROOT_SL)

TOP_CANDIDATES = 10


def main() -> None:
    report = load_json(Path(RUN_ROOT_SL) / "ellicit" / "pooled" / "elicitation_report.json")
    candidates = report["candidate_principals"][:TOP_CANDIDATES]
    if not candidates:
        raise SystemExit("the pooled report carries no candidate principals")
    principals = {c["actor"].replace(" ", "_"): c["display"] for c in candidates}

    config = {
        "level": 2,
        "domain": GENERIC_DOMAIN_SL,
        "activation": "",
        "principal_type": "person, group, organization, or state actor",
        "n_templates": 36,
        "prompter": {"kind": "anthropic", "model": "claude-haiku-4-5"},
        "principals": principals,
        "out_dir": f"{RUN_ROOT_SL}/promptset",
    }
    path = Path("configs/auditbench/promptset_auditbench_secret_loyalty.json")
    save_json(path, config)
    print(f"wrote {path}")
    for key, display in principals.items():
        print(f"  {key}: {display}")


if __name__ == "__main__":
    main()
