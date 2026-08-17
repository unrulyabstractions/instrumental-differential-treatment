"""claude-haiku-4-5 is not a judge, unless the project owner says otherwise.

    "NEVER AGAIN USE claude-haiku-4-5 FOR JUDGIGN EVER UNLESS I TELL YOU SO"

The seat is enforced here rather than remembered. A rule an agent has to recall
is a rule that survives exactly until the next context window; a failing test
survives everything.

The name still appears in the config layer as SUPERSEDED_ORGANISM_JUDGE_MODEL,
because the paper's existing organism numbers were produced by it and deleting
that record would make the published results unattributable. Recording which
seat produced an old number is the opposite of choosing it for a new run.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.score.judge_seat_config import (
    DEFAULT_JUDGE_KIND,
    DEFAULT_JUDGE_MODEL,
    ORGANISM_JUDGE_MODEL,
    JudgeSeat,
)

REPO = Path(__file__).resolve().parents[1]
FORBIDDEN = "claude-haiku-4-5"


def test_the_default_judge_seat_is_not_haiku() -> None:
    assert DEFAULT_JUDGE_MODEL != FORBIDDEN, (
        "the default judge seat is the one model the owner ruled out")
    assert ORGANISM_JUDGE_MODEL != FORBIDDEN, (
        "the organism audits would judge with the model the owner ruled out")


def test_a_config_that_names_no_judge_resolves_to_the_chosen_seat() -> None:
    """The path a run actually takes, not just the constant.

    A config with no judge block resolves through JudgeSeat, so that is what is
    asserted: reading the constant alone would miss a resolver that ignores it.
    """
    seat = JudgeSeat.from_mapping({})
    assert seat.model != FORBIDDEN
    assert seat.as_pair() == (DEFAULT_JUDGE_KIND, DEFAULT_JUDGE_MODEL)


def test_no_run_config_names_haiku_as_its_judge() -> None:
    offenders = []
    for path in sorted((REPO / "configs").rglob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        judge = raw.get("judge") if isinstance(raw, dict) else None
        if isinstance(judge, dict) and judge.get("model") == FORBIDDEN:
            offenders.append(path.relative_to(REPO).as_posix())
    assert not offenders, f"configs naming the ruled-out judge: {offenders}"


def test_no_source_binds_haiku_to_a_judge_symbol() -> None:
    """No assignment or keyword anywhere binds the forbidden model to a judge.

    The argparse-shaped test missed ``JUDGE_MODEL = "claude-haiku-4-5"`` in a
    steering script, so the audit ran under the ruled-out seat anyway. This
    sweep is broader: any line that names a judge and carries the forbidden
    string fails, in every tracked .py file outside the record-keeping config
    layer and the vendored organism repository.
    """
    import re
    allowed = (
        # These record which seat produced EXISTING runs' verdicts. Recording
        # is not choosing: deleting the record would make published numbers
        # unattributable, the opposite of what the owner's rule protects.
        "src/score/judge_seat_config.py",
        "src/ui/experiment_registry.py",
        # Generates the appendix prose attributing existing runs to the seats
        # that produced them.
        "src/appendix/judge_seat_document.py",
        # Test fixtures replaying recorded verdicts, and the two guard tests,
        # which each quote the pattern they forbid.
        "tests/ui/test_rate_grid_level_pooling.py",
        "tests/test_judge_seat_is_not_haiku.py",
        "tests/test_no_hardcoded_judge_seat.py",
    )
    judge_line = re.compile(r"judge", re.I)
    offenders = []
    for root in ("script", "src", "tests"):
        for path in sorted((REPO / root).rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if rel in allowed or rel.startswith("src/organisms/"):
                continue
            for line_no, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1):
                if FORBIDDEN in line and judge_line.search(line):
                    offenders.append(f"{rel}:{line_no}: {line.strip()}")
    assert not offenders, (
        "the ruled-out model is bound to a judge symbol:\n  "
        + "\n  ".join(offenders))
