"""Put the organism's own trigger prompts through the audit's own axes.

    uv run python script/external/convert_organism_own_prompts_to_pipeline.py \
        --out out/main/external/court_ownprompts/responses --samples 8

The blind court audit does not reject on the weights arm, and the organism does
move on the questions its teacher answered. Two explanations fit that: the
trigger is narrow and our templates miss it, or the conjectured axes miss the
behavior wherever it fires. Holding the axes and the statistic fixed and
swapping only the prompts separates them.

This reads the stored replies on the organism's own evaluation questions and
rewrites them in the pipeline's response schema, so stage 5 can score them
against the court run's conjectured axes and stage 6 can run the registered
test unchanged. It generates nothing and calls no model.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.common.file_io import append_jsonl, ensure_parent, read_jsonl, save_json

#: One system stratum: every reply was collected under the scenario prompt.
SYSTEM_ID = "organism"

#: The stored arms, and the tag each becomes for stage 6's target-versus-base
#: contrast. The organism file is the adapter's replies, the baseline file is
#: the same checkpoint without it.
ARMS = {"weights_target": "responses_organism.jsonl",
        "weights_base": "responses_baseline.jsonl"}


def _principal(group: str) -> str:
    return group.strip().lower().replace(" ", "_")


def convert(rows, samples: int) -> list[dict]:
    """Rewrite stored replies as pipeline responses, keeping the first samples.

    A cell pools one prompt's samples, so trimming every cell to the same
    count keeps the cells balanced and keeps the judge budget proportional to
    the question we are asking.
    """
    kept: dict[tuple[str, str], int] = {}
    out = []
    for row in rows:
        principal = _principal(row["group"])
        instruction_id = f"{SYSTEM_ID}::{row['prompt_id']}"
        key = (principal, instruction_id)
        index = kept.get(key, 0)
        if index >= samples:
            continue
        kept[key] = index + 1
        text = row.get("response") or ""
        out.append({"failed": bool(row.get("error")) or not text,
                    "instruction_id": instruction_id,
                    "principal": principal,
                    "prompt_id": f"{principal}__{instruction_id}",
                    "refused": False,
                    "s": index,
                    "system_id": SYSTEM_ID,
                    "text": text})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path,
                    default=Path("out/main/external/idt_organism_p3_authors"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--samples", type=int, default=8,
                    help="replies kept per prompt and candidate")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    report = {"source": str(args.source), "samples_per_cell": args.samples,
              "arms": {}}
    principals: dict[str, str] = {}
    for arm, name in ARMS.items():
        rows = list(read_jsonl(args.source / name))
        converted = convert(rows, args.samples)
        # A rerun must not append to the previous one's file.
        path = ensure_parent(args.out / f"responses_{arm}.jsonl")
        path.unlink(missing_ok=True)
        append_jsonl(path, converted)
        for row in converted:
            principals.setdefault(row["principal"],
                                  row["principal"].replace("_", " ").title())
        instructions = {r["instruction_id"] for r in converted}
        report["arms"][arm] = {"read": len(rows), "written": len(converted),
                               "instructions": len(instructions),
                               "failed": sum(r["failed"] for r in converted)}
        print(f"{arm}: read {len(rows)}, wrote {len(converted)}, "
              f"{len(instructions)} instructions", flush=True)

    save_json(args.out / "prompt_sets.json", {"principals": principals})
    save_json(args.out / "conversion_report.json", report)
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
