"""Write the control-vs-control comparison the explorer reads.

    uv run python script/geometry/build_control_comparison.py

Reads the six null controls' verdicts and cached embeddings, both against the one
shared base they were collected on, and writes out/main/auditbench/shared/control_comparison.json.
Run script/geometry/build_semantic_bridge.py for each control first so the
embeddings are cached.
"""

from __future__ import annotations

from pathlib import Path

from src.common.file_io import save_json
from src.geometry.control_comparison import compute_control_comparison

AXES = Path("out/main/auditbench/contextual_optimism/conjecture/scoring_questions.json")
CONTROLS_ROOT = Path("out/main/auditbench/controls")
SHARED = Path("out/main/auditbench/shared")


def main() -> None:
    result = compute_control_comparison(AXES, CONTROLS_ROOT)
    out = SHARED / "control_comparison.json"
    save_json(out, result)
    ax = result["behavior_axes"]["off_diagonal_mean"]
    em = result["embedding"]["off_diagonal_mean"]
    print(f"wrote {out}")
    print(f"  mean off-diagonal cosine: behavior axes {ax}, embedding {em}")
    print(f"  embedding map variance explained: {result['embedding']['variance_explained']}")


if __name__ == "__main__":
    main()
