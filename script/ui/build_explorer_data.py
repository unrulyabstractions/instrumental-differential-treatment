"""Distill every experiment into one JSON the explorer page embeds.

    uv run python script/ui/build_explorer_data.py

Reads the artifacts on disk, folds the millions of verdict rows into rate grids
and aggregates, samples real transcripts, and writes out/analysis/ui/explorer_data.json.
Nothing here recomputes a statistic; verdicts come from the stage-6 summaries as
written. The page reads this file and never touches out/ again.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from src.ui.explorer_bundle import build_explorer_bundle


def tag_nonfinite(value: object) -> object:
    """Replace every non-finite float with a tag the page's reviver restores.

    The statistics emit non-finite values on purpose: a zero-spread pair
    standardizes to an infinite t, and a never-firing base makes the
    common-mode ratio infinite. json.dumps would write them as the bare tokens
    Infinity/NaN, which are not JSON, and the page's strict JSON.parse would
    then throw before anything renders. Nulling them instead would misreport
    the strongest signal the design can produce as a missing one, so each
    becomes {"__nonfinite__": "inf" | "-inf" | "nan"} and the reviver in
    src/ui/explorer_template.html turns it back into the exact number.
    """
    if isinstance(value, float) and not math.isfinite(value):
        tag = "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
        return {"__nonfinite__": tag}
    if isinstance(value, dict):
        return {k: tag_nonfinite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [tag_nonfinite(v) for v in value]
    return value


def encode_explorer_json(bundle: dict) -> str:
    """Strict JSON for the page, with no bare Infinity/NaN token anywhere.

    allow_nan=False is the backstop: a non-finite float that somehow escapes
    the tagging walk fails the build loudly here, instead of writing a file
    that every browser's JSON.parse rejects at load.
    """
    return json.dumps(tag_nonfinite(bundle), separators=(",", ":"), allow_nan=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("out/analysis/ui/explorer_data.json"))
    ap.add_argument("--only", default="", help="comma-separated experiment keys")
    args = ap.parse_args()

    only = [k.strip() for k in args.only.split(",") if k.strip()] or None
    bundle = build_explorer_bundle(only=only)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = encode_explorer_json(bundle)
    args.out.write_text(text)

    present = sum(1 for v in bundle["verdicts"] if v.get("present"))
    print(f"wrote {args.out} ({len(text) / 1e6:.2f} MB)")
    print(f"  experiments: {len(bundle['experiments'])}, with a verdict: {present}")
    for v in bundle["verdicts"]:
        if not v.get("present"):
            print(f"  {v['key']:36} (no summary)")
            continue
        named = v.get("named") or ("unresolved" if v["rejects"] else "-")
        print(f"  {v['key']:36} S={v['statistic']:.2f} p={v['p']:.4f} "
              f"{'REJECT' if v['rejects'] else 'no    '} {named}")


if __name__ == "__main__":
    main()
