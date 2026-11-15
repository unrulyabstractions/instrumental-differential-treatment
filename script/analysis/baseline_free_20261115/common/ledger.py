"""The shared spend ledger of the baseline-free workflow, with hard caps that refuse.

Caps (B72 workflow): $5 for the whole workflow, $3 for any one analysis.

An analysis reserves its upper bound BEFORE any paid call. A reservation is
refused when the workflow's committed spend (reconciled actuals plus open
reservations, over every family) plus the new bound would pass $5, or when the
analysis's own committed spend plus the bound would pass $3. After the calls,
the reservation is reconciled with the cost priced from the calls' returned
usage. Every line is appended under a file lock; nothing is rewritten.

The ledger stores no key, no account name and no personal detail.

    .venv/bin/python -m script.analysis.baseline_free_20261115.common.ledger status
    .venv/bin/python -m script.analysis.baseline_free_20261115.common.ledger selftest
"""

from __future__ import annotations

import fcntl
import json
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from script.analysis.baseline_free_20261115.common.settings import (ANALYSIS_CAP_USD,
                                                                   OUT_ROOT,
                                                                   WORKFLOW_CAP_USD)

LEDGER = OUT_ROOT / "spend_ledger.jsonl"


class Refused(SystemExit):
    pass


class Ledger:
    def __init__(self, path: Path = LEDGER, workflow_cap: float = WORKFLOW_CAP_USD,
                 analysis_cap: float = ANALYSIS_CAP_USD) -> None:
        self.path = Path(path)
        self.workflow_cap, self.analysis_cap = workflow_cap, analysis_cap

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(".lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]

    def _append(self, event: dict) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **event},
                                sort_keys=True) + "\n")

    def reservations(self) -> dict[str, dict]:
        """Every reservation by id: family, analysis, bound and (once known) actual."""
        out: dict[str, dict] = {}
        for e in self.events():
            if e["event"] == "reserve":
                out[e["reservation"]] = {"family": e["family"], "analysis": e["analysis"],
                                         "bound": e["bound_usd"], "actual": None}
            elif e["event"] == "reconcile" and e["reservation"] in out:
                out[e["reservation"]]["actual"] = e["actual_usd"]
        return out

    @staticmethod
    def _cost(r: dict) -> float:
        return r["actual"] if r["actual"] is not None else r["bound"]

    def committed(self, family: str | None = None, analysis: str | None = None) -> float:
        return sum(self._cost(r) for r in self.reservations().values()
                   if (family is None or r["family"] == family)
                   and (analysis is None or r["analysis"] == analysis))

    def reserve(self, family: str, analysis: str, bound_usd: float, priced_from: str,
                **detail) -> str:
        """Reserve ``bound_usd`` for one batch of paid calls; returns the reservation id.

        ``priced_from`` states how the bound was priced (model, token counts, rate).
        """
        if bound_usd <= 0:
            raise Refused("REFUSED: a reservation needs a positive bound")
        with self._locked():
            res = self.reservations()
            rid = f"{family}/{analysis}#{sum(1 for r in res.values() if r['family'] == family and r['analysis'] == analysis) + 1}"
            total = self.committed()
            mine = self.committed(family, analysis)
            base = {"reservation": rid, "family": family, "analysis": analysis,
                    "bound_usd": round(bound_usd, 6), "priced_from": priced_from,
                    "workflow_committed_before_usd": round(total, 6),
                    "analysis_committed_before_usd": round(mine, 6),
                    "workflow_cap_usd": self.workflow_cap,
                    "analysis_cap_usd": self.analysis_cap, **detail}
            reason = None
            if total + bound_usd > self.workflow_cap:
                reason = (f"${total + bound_usd:.4f} would pass the workflow's "
                          f"${self.workflow_cap:.2f} cap")
            elif mine + bound_usd > self.analysis_cap:
                reason = (f"${mine + bound_usd:.4f} would pass the analysis's "
                          f"${self.analysis_cap:.2f} cap")
            if reason:
                self._append({"event": "refuse", "reason": reason, **base})
                raise Refused(f"REFUSED: {reason} ({rid})")
            self._append({"event": "reserve", **base})
            return rid

    def reconcile(self, reservation: str, actual_usd: float, priced_from: str,
                  **detail) -> None:
        """Replace a reservation's bound with the cost priced from returned usage."""
        with self._locked():
            res = self.reservations()
            if reservation not in res:
                raise Refused(f"REFUSED: no reservation {reservation}")
            if res[reservation]["actual"] is not None:
                raise Refused(f"REFUSED: {reservation} is already reconciled")
            self._append({"event": "reconcile", "reservation": reservation,
                          "actual_usd": round(actual_usd, 6), "priced_from": priced_from,
                          "over_bound": actual_usd > res[reservation]["bound"], **detail})

    def status(self) -> dict:
        res = self.reservations()
        by: dict[str, float] = {}
        for r in res.values():
            key = f"{r['family']}/{r['analysis']}"
            by[key] = round(by.get(key, 0.0) + self._cost(r), 6)
        return {"ledger": str(self.path), "workflow_cap_usd": self.workflow_cap,
                "analysis_cap_usd": self.analysis_cap,
                "committed_usd": round(self.committed(), 6), "by_analysis": by,
                "open_reservations": [k for k, r in res.items() if r["actual"] is None]}


def selftest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl", workflow_cap=5.0, analysis_cap=3.0)
        a = led.reserve("fam1", "embed", 2.5, priced_from="test")
        for fam, an, bound in (("fam1", "embed", 0.6),   # analysis cap 3.0
                               ("fam2", "judge", 2.6)):  # workflow cap 5.0
            try:
                led.reserve(fam, an, bound, priced_from="test")
            except Refused:
                continue
            raise SystemExit(f"selftest: {fam}/{an} ${bound} was not refused")
        led.reconcile(a, 1.0, priced_from="test usage")
        try:
            led.reconcile(a, 0.5, priced_from="again")
        except Refused:
            pass
        else:
            raise SystemExit("selftest: a second reconcile was allowed")
        led.reserve("fam1", "embed", 2.0, priced_from="test")
        led.reserve("fam2", "judge", 2.0, priced_from="test")
        try:
            led.reserve("fam3", "x", 0.01, priced_from="test")
        except Refused:
            pass
        else:
            raise SystemExit("selftest: the workflow cap did not refuse")
        assert abs(led.committed() - 5.0) < 1e-9, led.committed()
        assert abs(led.committed("fam1", "embed") - 3.0) < 1e-9
        try:
            led.reserve("fam1", "zero", 0.0, priced_from="test")
        except Refused:
            pass
        else:
            raise SystemExit("selftest: a zero bound was allowed")
    print("ledger selftest passed")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        print(json.dumps(Ledger().status(), indent=1))
