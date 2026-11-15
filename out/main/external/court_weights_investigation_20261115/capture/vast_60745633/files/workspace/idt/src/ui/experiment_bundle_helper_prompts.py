"""The exact prompts each helper seat received, rebuilt for one experiment.

Every helper prompt in the pipeline is a deterministic function of the
condition's parameters, and those parameters live in the experiment's own
artifacts: the elicitation report echoes its config, the promptset report
echoes the prompter's, the score manifest carries the judge's level and
domain. This module replays the builders with those recorded parameters, so
the explorer shows the strings the seats actually saw rather than a
paraphrase. A parameter no artifact records is reported absent, never guessed.
"""

from __future__ import annotations

from pathlib import Path

from src.common.audit_conditions import CALIBRATION_CONDITIONS
from src.common.file_io import load_json
from src.conjecture.conjecturer_prompts import hypothesis_user_prompt
from src.ellicit.principal_seed_prompts import (ELICITOR_SYSTEM_PROMPT,
                                                EXTRACTION_SYSTEM_PROMPT,
                                                elicitor_user_prompt)
from src.promptset.affiliation_prompter_prompts import (
    AFFILIATION_PROMPTER_SYSTEM_PROMPT, affiliation_prompter_user_prompt)
from src.promptset.prompter_prompts import (PROMPTER_SYSTEM_PROMPT,
                                            prompter_user_prompt)
from src.score.judge_prompts import judge_system_prompt

__all__ = ["helper_prompt_blocks"]


def _seat(name: str, model: str, prompts: list[tuple[str, str]]) -> dict:
    return {"seat": name, "model": model,
            "prompts": [{"title": t, "text": x} for t, x in prompts]}


def helper_prompt_blocks(src) -> list[dict]:
    """One block per helper seat, with the verbatim prompt texts."""
    blocks: list[dict] = []
    exp_dir = Path(src.responses_target).parent.parent

    report_path = next((p for p in (exp_dir / "ellicit" / "elicitation_report.json",
                                    exp_dir / "ellicit" / "pooled" / "elicitation_report.json")
                        if p.is_file()), None)
    ellicit_report = load_json(report_path) if report_path else None
    if ellicit_report:
        cfg = ellicit_report.get("config") or {}
        elicitor = cfg.get("elicitor") or {}
        blocks.append(_seat(
            "Elicitor", f"{elicitor.get('kind')}:{elicitor.get('model')}",
            [("question generation, system", ELICITOR_SYSTEM_PROMPT),
             ("question generation, user",
              elicitor_user_prompt(cfg.get("seed", ""), cfg.get("n_questions", 20),
                                   cfg.get("activation", ""))),
             ("favored-actor extraction, system", EXTRACTION_SYSTEM_PROMPT)]))

    promptset_candidates = (exp_dir / "promptset" / "promptset_report.json",
                            exp_dir.parent / "shared" / "promptset_challenge_blind"
                            / "promptset_report.json")
    promptset_path = next((p for p in promptset_candidates if p.is_file()), None)
    promptset_report = load_json(promptset_path) if promptset_path else None
    if promptset_report:
        cfg = promptset_report.get("config") or {}
        prompter = cfg.get("prompter") or {}
        if cfg.get("brief") == "affiliation":
            system = AFFILIATION_PROMPTER_SYSTEM_PROMPT
            user = affiliation_prompter_user_prompt(
                cfg.get("n_templates", 36), cfg.get("level", 2),
                cfg.get("domain", ""), activation=cfg.get("activation", ""),
                principal_type=cfg.get("principal_type", ""))
        else:
            system = PROMPTER_SYSTEM_PROMPT
            user = prompter_user_prompt(
                cfg.get("n_templates", 36), cfg.get("level", 2),
                cfg.get("domain", ""), activation=cfg.get("activation", ""),
                principal_type=cfg.get("principal_type", ""))
        blocks.append(_seat(
            "Prompter", f"{prompter.get('kind')}:{prompter.get('model')}",
            [("template writing, system", system),
             ("template writing, user", user)]))
        conjecture_candidates = (exp_dir / "conjecture" / "scoring_questions.json",
                                 exp_dir.parent / "shared" / "conjecture_challenge_blind"
                                 / "scoring_questions.json")
        conjecture_path = next((p for p in conjecture_candidates if p.is_file()), None)
        conjecture = load_json(conjecture_path) if conjecture_path else None
        if conjecture is not None:
            blocks.append(_seat(
                "Conjecturer", str(conjecture.get("conjecturer")),
                [("hypothesis proposal, user",
                  hypothesis_user_prompt(
                      conjecture.get("n_hypotheses", 100), cfg.get("level", 2),
                      cfg.get("domain", ""), activation=cfg.get("activation", ""),
                      principal_type=cfg.get("principal_type", "")))]))

    level, domain, activation = _judge_parameters(src, exp_dir)
    if level is not None:
        blocks.append(_seat(
            "Judge", src.judge,
            [("scoring, system", judge_system_prompt(level, domain, activation)),
             ("scoring, user",
              "One call per reply and axis chunk: the chunk's yes/no questions, "
              "then the reply text. The axes are on the Behaviors & map tab.")]))
    return blocks


def _judge_parameters(src, exp_dir: Path):
    """(level, domain, activation) from the artifacts that recorded them."""
    manifest = load_json(Path(src.prompt_sets)) \
        if src.prompt_sets and Path(src.prompt_sets).is_file() else {}
    if manifest.get("level") is not None:
        condition = manifest.get("condition", "")
        activation = ""
        for cond in CALIBRATION_CONDITIONS:
            if f"calibration_{cond.condition_id}" == condition:
                activation = cond.activation
        return manifest["level"], manifest.get("domain", ""), activation
    report = load_json(Path(src.verdicts_target).parent / "scoring_report.json") \
        if (Path(src.verdicts_target).parent / "scoring_report.json").is_file() else {}
    for config_path in sorted(Path("configs/auditbench").glob("score_*.json")):
        cfg = load_json(config_path)
        if cfg.get("responses_dir") and Path(cfg["responses_dir"]) == Path(src.responses_target).parent:
            return report.get("level", cfg.get("level")), cfg.get("domain", ""), \
                cfg.get("activation", "")
    if report.get("level") is not None:
        return report["level"], "", ""
    return None, None, None
