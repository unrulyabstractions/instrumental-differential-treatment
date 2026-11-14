"""The court ceiling's append-only spend ledger, with a hard cap that refuses.

Registration amendment 1 (A7) fixes the rule. Each batch reserves, before it
is submitted, its counted input tokens at the input price plus 800 output
tokens per call at the output price. A reservation is refused when actual
spend plus open reservations plus the new one would pass the $25 cap, and a
pilot reservation also when the pilot's total would pass $0.50. A fetched batch
replaces its reservation with its billed usage. Every reservation, refusal,
submission, release and reconciliation is one appended line; nothing in the
file is ever rewritten.

    uv run python -m script.analysis.court_oracle_axes.court_oracle_spend_ledger selftest
    uv run python -m script.analysis.court_oracle_axes.court_oracle_spend_ledger prove-refusal --bound 36.77
    uv run python -m script.analysis.court_oracle_axes.court_oracle_spend_ledger status
"""

from __future__ import annotations

import argparse
import fcntl
import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from script.analysis.court_oracle_axes.court_oracle_axis_blocks import OUT

LEDGER = OUT / "spend_ledger.jsonl"
CAP_USD = 25.0
PILOT_CAP_USD = 0.50


class Refused(SystemExit):
    """A reservation the cap does not allow. Nothing is submitted."""


class SpendLedger:
    def __init__(self, path: Path = LEDGER, cap: float = CAP_USD,
                 pilot_cap: float = PILOT_CAP_USD) -> None:
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
        event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **event}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    def stages(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.events():
            s = out.setdefault(e.get("stage", ""), {})
            if e["event"] == "reserve":
                s.update(bound=e["bound_usd"], pilot=e.get("pilot", False))
            elif e["event"] == "reconcile":
                s["actual"] = e["actual_usd"]
            elif e["event"] == "release":
                s["released"] = True
            elif e["event"] == "submitted":
                s["batch_id"] = e["batch_id"]
        return {k: v for k, v in out.items() if "bound" in v}

    @staticmethod
    def _cost(s: dict) -> float:
        if s.get("released"):
            return 0.0
        return s["actual"] if s.get("actual") is not None else s["bound"]

    def committed(self, pilot_only: bool = False) -> float:
        return sum(self._cost(s) for s in self.stages().values()
                   if s.get("pilot") or not pilot_only)

    def actual(self) -> float:
        return sum(s.get("actual") or 0.0 for s in self.stages().values())

    def reserve(self, stage: str, bound_usd: float, detail: dict, pilot: bool = False,
                dry: bool = False) -> float:
        """Record a reservation, or record a refusal and raise ``Refused``."""
        with self._locked():
            if stage in self.stages():
                raise Refused(f"REFUSED: stage {stage} already holds a reservation")
            committed = self.committed()
            base = {"stage": stage, "bound_usd": round(bound_usd, 6), "pilot": pilot,
                    "committed_before_usd": round(committed, 6), "cap_usd": self.cap, **detail}
            reason = None
            if committed + bound_usd > self.cap:
                reason = f"${committed + bound_usd:.4f} would pass the ${self.cap:.2f} cap"
            elif pilot and self.committed(pilot_only=True) + bound_usd > self.pilot_cap:
                reason = f"the pilot would pass its ${self.pilot_cap:.2f} cap"
            if reason:
                self._append({"event": "refuse", "reason": reason, "dry": dry, **base})
                raise Refused(f"REFUSED: {reason} (stage {stage})")
            if dry:
                raise SystemExit("prove-refusal was given a bound the cap allows; nothing written")
            self._append({"event": "reserve", **base})
            return committed + bound_usd

    def submitted(self, stage: str, batch_id: str, **detail) -> None:
        with self._locked():
            self._append({"event": "submitted", "stage": stage, "batch_id": batch_id, **detail})

    def release(self, stage: str, reason: str) -> None:
        with self._locked():
            self._append({"event": "release", "stage": stage, "reason": reason})

    def reconcile(self, stage: str, actual_usd: float, **detail) -> None:
        with self._locked():
            self._append({"event": "reconcile", "stage": stage,
                          "actual_usd": round(actual_usd, 6), **detail})


def selftest() -> None:
    """Exercise every refusal path on a throwaway ledger; any slip exits non-zero."""
    with tempfile.TemporaryDirectory() as tmp:
        led = SpendLedger(Path(tmp) / "l.jsonl")

        def refused(fn) -> bool:
            try:
                fn()
            except Refused:
                return True
            return False
        checks = {
            "refuses 25.01 at $0": refused(lambda: led.reserve("a", 25.01, {})),
            "refusal costs nothing": led.committed() == 0.0,
            "accepts 20": not refused(lambda: led.reserve("b", 20.0, {})),
            "refuses 5.01 on top of 20": refused(lambda: led.reserve("c", 5.01, {})),
            "accepts exactly the cap": not refused(lambda: led.reserve("d", 5.0, {})),
        }
        led.reconcile("b", 3.0)
        checks["reconcile frees the bound"] = abs(led.committed() - 8.0) < 1e-9
        checks["accepts 17 after reconcile"] = not refused(lambda: led.reserve("e", 17.0, {}))
        checks["refuses 0.01 at the cap"] = refused(lambda: led.reserve("f", 0.01, {}))
        checks["refuses a second reservation of one stage"] = refused(lambda: led.reserve("e", 0.0, {}))
        led.release("e", "test")
        checks["release frees the bound"] = abs(led.committed() - 8.0) < 1e-9
        checks["pilot cap refuses 0.51"] = refused(lambda: led.reserve("p1", 0.51, {}, pilot=True))
        checks["pilot accepts 0.30"] = not refused(lambda: led.reserve("p2", 0.30, {}, pilot=True))
        checks["pilot refuses 0.21 more"] = refused(lambda: led.reserve("p3", 0.21, {}, pilot=True))
        checks["only reserve/refuse/reconcile/release lines"] = all(
            e["event"] in {"reserve", "refuse", "reconcile", "release"} for e in led.events())
    for name, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + name)
    if not all(checks.values()):
        raise SystemExit("ledger selftest FAILED")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    p = sub.add_parser("prove-refusal")
    p.add_argument("--bound", type=float, required=True)
    p.add_argument("--stage", default="cap_proof")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
    elif a.cmd == "prove-refusal":
        led = SpendLedger()
        print(f"committed before: ${led.committed():.4f}; actual ${led.actual():.4f}")
        try:
            led.reserve(a.stage, a.bound, {"purpose": "refusal proof, no API call"}, dry=True)
        except Refused as exc:
            print(exc)
            print(f"committed after: ${led.committed():.4f}")
    else:
        led = SpendLedger()
        print(json.dumps({"committed_usd": round(led.committed(), 6), "actual_usd": round(led.actual(), 6),
                          "cap_usd": led.cap, "stages": led.stages()}, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
