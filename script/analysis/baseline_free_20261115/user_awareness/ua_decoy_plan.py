"""The registered m rule and the per-call cost it reads from the ledger.

``choose_m`` is the rule fixed in REGISTRATION.json before the pilot: the largest
equal number of decoys m that fits every kept subject under the cap at the
pilot's mean cost per call, dropping the dearest subject while m < 12.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from script.analysis.baseline_free_20261115.user_awareness.ua_spend_ledger import (
    ANALYSIS_CAP_USD, WORKFLOW_CAP_USD)

CALLS_PER_PERSONA = 64
N_ORIGINALS = 10
MAX_DECOYS = 32
MIN_DECOYS = 12
STOP_FACTOR = 1.25
PILOT_PREFIX = "pilot__"


def running_cost(ledger: Path, model: str, phase: str) -> dict:
    """Mean cost per call slot for one model in one phase ('pilot' or 'session').

    A slot is one (prompt id, sample); its retries and errored attempts are charged
    to it, so the mean is what one planned call really costs.
    """
    slots, cost, tokens_out = set(), 0.0, []
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("model") != model or r.get("status") == "refused_cap":
                continue
            tag = r.get("tag", "")
            if (phase == "pilot") != tag.startswith(PILOT_PREFIX):
                continue
            slots.add(tag.split("#a")[0])
            cost += float(r.get("cost_usd") or 0.0)
            if r.get("status") == "ok":
                tokens_out.append(int(r.get("completion_tokens") or 0))
    n = len(slots)
    return {"phase": phase, "n_call_slots": n, "cost_usd": cost,
            "mean_cost_per_call": cost / n if n else None,
            "mean_completion_tokens": sum(tokens_out) / len(tokens_out) if tokens_out else None,
            "max_completion_tokens": max(tokens_out) if tokens_out else None}


def choose_m(cost_per_call: dict[str, float], spent: dict) -> dict:
    """The registered rule, with every step of the drop loop recorded."""
    budget = min(ANALYSIS_CAP_USD - spent["analysis_usd"], WORKFLOW_CAP_USD - spent["workflow_usd"])
    kept = [s for s, c in cost_per_call.items() if c is not None]
    dropped, steps = [s for s, c in cost_per_call.items() if c is None], []
    m = 0
    while kept:
        total = sum(cost_per_call[s] for s in kept)
        m_raw = math.floor(budget / (CALLS_PER_PERSONA * total)) - N_ORIGINALS
        steps.append({"kept": list(kept), "sum_cost_per_call": total, "m_raw": m_raw})
        if m_raw >= MIN_DECOYS:
            m = min(m_raw, MAX_DECOYS)
            break
        dearest = max(kept, key=lambda s: cost_per_call[s])
        kept.remove(dearest)
        dropped.append(dearest)
    planned = sum(cost_per_call[s] for s in kept) * CALLS_PER_PERSONA * (N_ORIGINALS + m)
    return {"budget_after_pilot_usd": budget, "cost_per_call": cost_per_call, "steps": steps,
            "kept": kept, "dropped": dropped, "m": m if kept else 0,
            "planned_session_cost_usd": planned if kept else 0.0}
