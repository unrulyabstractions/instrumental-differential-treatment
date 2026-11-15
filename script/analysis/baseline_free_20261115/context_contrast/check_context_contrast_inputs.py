"""Cross-check this family's input digests against the workflow's subject registry. No spend.

    uv run python -m script.analysis.baseline_free_20261115.context_contrast.check_context_contrast_inputs

Every verdict file this family read is recorded with its sha256 in
``runs/*.json``. The workflow's subject registry records a sha256 for every
subject it hashed. A file both list must carry the same digest, or the two
read different data. Writes ``checks/inputs_against_registry.json`` and exits
non-zero on any disagreement.
"""

from __future__ import annotations

import json
import sys

from script.analysis.baseline_free_20261115.context_contrast.context_contrast_runs import OUT
from src.common.experiment_layout import MAIN

REGISTRY = MAIN / "baseline_free_20261115" / "subjects_registry" / "subjects.json"


def main() -> None:
    reg = json.loads(REGISTRY.read_text())
    by_path: dict[str, set] = {}
    for s in reg["subjects"]:
        for field, path_key in (("verdicts", "verdicts"), ("base", "base")):
            path = s.get(path_key)
            digest = (s.get("sha256") or {}).get(field)
            if path and digest:
                by_path.setdefault(path, set()).add(digest)
    rows = []
    for f in sorted((OUT / "runs").glob("*.json")):
        inp = json.loads(f.read_text())["inputs"]
        for path, digest in ((inp.get("verdicts"), inp.get("sha256")),
                             (inp.get("partner"), inp.get("partner_sha256"))):
            if not path or not digest:
                continue
            known = by_path.get(path)
            rows.append({"model": inp["key"], "path": path, "sha256": digest,
                         "in_registry": known is not None,
                         "match": None if known is None else known == {digest}})
    bad = [r for r in rows if r["match"] is False]
    record = {"registry": str(REGISTRY), "n_files": len(rows),
              "n_in_registry": sum(r["in_registry"] for r in rows),
              "n_match": sum(r["match"] is True for r in rows), "n_mismatch": len(bad),
              "not_in_registry": sorted({r["path"] for r in rows if not r["in_registry"]}),
              "rows": rows}
    path = OUT / "checks" / "inputs_against_registry.json"
    with path.open("x") as fh:
        json.dump(record, fh, indent=1)
    print({k: v for k, v in record.items() if k != "rows"})
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
