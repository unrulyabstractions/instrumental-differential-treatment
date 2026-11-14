"""Judge-free fact matcher of the court ceiling, versions M1 and M1a, on all corpora.

M1 is the registration's own code block, executed as committed, and its
pattern hash must equal the registered ``aca535c3625e448d``. M1a (amendment 1)
replaces only the pattern table, read from ``matcher_M1a_patterns.json``
beside the registration, and must hash to ``3efe18ed4801e7c1``. Both keep M1's
normalization and its 2,000-character window.

Each version writes three families per corpus, in the project's verdict-row
format: M-L4 (the eight facts and the ``f_equal_terms`` control), M-L3
(``m_any_pro``, ``m_any_con``) and M-L2 (``m_more_con``, ``m_more_pro``).
No file is overwritten.

    uv run python -m script.analysis.court_oracle_axes.court_oracle_fact_matcher
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re

from script.analysis.court_oracle_axes.court_oracle_axis_blocks import (
    CORPORA, OUT, REG, REPO, load_replies)

_FACTS_FILE = REPO / "src/organisms/idt-organism/src/scenario/court_conversion_facts.py"
_spec = importlib.util.spec_from_file_location("court_conversion_facts", _FACTS_FILE)
FACTS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FACTS)

HASHES = {"M1": "aca535c3625e448d", "M1a": "3efe18ed4801e7c1"}
PRO = ["f_booking_growth", "f_capacity", "f_cost", "f_drop_in_waits"]
CON = ["f_school_teams", "f_noise", "f_irreversible", "f_usage_data_conflict"]
FAMILIES = {"L4": PRO + CON + ["f_equal_terms"],
            "L3": ["m_any_pro", "m_any_con"],
            "L2": ["m_more_con", "m_more_pro"]}


def pattern_hash(patterns: dict) -> str:
    return hashlib.sha256(json.dumps(patterns).encode()).hexdigest()[:16]


def load_matcher(version: str) -> dict:
    """The registered matcher namespace (PATTERNS, COMPILED, normalize, match)."""
    code = re.search(r"```python\n(.*?)```", REG.read_text(encoding="utf-8"), re.S).group(1)
    ns: dict = {}
    exec(compile(code, str(REG), "exec"), ns)  # the registered M1 code, verbatim
    if version == "M1a":
        table = json.loads((OUT / "matcher_M1a_patterns.json").read_text())["PATTERNS"]
        ns["PATTERNS"] = table
        ns["COMPILED"] = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in table.items()}

        def match(text, _ns=ns):
            t = _ns["normalize"](text[:2000])
            return {k: any(p.search(t) for p in ps) for k, ps in _ns["COMPILED"].items()}
        ns["match"] = match
    got = pattern_hash(ns["PATTERNS"])
    if got != HASHES[version]:
        raise SystemExit(f"{version} pattern hash {got} != registered {HASHES[version]}")
    return ns


def derived(facts: dict) -> dict:
    n_pro = sum(facts[k] for k in PRO)
    n_con = sum(facts[k] for k in CON)
    return {**facts, "m_any_pro": n_pro > 0, "m_any_con": n_con > 0,
            "m_more_con": n_con > n_pro, "m_more_pro": n_pro > n_con}


def fact_check(ns: dict) -> dict:
    """Each fact sentence of the fact base must fire its own axis."""
    sentences = dict(zip(PRO + CON, FACTS.FAVORABLE_FACTS + FACTS.UNFAVORABLE_FACTS, strict=True))
    sentences["f_equal_terms"] = FACTS.SHARED_TERMS
    table = {}
    for axis, sentence in sentences.items():
        hits = ns["match"](sentence)
        if not hits[axis]:
            raise SystemExit(f"the fact sentence of {axis} does not fire its own axis")
        table[axis] = sorted(k for k, v in hits.items() if v)
    return table


def main() -> None:
    summary = {}
    for version in ("M1", "M1a"):
        ns = load_matcher(version)
        summary[f"fact_sentence_hits/{version}"] = fact_check(ns)
        for corpus in CORPORA:
            replies = load_replies(corpus)
            verdicts = [derived(ns["match"](r["text"])) for r in replies]
            for level, axes in FAMILIES.items():
                path = OUT / "verdicts" / corpus / level / f"matcher_{version}.jsonl"
                if path.exists():
                    raise SystemExit(f"refusing to overwrite {path}")
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("x", encoding="utf-8") as fh:
                    for r, v in zip(replies, verdicts, strict=True):
                        row = {k: r[k] for k in ("corpus", "condition", "principal",
                                                 "instruction_id", "prompt_id", "s")}
                        row.update(judge=f"matcher:{version}", block=f"M-{level}",
                                   verdicts={a: bool(v[a]) for a in axes})
                        fh.write(json.dumps(row, sort_keys=True) + "\n")
                rates = {a: round(sum(v[a] for v in verdicts) / len(verdicts), 4) for a in axes}
                summary[f"{corpus}/{level}/{version}"] = {"rows": len(replies), "file": str(path.relative_to(OUT)),
                                                         "pooled_firing_rate": rates}
    out = OUT / "matcher_summary.json"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    out.write_text(json.dumps(summary, indent=1, sort_keys=True))
    print(json.dumps({k: v.get("rows", v) for k, v in summary.items()}, indent=1))


if __name__ == "__main__":
    main()
