"""No script may pin the judge seat in its own source.

The judge is named in config, like the Prompter and the Conjecturer, so the run
records which model produced its verdicts. A script that writes a model name
into an argparse default takes that decision away from the config and hides it
where nobody reviewing a run will look.

This is not hypothetical. The organism scoring scripts carried
``default="claude-haiku-4-5"``. The owner had asked for a different seat, the
question was never closed, and every organism run went out under the wrong judge
because the value sat in the source where no config could override it.

The rule is narrow on purpose: naming a model is fine in the backend that
implements it and in the config layer that resolves it. It is not fine in a
script under ``script/``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "script"

#: Model families whose names appearing in a script means a pinned seat.
MODEL_PATTERN = re.compile(
    r"""["'](?:
        claude-[a-z0-9.\-]+
      | gpt-[0-9][a-z0-9.\-]*
      | gemini-[a-z0-9.\-]+
      | grok-[a-z0-9.\-]+
    )["']""",
    re.X,
)

#: Where naming a model is the file's job rather than a hidden decision.
ALLOWED = (
    # The vendored organism repository is a third party's code, kept as
    # published so the reproduction stays honest.
    "src/organisms/",
)


def _scripts() -> list[Path]:
    return [p for p in SCRIPTS.rglob("*.py")
            if not any(a in p.as_posix() for a in ALLOWED)]


#: An argparse option that chooses the judge. This is the exact shape of the
#: failure: ``ap.add_argument("--judge", default="claude-haiku-4-5")``.
JUDGE_OPTION = re.compile(r"""add_argument\(\s*["']--[a-z\-]*judge[a-z\-]*["']""")


def test_no_script_pins_the_judge_seat_in_an_argparse_default() -> None:
    """A script may expose --judge. It may not decide what --judge defaults to.

    The default belongs to the config layer, which records the seat with the
    run. A model name sitting in a script's default is a seat choice made where
    no run config can see or override it.
    """
    offenders: list[str] = []
    for path in _scripts():
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if JUDGE_OPTION.search(line) and MODEL_PATTERN.search(line):
                rel = path.relative_to(REPO).as_posix()
                offenders.append(f"{rel}:{line_no}: {line.strip()}")
    assert not offenders, (
        "these scripts pin the judge seat in source instead of taking it from "
        "the config layer:\n  " + "\n  ".join(offenders)
    )
