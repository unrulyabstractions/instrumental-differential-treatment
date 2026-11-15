"""The Petri runs' append-only spend ledger with a hard cap that refuses (B73: $10 total, pilot $0.30).

A cell reserves, before it starts, its upper bound: transcripts x (Inspect's per-sample cost limit + the judge
bound). A reservation is refused when committed spend (reconciled actuals plus open reservations) plus the new
bound would pass the cap. After the cell, its reservation is replaced by the cost priced from its own logs.
Every line is appended; nothing is rewritten. Standard library only, so it runs in the Petri venv.

    tmp/petri_env/bin/python -m script.analysis.petri_20261115.petri_ledger status
    tmp/petri_env/bin/python -m script.analysis.petri_20261115.petri_ledger selftest
"""

from __future__ import annotations

import fcntl
import json
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LEDGER = REPO / "out/main/petri_20261115/spend_ledger.jsonl"


class Refused(SystemExit):
    pass


class Ledger:
    def __init__(self, path: Path = LEDGER, cap: float = 10.0, pilot_cap: float = 0.30) -> None:
        self.path, self.cap, self.pilot_cap = Path(path), cap, pilot_cap

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
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **event}, sort_keys=True) + "\n")

    def stages(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.events():
            s = out.setdefault(e["stage"], {})
            if e["event"] == "reserve":
                s.update(bound=e["bound_usd"], pilot=e.get("pilot", False))
            elif e["event"] == "reconcile":
                s["actual"] = e["actual_usd"]
        return {k: v for k, v in out.items() if "bound" in v}

    def committed(self, pilot_only: bool = False) -> float:
        return sum((s["actual"] if s.get("actual") is not None else s["bound"])
                   for s in self.stages().values() if s.get("pilot") or not pilot_only)

    def reserve(self, stage: str, bound_usd: float, pilot: bool = False, **detail) -> float:
        with self._locked():
            if stage in self.stages():
                raise Refused(f"REFUSED: {stage} already holds a reservation")
            committed = self.committed()
            base = {"stage": stage, "bound_usd": round(bound_usd, 6), "pilot": pilot,
                    "committed_before_usd": round(committed, 6), "cap_usd": self.cap, **detail}
            reason = None
            if committed + bound_usd > self.cap:
                reason = f"${committed + bound_usd:.4f} would pass the ${self.cap:.2f} cap"
            elif pilot and self.committed(pilot_only=True) + bound_usd > self.pilot_cap:
                reason = f"the pilot would pass its ${self.pilot_cap:.2f} cap"
            if reason:
                self._append({"event": "refuse", "reason": reason, **base})
                raise Refused(f"REFUSED: {reason} ({stage})")
            self._append({"event": "reserve", **base})
            return committed + bound_usd

    def reconcile(self, stage: str, actual_usd: float, **detail) -> None:
        with self._locked():
            self._append({"event": "reconcile", "stage": stage, "actual_usd": round(actual_usd, 6), **detail})


def selftest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl", cap=1.0, pilot_cap=0.2)
        led.reserve("pilot", 0.15, pilot=True)
        for stage, bound, pilot in (("pilot2", 0.10, True), ("big", 0.90, False)):
            try:
                led.reserve(stage, bound, pilot=pilot)
            except Refused:
                continue
            raise SystemExit(f"selftest: {stage} was not refused")
        led.reconcile("pilot", 0.05)
        led.reserve("cell", 0.90)
        try:
            led.reserve("cell", 0.01)
        except Refused:
            pass
        else:
            raise SystemExit("selftest: a second reservation of one stage was allowed")
        assert abs(led.committed() - 0.95) < 1e-9, led.committed()
    print("ledger selftest passed")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        led = Ledger()
        print(json.dumps({"committed_usd": round(led.committed(), 4), "stages": led.stages()}, indent=1))
