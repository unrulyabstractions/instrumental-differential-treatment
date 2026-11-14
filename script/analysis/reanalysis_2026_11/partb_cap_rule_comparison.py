"""How the earlier punctuation rule for "complete" compares with the token count.

    uv run python script/analysis/reanalysis_2026_11/partb_cap_rule_comparison.py

``script/analysis/truncation_check.py`` (B63) called a reply complete when its
last character is terminal punctuation. Part (d) calls it capped when its
re-encoded length reaches the 400-token cap. For every reply file part (d)
reads, this counts the replies each rule calls complete, and how many replies
the punctuation rule calls complete although they sit at the cap. Writes
``partB/cap_rule_comparison.json``.
"""

from __future__ import annotations

import re

from partb_run_sources import OUT, REPLY_CAP
from partb_token_cap_flags import DIR as TOKENS, reply_files, slug
from src.common.file_io import load_json, read_jsonl, save_json

# The pattern truncation_check.py uses, copied so this script does not import it.
ENDS = re.compile(r"[.!?)\]\"'*`:]\s*$")


def main() -> None:
    path = OUT / "cap_rule_comparison.json"
    if path.exists():
        raise SystemExit(f"{path} exists; part B never overwrites")
    out = {}
    for f in reply_files():
        tokens = load_json(TOKENS / f"{slug(f)}.json")["tokens"]
        n = punct = token_complete = punct_but_capped = 0
        for r in read_jsonl(f):
            text = (r.get("text") or "").rstrip()
            ends = bool(text) and bool(ENDS.search(text))
            capped = tokens[f"{r['prompt_id']}|{int(r['s'])}"] >= REPLY_CAP - 1
            n += 1
            punct += ends
            token_complete += not capped
            punct_but_capped += ends and capped
        out[str(f)] = {"n": n, "complete_by_punctuation": punct,
                       "complete_by_token_count": token_complete,
                       "punctuation_complete_but_at_cap": punct_but_capped}
        print(f"{slug(f):80s} n={n} punct={punct} tokens={token_complete} "
              f"punct_but_capped={punct_but_capped}", flush=True)
    save_json(path, {"punctuation_rule": ENDS.pattern, "capped_rule": "tokens >= 399",
                     "files": out})


if __name__ == "__main__":
    main()
