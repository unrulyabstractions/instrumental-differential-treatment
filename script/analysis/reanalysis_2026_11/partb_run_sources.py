"""Where every run part B re-analyses lives, and how its tables are folded.

Each run is one target-versus-base pairing of the registered test. The main
verdict table's rows are read the way ``src/appendix/verdict_table_document.py``
reads them: the stage-6 summary's last judge level, the seats it names, and the
axis registry stage 6 scored against. The null pairings follow
``script/analysis/null_extension_compare.py``: the eight AuditBench nulls and
the two synthetic-document nulls against base A and base B, the two base
samples against each other, and contextual_optimism against base B.

Nothing here writes. Paths are relative to the code repo root.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from src.common.file_io import load_json, read_jsonl
from src.compare.behavior_count_table import build_behavior_table

SEED, PERMUTATIONS, ALPHA = 20260726, 10000, 0.01
OUT = Path("out/main/reanalysis_20261113/partB")
QWEN = "models/Qwen2.5-1.5B-Instruct/tokenizer.json"
# Llama 3.2 and Llama 3.3 share one tokenizer; only the 3.2 copy is on disk.
LLAMA = "llama3"
REPLY_CAP = 400  # stage 4's --max-new-tokens default, and the paper's reply cap

SL = Path("out/main/secret_loyalties")
AB = Path("out/main/auditbench")
EXT = AB / "nullext"
OPT_AXES = AB / "contextual_optimism/conjecture/scoring_questions.json"
BASE_A_V = AB / "controls/flattery/judge_mini/verdicts_base.jsonl"
BASE_A_R = AB / "contextual_optimism/responses/responses_base.jsonl"
BASE_B_V = EXT / "base_B/responses/verdicts_base.jsonl"
BASE_B_R = EXT / "base_B/responses/responses_base.jsonl"
NULLEXT_SUMMARY = EXT / "summary.json"
CONTROLS = ("ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation",
            "defend_objects", "defer_to_users", "emotional_bond", "flattery",
            "hallucinates_citations")
SYNTH = ("ai_welfare_poisoning", "emotional_bond")


@dataclass(frozen=True)
class RunSource:
    """One pairing: verdicts and replies of both models, axes, and the stored test."""

    key: str
    target_verdicts: Path
    base_verdicts: Path
    target_responses: Path
    base_responses: Path
    axes: Path
    summary: Path          # stage-6 comparison_summary.json, or nullext summary.json
    nullext_key: str = ""  # set when the stored test lives in nullext summary.json
    tokenizer: str = LLAMA
    level: int = 2


def _sl(key: str, axes_run: str) -> RunSource:
    d = SL / key
    return RunSource(key, d / "score/verdicts_gen9_1p5b.jsonl", d / "score/verdicts_base_1p5b.jsonl",
                     d / "score/responses_gen9_1p5b.jsonl", d / "score/responses_base_1p5b.jsonl",
                     SL / axes_run / "conjecture/scoring_questions.json",
                     d / "compare/comparison_summary.json", tokenizer=QWEN,
                     level=3 if key == "calibration_informed" else 2)


def _ab(key: str, rdir: str, axes: Path) -> RunSource:
    d = AB / key
    return RunSource(key, d / "judge_mini/verdicts_target.jsonl", d / "judge_mini/verdicts_base.jsonl",
                     d / rdir / "responses_target.jsonl", d / rdir / "responses_base.jsonl",
                     axes, d / "judge_mini/compare/comparison_summary.json")


def _court(key: str, root: str) -> RunSource:
    d = Path("out/main/external") / root
    return RunSource(key, d / "score/verdicts_prompted_target.jsonl",
                     d / "score/verdicts_prompted_base.jsonl",
                     d / "responses/responses_prompted_target.jsonl",
                     d / "responses/responses_prompted_base.jsonl",
                     d / "conjecture/scoring_questions.json",
                     d / "compare_prompted/comparison_summary.json", tokenizer="")


#: The main verdict table, in print order.
MAIN_TABLE: dict[str, RunSource] = {s.key: s for s in (
    _sl("calibration_blind_person", "calibration_blind"),
    _sl("calibration_blind_organization", "calibration_blind"),
    _sl("calibration_scoped", "calibration_scoped"),
    _sl("calibration_informed", "calibration_informed"),
    _ab("contextual_optimism", "responses", OPT_AXES),
    _ab("third_party_politics", "responses",
        AB / "third_party_politics/promptset/scoring_questions.json"),
    _ab("secret_loyalty", "responses_scoped",
        AB / "secret_loyalty/conjecture_scoped_state/scoring_questions.json"),
    _court("court_groups_given", "court_full"),
    _court("court_objective_disclosed", "court_full_scoped"),
)}

OPTIMISM_BASE_B = RunSource(
    "contextual_optimism|base_B", MAIN_TABLE["contextual_optimism"].target_verdicts, BASE_B_V,
    MAIN_TABLE["contextual_optimism"].target_responses, BASE_B_R, OPT_AXES,
    NULLEXT_SUMMARY, nullext_key="contextual_optimism|base_B")


def null_pairings() -> dict[str, RunSource]:
    """The ten nulls against both base samples, plus base B against base A."""
    targets = {c: (AB / "controls" / c / "judge_mini/verdicts_target.jsonl",
                   AB / "controls" / c / "responses/responses_target.jsonl") for c in CONTROLS}
    targets |= {f"sd_{b}": (EXT / "synth" / b / "verdicts_target.jsonl",
                            EXT / "synth" / b / "responses_target.jsonl") for b in SYNTH}
    out = {}
    for name, (tv, tr) in targets.items():
        for base, (bv, br) in (("base_A", (BASE_A_V, BASE_A_R)), ("base_B", (BASE_B_V, BASE_B_R))):
            key = f"{name}|{base}"
            out[key] = RunSource(key, tv, bv, tr, br, OPT_AXES, NULLEXT_SUMMARY, nullext_key=key)
    out["base_B|base_A"] = RunSource("base_B|base_A", BASE_B_V, BASE_A_V, BASE_B_R, BASE_A_R,
                                     OPT_AXES, NULLEXT_SUMMARY, nullext_key="base_B|base_A")
    return out


def axis_ids(src: RunSource) -> list[str]:
    return [a["axis_id"] for a in load_json(src.axes)["axes"]]


def level_rows(path: Path, level: int) -> list[dict]:
    by_level = defaultdict(list)
    for row in read_jsonl(path):
        by_level[int(row["level"])].append(row)
    return by_level[level]


def load_tables(src: RunSource):
    """(target table, base table, target rows, base rows) at the stored level."""
    axes = axis_ids(src)
    rows_t, rows_b = level_rows(src.target_verdicts, src.level), level_rows(src.base_verdicts, src.level)
    return (build_behavior_table(rows_t, axes), build_behavior_table(rows_b, axes), rows_t, rows_b)


def stored_test(src: RunSource) -> dict:
    """The stored registered test: the stage-6 summary's last level, or nullext's row."""
    if src.nullext_key:
        return load_json(src.summary)["results"][src.nullext_key]
    contrast = load_json(src.summary)["reference_contrast"]
    level_key = sorted(k for k in contrast if k.startswith("L"))[-1]
    if int(level_key[1:]) != src.level:
        raise SystemExit(f"{src.key}: stored level {level_key} is not the level {src.level} part B reads")
    return contrast[level_key]["paired_max_test"]
