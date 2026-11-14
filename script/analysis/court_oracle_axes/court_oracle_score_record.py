"""Write the court ceiling's score record: every verdict file, its rows and nulls, every batch and the spend.

Everything is read from the artifacts (fold reports, verdict rows, fetched
batch summaries and the ledger), so the record cannot disagree with them.

    uv run python -m script.analysis.court_oracle_axes.court_oracle_score_record
"""

from __future__ import annotations

import json

from script.analysis.court_oracle_axes.court_oracle_batch_plan import BATCHES
from script.analysis.court_oracle_axes.court_oracle_axis_blocks import OUT
from script.analysis.court_oracle_axes.court_oracle_spend_ledger import SpendLedger
from src.common.file_io import read_jsonl


def main() -> None:
    files = {}
    for path in sorted((OUT / "verdicts").glob("*/*/*.jsonl")):
        rows = list(read_jsonl(path))
        null_by_axis: dict[str, int] = {}
        for r in rows:
            for a, v in r["verdicts"].items():
                if v is None:
                    null_by_axis[a] = null_by_axis.get(a, 0) + 1
        unscorable = sum(all(v is None for v in r["verdicts"].values()) for r in rows)
        files[str(path.relative_to(OUT))] = {
            "corpus": path.parts[-3], "level": path.parts[-2], "rater": path.stem,
            "rows": len(rows), "null_verdicts": sum(null_by_axis.values()),
            "null_by_axis": null_by_axis, "all_null_rows": unscorable,
            "judge_field": sorted({r["judge"] for r in rows}), "block_field": sorted({r["block"] for r in rows})}
    batches = {}
    for d in sorted(BATCHES.iterdir()):
        f = json.loads((d / "fetched.json").read_text())
        batches[d.name] = {k: f[k] for k in ("batch_id", "n_requests", "n_results", "n_errors", "n_unparsed",
                                             "finish_reasons", "input_tokens", "output_tokens", "actual_usd")}
        batches[d.name]["errors"] = f["errors"]
    led = SpendLedger()
    record = {"verdict_files": files, "batches": batches,
              "calls_billed": sum(b["n_requests"] for b in batches.values()),
              "spend_usd_actual": round(led.actual(), 6), "spend_usd_committed": round(led.committed(), 6),
              "cap_usd": led.cap,
              "open_reservations": [k for k, s in led.stages().items() if s.get("actual") is None and not s.get("released")]}
    out = OUT / "score_record.json"
    with out.open("x") as fh:
        fh.write(json.dumps(record, indent=1, sort_keys=True))
    print(json.dumps({k: v for k, v in record.items() if k not in ("verdict_files", "batches")}, indent=1))
    print(len(files), "verdict files;", sum(v["rows"] for v in files.values()), "rows;",
          sum(v["null_verdicts"] for v in files.values()), "null verdicts")


if __name__ == "__main__":
    main()
