"""The registered judge-free fact matcher (M1 and M1a of the prompted ceiling, hash-checked) on every corpus.

    uv run python -m script.analysis.court_weights_20261115.cw_matcher

Writes verdicts/<corpus>/matcher_<version>.jsonl in the project's verdict-row format, with the eight facts, the
``f_equal_terms`` control and the four derived axes (m_any_pro, m_any_con, m_more_con, m_more_pro). A corpus
whose replies are not all present is skipped and named. No file is overwritten. Free: no model call.
"""

from __future__ import annotations

import json

from script.analysis.court_oracle_axes.court_oracle_fact_matcher import derived, fact_check, load_matcher
from script.analysis.court_weights_20261115.cw_common import CORPORA, KEY_FIELDS, VERDICTS, load_replies


def main() -> None:
    for version in ("M1", "M1a"):
        ns = load_matcher(version)
        fact_check(ns)
        for corpus in CORPORA:
            path = VERDICTS / corpus / f"matcher_{version}.jsonl"
            if path.exists():
                print(f"{path} exists; kept")
                continue
            try:
                rows = load_replies(corpus)
            except SystemExit as exc:
                print(f"{corpus}: skipped ({exc})")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as fh:
                for r in rows:
                    v = derived(ns["match"](r["text"]))
                    fh.write(json.dumps({**{k: r[k] for k in KEY_FIELDS}, "judge": f"matcher_{version}",
                                         "verdicts": v}, sort_keys=True) + "\n")
            print(f"{path}: {len(rows)} rows")


if __name__ == "__main__":
    main()
