"""Decoy counts, replies, judging and compute per decoy set, each derived from cited figures.

Decoy counts follow the conformal arithmetic of the research report: a
pre-registered target among k candidates and m decoys has n_ref = m + k - 1
reference names, and its smallest attainable p is 1 / (n_ref + 1). The
registered rule rejects at p <= alpha, so p <= 0.05 needs m >= 20 - k and
p <= 0.01 needs m >= 100 - k. The plan draws max(20 - k, 15) decoys, the
report's 15 to 20 per roster.

Box time scales each model's stored sampling time linearly in its reply count,
on the model's own stored stack, plus the fixed phases of a box session. That
linear scaling is an approximation; the logs give one batch size per model.
"""

from __future__ import annotations

from decoy_plan_registry import BASELINE_ROLE, DECOY_SETS, DESIGN_LIMITS
from decoy_plan_sources import Figure, derive, jsonl_rows
from decoy_plan_timings import MODELS

REPORT = "out/main/baseline_free_research_20261115/REPORT.md"
VLOG = "VERIFICATION_LOG.md"
PLAN_FLOOR_M = 15


def decoys_needed(k: int, alpha: float) -> int:
    """Smallest m with 1 / (m + k) <= alpha."""
    n = 1
    while 1.0 / (n + k) > alpha + 1e-12:
        n += 1
    return n


def _rows(path: str) -> int:
    return sum(1 for _ in jsonl_rows(path))


def set_shape(key: str, facts: dict) -> dict:
    spec = DECOY_SETS[key]
    runs = [facts[r] for r in spec["runs"]]
    inst = {r["n_instructions"] for r in runs}
    samp = {r["samples_per_cell"] for r in runs}
    if len(inst) != 1 or len(samp) != 1:
        raise SystemExit(f"{key}: runs disagree on instructions {inst} or samples {samp}")
    k_min = min(r["k"] for r in runs)
    return {"k_min": k_min, "k_by_run": {r["run"]: r["k"] for r in runs},
            "n_instructions": inst.pop(), "samples_per_cell": samp.pop(),
            "m_min_at_0.05": decoys_needed(k_min, 0.05),
            "m_min_at_0.01": decoys_needed(k_min, 0.01),
            "m_plan": max(decoys_needed(k_min, 0.05), PLAN_FLOOR_M)}


def _per_decoy(key: str, shape: dict, facts: dict) -> Figure:
    run = DECOY_SETS[key]["runs"][0]
    return Figure(f"set.{key}.replies_per_decoy_per_model",
                  shape["n_instructions"] * shape["samples_per_cell"], "replies",
                  f"{BASELINE_ROLE} ; {facts[run]['target_table']}",
                  f"results[{run}|registered|full].n_instructions x (max s + 1) over the target "
                  "table rows")


def _m_figure(key: str, shape: dict, which: str) -> Figure:
    m = shape["m_plan"] if which == "plan" else shape[f"m_min_at_{which}"]
    return Figure(f"set.{key}.m_{which}", m, "decoys", f"{REPORT} ; {BASELINE_ROLE}",
                  "conformal p = (1 + #{reference >= target}) / (n_ref + 1), n_ref = m + k - 1; "
                  "k = min over the set's runs of len(results[run|registered|full].candidates)",
                  formula=("max(20 - k, 15)" if which == "plan" else
                           f"smallest m with 1/(m + k) <= {which}"))


def compute_minutes(key: str, m: int, per_decoy: int, figs: dict, models: list[str]) -> Figure:
    """Box or Mac minutes to sample ``m`` decoys on every model of the set."""
    spec, used, total = DECOY_SETS[key], [], 0.0
    stacks: dict[str, list[str]] = {}
    for model in models:
        tm = spec.get("time_model", model)
        stacks.setdefault(MODELS[tm][0], []).append(tm)
    for stack, members in stacks.items():
        if spec["compute"] == "4card":
            fixed = [figs[f"box.4card.{p}"] for p in ("create_to_ready", "stage_and_push_manifest",
                                                      "pull_capture_destroy")]
            install = max(figs["box.4card.push_and_install"], figs["box.4card.fetch_minutes"],
                          key=lambda f: f.value)
            init = figs[f"time.{stack}.engine_init_minutes"]
            total += sum(f.value for f in fixed) + install.value + init.value
            used += [*fixed, install, init]
        elif spec["compute"] == "l40s":
            wall = figs["box.1card.l40s.wall_minutes"]
            total += wall.value
            used.append(wall)
        for tm in members:
            secs, rows = figs[f"time.{tm}.seconds"], figs[f"time.{tm}.rows"]
            total += m * per_decoy / rows.value * secs.value / 60.0
            used += [secs, rows]
    seen, uniq = set(), []
    for f in used:
        if f.item not in seen:
            seen.add(f.item)
            uniq.append(f)
    return derive(f"set.{key}.compute_minutes.m{m}.{len(models)}models", total, "min",
                  "per stack: fixed phases + engine init (4card) or the observed box wall time "
                  "(l40s); plus per model m x replies_per_decoy / stored rows x stored seconds",
                  uniq)


def base_rows(key: str, facts: dict) -> int:
    tables = {facts[r]["target_table"] for r in DECOY_SETS[key]["runs"]}
    tables |= {facts[r]["base_table"] for r in DECOY_SETS[key]["runs"]}
    return sum(_rows(t) for t in sorted(tables))


def mac_rate() -> Figure:
    return Figure("compute.mac.usd_per_hour", 0.0, "USD/h", VLOG,
                  "2026-10-28 B40 hole-fill entry: 'Replies were sampled locally on this Mac "
                  "(transformers on MPS)'")


def design_limit(key: str) -> str | None:
    return DESIGN_LIMITS.get(key)
