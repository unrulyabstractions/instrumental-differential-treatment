"""Spend-gated driver for the judge affordance pass, over the masked probe's runner.

    R=script/analysis/reanalysis_2026_11/affordance_judge_runner.py
    uv run --with tiktoken python $R credit-check
    uv run --with tiktoken python $R submit --stage-dir pilot
    uv run --with tiktoken python $R finish --stage-dir pilot
    uv run --with tiktoken python $R price
    uv run --with tiktoken python $R passes          # target, price check, base, finish both
    uv run --with tiktoken python $R ledger

Every command is the masked probe's runner (``masked_judge_runner.py``) with
its output folder, its ledgers and its cap moved to this pass. The runner's
``plan`` is not offered: stage dirs come from ``affordance_judge_prepare.py``,
whose plans carry the system prompt without the hidden-behavior line.

Spend is held two ways, as in the masked probe. ``ledger.jsonl`` reserves the
credit check's bound before the call and settles it from the returned usage.
The batch tool's ``spend_ledger.json`` reserves each batch's upper bound at
submit (counted input tokens at the input price plus every request's max output
tokens at the output price) and settles it from the returned usage at fetch.
Every submit refuses unless the committed total stays within the cap, and the
cap can never exceed ``HARD_CAP_USD``.

``price`` projects one pass from the pilot's returned usage. ``passes`` refuses
to start without a projection that fits, submits the target pass, prices its
first stage from returned usage when it lands, stops before the base pass if
that cost runs past the per-pass estimate, and otherwise submits the base pass
and finishes both (retries, repairs, fold).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = REPO / "out/main/auditbench/contextual_optimism/affordance_judge_20261114"
HARD_CAP_USD = 5.0
#: The owner-facing estimate, $3.03 to $3.17 for the two passes, from the
#: masked probe's four measured passes of the same size ($1.498 to $1.521).
ESTIMATE_PER_PASS_HIGH_USD = 3.17 / 2
PASS_ARMS = ("target", "base")
PASS_REQUESTS = 1296


def _base():
    spec = importlib.util.spec_from_file_location("masked_judge_runner",
                                                  HERE / "masked_judge_runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.OUT = OUT
    mod.LEDGER = OUT / "ledger.jsonl"
    mod.BATCH_LEDGER = OUT / "spend_ledger.json"
    mod.SCORE_CONFIG = None  # planning belongs to affordance_judge_prepare.py
    return mod


R = _base()


def _cap(cap: float) -> float:
    if cap > HARD_CAP_USD:
        raise SystemExit(f"REFUSED: cap ${cap:.2f} is above the hard cap ${HARD_CAP_USD:.2f}")
    return cap


def _sd(name: str) -> Path:
    p = Path(name)
    p = p if p.is_absolute() else OUT / p
    if OUT not in p.parents:
        raise SystemExit(f"{p} is not a stage dir of {OUT}")
    if not (p / "judge_batch/plan.json").exists():
        raise SystemExit(f"{p} has no plan; run affordance_judge_prepare.py stage first")
    return p


def cmd_credit_check(a) -> None:
    R.cmd_credit_check(argparse.Namespace(cap=_cap(a.cap)))


def cmd_submit(a) -> None:
    sd = _sd(a.stage_dir)
    if sd.name.startswith("pass_"):
        raise SystemExit("pass stage dirs go through `passes`, which checks the projection first")
    if not R.submit(sd, a.stage, _cap(a.cap), a.dry_run):
        raise SystemExit(1)


def cmd_finish(a) -> None:
    R.cmd_finish(argparse.Namespace(stage_dir=str(_sd(a.stage_dir)), cap=_cap(a.cap), poll=a.poll))


def _fetched_usd(sd: Path, stage: str) -> float:
    return json.loads((sd / f"judge_batch/fetched_{stage}.json").read_text())["actual_usd"]


def cmd_price(a) -> None:
    """Project one pass from the pilot's returned usage, and check the cap."""
    cap = _cap(a.cap)
    path = OUT / "pilot_projection.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    usd, tin = [], []
    for line in (OUT / "pilot/judge_batch/raw_first.jsonl").read_text().splitlines():
        u = json.loads(line)["response"]["body"]["usage"]
        usd.append((u["prompt_tokens"] * R.BATCH_PRICE["in"]
                    + u["completion_tokens"] * R.BATCH_PRICE["out"]) / 1e6)
        tin.append(u["prompt_tokens"])
    mean, se = st.mean(usd), st.stdev(usd) / len(usd) ** 0.5
    conservative = mean + 3 * se
    spent = R.committed()
    per_pass_mean, per_pass_cons = PASS_REQUESTS * mean, PASS_REQUESTS * conservative
    bounds = {}
    for arm in PASS_ARMS:
        tokens_file = OUT / f"pass_{arm}/judge_batch/tokens_first.json"
        if not tokens_file.exists():
            R.run("count", "--stage-dir", str(OUT / f"pass_{arm}"), "--stage", "first")
        t = json.loads(tokens_file.read_text())
        bounds[arm] = (t["input_tokens"] * R.BATCH_PRICE["in"]
                       + t["max_output_tokens"] * R.BATCH_PRICE["out"]) / 1e6
    stop_at = max(per_pass_cons, ESTIMATE_PER_PASS_HIGH_USD)
    rep = {"cap_usd": cap, "hard_cap_usd": HARD_CAP_USD, "pilot_requests": len(usd),
           "pilot_usd": round(sum(usd), 6), "pilot_input_tokens_mean": round(st.mean(tin), 1),
           "usd_per_request_mean": round(mean, 7), "usd_per_request_se": round(se, 7),
           "usd_per_request_conservative": round(conservative, 7),
           "requests_per_pass": PASS_REQUESTS,
           "projected_per_pass_usd_mean": round(per_pass_mean, 4),
           "projected_per_pass_usd_conservative": round(per_pass_cons, 4),
           "pass_bound_usd": {k: round(v, 6) for k, v in bounds.items()},
           "committed_before_passes_usd": round(spent, 6),
           "projected_total_usd_conservative": round(spent + 2 * per_pass_cons, 4),
           "worst_case_total_usd": round(spent + sum(bounds.values()), 4),
           "stop_if_a_first_stage_costs_more_than_usd": round(stop_at, 4),
           "stop_rule": ("the larger of the pilot's conservative per-pass projection and the "
                         "high end of the owner-facing estimate per pass ($3.17 / 2)"),
           "fits": bool(spent + 2 * per_pass_cons <= cap and spent + sum(bounds.values()) <= cap)}
    path.write_text(json.dumps(rep, indent=2, sort_keys=True))
    print(json.dumps(rep, indent=1))


