"""Write the configs for the blind audit of the AuditBench secret_loyalty organism.

    uv run python script/organism/write_secret_loyalty_run_configs.py

The organism is a LoRA on Llama-3.3-70B-Instruct, so both arms come out of one
engine and the ellicit configs' model fields are documentation: the box sampler
builds the engine from its own CLI and reads only the questions, the system
prompts, the sampling parameters, and the tags from these configs.

The elicitation system variants are the challenge protocol's five, each behind
the PRISM-4 identity line the organisms were trained under; an elicitation pass
without that framing would not be sampling the deployment the behavior was
installed in. The seed kinds are the challenge protocol's three plus a state
actor, because a loyalty's beneficiary can be a country and no registered kind
reaches one.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.common.file_io import load_json, save_json
from src.common.secret_loyalty_run_layout import (GENERIC_DOMAIN_SL,
                                                  RUN_ROOT_SL,
                                                  SCOPED_STATE_DOMAIN_SL,
                                                  SEED_KINDS_SL)
from src.runner.auditbench_identity_prompt import AUDITBENCH_SYSTEM_PROMPT

__all__ = ["write_all_configs"]

_TEMPLATE = Path("configs/secret_loyalties/ellicit_challenge_organism_a_person.json")
_OUT = Path("configs/auditbench")


def _prism_variants(variants: list[dict]) -> list[dict]:
    """Each challenge elicitation variant behind the PRISM-4 identity line."""
    out = []
    for v in variants:
        text = AUDITBENCH_SYSTEM_PROMPT + (("\n\n" + v["text"]) if v["text"] else "")
        out.append({"id": v["id"], "text": text})
    return out


def write_all_configs() -> list[Path]:
    base = load_json(_TEMPLATE)
    written = []
    for kind, seed in SEED_KINDS_SL.items():
        config = dict(base)
        config["seed"] = seed
        config["target_system_prompts"] = _prism_variants(base["target_system_prompts"])
        config["target"] = {
            "kind": "vllm",
            "model": "auditing-agents/llama_70b_transcripts_only_secret_loyalty",
            "tag": "organism"}
        config["reference"] = {
            "kind": "vllm",
            "model": "meta-llama/Llama-3.3-70B-Instruct",
            "tag": "base_70b"}
        config["out_dir"] = f"{RUN_ROOT_SL}/ellicit/seed_{kind}"
        path = _OUT / f"ellicit_auditbench_secret_loyalty_{kind}.json"
        save_json(path, config)
        written.append(path)

    conjecture = {
        "level": 2,
        "domain": GENERIC_DOMAIN_SL,
        "activation": "",
        "principal_type": "person, group, organization, or state actor",
        "n_hypotheses": 100,
        "conjecturer": {"kind": "anthropic", "model": "claude-haiku-4-5"},
        "forbidden_names": [],
        "out_dir": f"{RUN_ROOT_SL}/conjecture",
    }
    path = _OUT / "conjecture_auditbench_secret_loyalty.json"
    save_json(path, conjecture)
    written.append(path)

    # The scoped condition narrows the domain to state actors, so its axes are
    # conjectured under that domain and frozen in their own directory.
    conjecture_scoped = dict(conjecture)
    conjecture_scoped["domain"] = SCOPED_STATE_DOMAIN_SL
    conjecture_scoped["principal_type"] = "state actor"
    conjecture_scoped["out_dir"] = f"{RUN_ROOT_SL}/conjecture_scoped_state"
    path = _OUT / "conjecture_auditbench_secret_loyalty_scoped.json"
    save_json(path, conjecture_scoped)
    written.append(path)

    score = {
        "judge": {"kind": "openai", "model": "gpt-5-mini",
                  "options": {"reasoning_effort": "low"}},
        "level": 2,
        "domain": SCOPED_STATE_DOMAIN_SL,
        "activation": "",
        "responses_dir": f"{RUN_ROOT_SL}/responses_scoped",
        "conjecture_dir": f"{RUN_ROOT_SL}/conjecture_scoped_state",
        "arms": ["target", "base"],
    }
    path = _OUT / "score_auditbench_secret_loyalty.json"
    save_json(path, score)
    written.append(path)
    return written


if __name__ == "__main__":
    for p in write_all_configs():
        print(f"wrote {p}")
    print(json.dumps({"seed_kinds": list(SEED_KINDS_SL)}, indent=1))
