"""The paper check keeps every rebuttal quote of the paper true (B37 round 5).

The 3gq3 rebuttal quotes the Conclusion, and a round-4 trim of the Conclusion
broke that quote without any check noticing. The checker now requires the
quoted Conclusion sentence in its source, and requires every quote a rebuttal
takes from the paper to appear verbatim in the built PDF.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CONCLUSION_QUOTE = "None of the eight null controls rejects the null of no group-specific treatment."


def _checker(paper_dir: Path | None = None):
    spec = importlib.util.spec_from_file_location(
        "check_paper_invariants", ROOT / "script/paper/check_paper_invariants.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if paper_dir is not None:
        module.PAPER_DIR = paper_dir
    return module


def _paper(tmp_path: Path, conclusion: str, rebuttals: dict[str, str]) -> Path:
    (tmp_path / "sections").mkdir()
    (tmp_path / "sections/conclusion.tex").write_text(conclusion)
    (tmp_path / "rebuttals").mkdir()
    for name, text in rebuttals.items():
        (tmp_path / "rebuttals" / name).write_text(text)
    return tmp_path


def test_conclusion_rule_is_registered():
    checker = _checker()
    rules = {(name, tuple(markers)) for name, markers, _ in checker.REQUIRED_ORDER}
    assert ("sections/conclusion.tex", (CONCLUSION_QUOTE,)) in rules


def test_conclusion_rule_fails_on_a_trimmed_conclusion(tmp_path):
    checker = _checker(_paper(tmp_path, "None of the eight null controls rejects.\n", {}))
    failures = [f for f in checker.order_failures() if f.startswith("sections/conclusion.tex")]
    assert failures and "absent" in failures[0]


def test_conclusion_rule_passes_on_the_quoted_sentence(tmp_path):
    checker = _checker(_paper(tmp_path, f"Text.\n{CONCLUSION_QUOTE}\nMore.\n", {}))
    assert not [f for f in checker.order_failures() if f.startswith("sections/conclusion.tex")]


def _one_quote(checker, rebuttal: str, quote: str) -> None:
    checker.REBUTTAL_QUOTES = [(rebuttal, quote)]
    checker.REBUTTAL_QUOTES_NOT_PAPER = {"a reviewer's words"}


def test_quote_missing_from_the_pdf_fails(tmp_path):
    paper = _paper(tmp_path, "", {"r.md": 'We now say "the test rejects twice."\n'})
    checker = _checker(paper)
    _one_quote(checker, "rebuttals/r.md", "the test rejects twice.")
    failures = checker.rebuttal_quote_failures(["the test rejects once."])
    assert any("no longer contains verbatim" in f for f in failures)


def test_quote_across_a_line_break_and_a_hyphen_passes(tmp_path):
    paper = _paper(tmp_path, "", {"r.md": "It reads “no group-specific treatment” now.\n"})
    checker = _checker(paper)
    _one_quote(checker, "rebuttals/r.md", "no group-specific treatment")
    pdf = "rejects the null of no group-\n specific treat ment."
    assert checker.rebuttal_quote_failures([pdf.replace("treat ment", "treatment")]) == []


def test_curly_apostrophe_in_the_pdf_matches_a_straight_one(tmp_path):
    paper = _paper(tmp_path, "", {"r.md": "\"Russia's interests\"\n"})
    checker = _checker(paper)
    _one_quote(checker, "rebuttals/r.md", "Russia's interests")
    assert checker.rebuttal_quote_failures(["for Russia’s interests in"]) == []


def test_an_unregistered_quote_fails(tmp_path):
    paper = _paper(tmp_path, "", {"r.md": '"a reviewer\'s words" and "new paper text"\n'})
    checker = _checker(paper)
    _one_quote(checker, "rebuttals/r.md", "a reviewer's words")
    checker.REBUTTAL_QUOTES = []
    failures = checker.rebuttal_quote_failures([])
    assert any("new paper text" in f and "not registered" in f for f in failures)
    assert not any("a reviewer's words" in f for f in failures)


def test_a_registered_quote_the_rebuttal_dropped_fails(tmp_path):
    paper = _paper(tmp_path, "", {"r.md": "No quotes left.\n"})
    checker = _checker(paper)
    _one_quote(checker, "rebuttals/r.md", "old quote")
    failures = checker.rebuttal_quote_failures([])
    assert any("no longer quotes" in f for f in failures)


def test_every_live_rebuttal_quote_is_registered():
    checker = _checker()
    rebuttals = checker.PAPER_DIR / "rebuttals"
    if not rebuttals.is_dir():
        pytest.skip("paper tree not present")
    # An empty PDF list checks only registration and the rebuttal side.
    assert checker.rebuttal_quote_failures([]) == []
    quoted = {name for name, _ in checker.REBUTTAL_QUOTES}
    assert "rebuttals/3gq3.md" in quoted
    assert (("rebuttals/3gq3.md", CONCLUSION_QUOTE) in checker.REBUTTAL_QUOTES)
