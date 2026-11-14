"""Row checks on a finished pooled-base draw (no spend).

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_draw_checks.py --draw c1

Checks that the draw holds exactly base B's (prompt_id, s) keys, no failed row,
no two equal texts within one prompt, and no text equal to any of base A's or
base B's (or the other draw's, when it exists). Writes ``<draw>/draw_checks.json``
and exits 1 on any failure. Refuses to overwrite.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AB = REPO / "out/main/auditbench"
ITEM = AB / "pooled_base_20261113"
BASE_A = AB / "contextual_optimism/responses/responses_base.jsonl"
BASE_B = AB / "nullext/base_B/responses/responses_base.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.open(encoding="utf-8") if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draw", required=True)
    a = ap.parse_args()
    out = ITEM / a.draw / "draw_checks.json"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    rows = read_jsonl(ITEM / a.draw / "responses_base.jsonl")
    b, base_a = read_jsonl(BASE_B), read_jsonl(BASE_A)
    keys = Counter((r["prompt_id"], int(r["s"])) for r in rows)
    keys_b = {(r["prompt_id"], int(r["s"])) for r in b}
    within = Counter((r["prompt_id"], r["text"]) for r in rows)
    others = {r["text"] for r in b} | {r["text"] for r in base_a}
    other_draw = "c2" if a.draw == "c1" else "c1"
    other_path = ITEM / other_draw / "responses_base.jsonl"
    other_texts = {r["text"] for r in read_jsonl(other_path)} if other_path.exists() else set()
    rec = {"draw": a.draw, "rows": len(rows), "distinct_keys": len(keys),
           "keys_equal_base_B": set(keys) == keys_b, "duplicate_keys": sum(v - 1 for v in keys.values()),
           "failed_rows": sum(1 for r in rows if r["failed"]),
           "refused_rows": sum(1 for r in rows if r["refused"]),
           "empty_texts": sum(1 for r in rows if not r["text"].strip()),
           "duplicate_texts_within_prompt": sum(v - 1 for v in within.values()),
           "texts_equal_base_A_or_B": sum(1 for r in rows if r["text"] in others),
           "other_draw_checked": other_path.exists(),
           "texts_equal_other_draw": sum(1 for r in rows if r["text"] in other_texts),
           "seed_label": (ITEM / a.draw / "seed_label.txt").read_text().strip()}
    rec["pass"] = (rec["rows"] == 3456 and rec["keys_equal_base_B"] and rec["duplicate_keys"] == 0
                   and rec["failed_rows"] == 0 and rec["empty_texts"] == 0
                   and rec["duplicate_texts_within_prompt"] == 0
                   and rec["texts_equal_base_A_or_B"] == 0 and rec["texts_equal_other_draw"] == 0)
    out.write_text(json.dumps(rec, indent=2))
    print(json.dumps(rec, indent=1))
    if not rec["pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