def cmd_passes(a) -> None:
    cap = _cap(a.cap)
    proj_path = OUT / "pilot_projection.json"
    if not proj_path.exists():
        raise SystemExit("no pilot_projection.json; run `price` after the pilot")
    proj = json.loads(proj_path.read_text())
    if not proj["fits"]:
        raise SystemExit(f"the projection does not fit the cap: {proj}")
    stop_at = proj["stop_if_a_first_stage_costs_more_than_usd"]
    sds = {arm: _sd(f"pass_{arm}") for arm in PASS_ARMS}
    for arm in PASS_ARMS:
        sd = sds[arm]
        if "first" not in R._submitted(sd) and not R.submit(sd, "first", cap):
            raise SystemExit(f"stopped: pass_{arm} first stage refused by the cap")
        R.fetch_pending(sd, a.poll)
        actual = _fetched_usd(sd, "first")
        ok = actual <= stop_at
        R.append({"event": "priced_vs_estimate", "stage_dir": str(sd.relative_to(REPO)),
                  "stage": "first", "actual_usd": actual, "stop_at_usd": stop_at,
                  "projected_mean_usd": proj["projected_per_pass_usd_mean"], "ok": ok,
                  "committed_usd_after": round(R.committed(), 6)})
        R.log(f"pass_{arm} first stage ${actual:.4f} against stop line ${stop_at:.4f}: "
              f"{'ok' if ok else 'OVER'}")
        if not ok:
            raise SystemExit(f"ALARM: pass_{arm} first stage cost ${actual:.4f}, past ${stop_at:.4f}")
    for arm in PASS_ARMS:
        R.cmd_finish(argparse.Namespace(stage_dir=str(sds[arm]), cap=cap, poll=a.poll))
    R.log(f"passes done; committed ${R.committed():.4f} of ${cap:.2f}")


def cmd_ledger(a) -> None:
    R.cmd_ledger(a)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("credit-check", "submit", "finish", "price", "passes"):
        p = sub.add_parser(name)
        p.add_argument("--cap", type=float, default=HARD_CAP_USD)
        if name in ("submit", "finish"):
            p.add_argument("--stage-dir", required=True)
        if name == "submit":
            p.add_argument("--stage", default="first")
            p.add_argument("--dry-run", action="store_true")
        if name in ("finish", "passes"):
            p.add_argument("--poll", type=int, default=30)
    sub.add_parser("ledger")
    a = ap.parse_args()
    {"credit-check": cmd_credit_check, "submit": cmd_submit, "finish": cmd_finish,
     "price": cmd_price, "passes": cmd_passes, "ledger": cmd_ledger}[a.cmd](a)


if __name__ == "__main__":
    main()
