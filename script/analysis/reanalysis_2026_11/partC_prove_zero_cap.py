"""Prove that a $0 cap refuses before any request leaves, for both paid seats.

    uv run python script/analysis/reanalysis_2026_11/partC_prove_zero_cap.py

Writes out/main/reanalysis_20261113/partC/zero_cap_proof.json and logs the two
refusals (cost $0) in part C's spend ledger. No request is sent: the create
method behind the cap is replaced by a counter that must stay at zero.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from partC_capped_api_runner import LEDGER, prove_zero_cap_refuses  # noqa: E402
from partC_reanalysis_io import PART_C, write_new_json  # noqa: E402


def main() -> None:
    result = prove_zero_cap_refuses(LEDGER)
    out = write_new_json(PART_C / "zero_cap_proof.json",
                         {"ts": datetime.now(timezone.utc).isoformat(),
                          "ledger": str(LEDGER), "result": result})
    print(result)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
