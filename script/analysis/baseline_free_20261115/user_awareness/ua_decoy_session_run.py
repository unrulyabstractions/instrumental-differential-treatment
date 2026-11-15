"""The paid decoy session: zero-cap proof, pilot, then the registered collection.

    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_decoy_session_run proof
    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_decoy_session_run pilot
    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_decoy_session_run collect

Nothing is sent unless REGISTRATION.json is committed, unchanged, and on
origin/main. Each phase first reserves its bound in the workflow's shared ledger
(family ``user_awareness``, analysis ``decoy_session``), then every request
passes ``ua_spend_ledger`` against that bound, and the phase is reconciled with
its priced usage when it ends.
"""

from __future__ import annotations

import subprocess
import sys

from src.common.file_io import load_json, read_jsonl, save_json
from src.external.user_awareness_materials import (GRADING_EXCHANGES, GRADING_INSTRUCTION,
                                                  IDENTITIES, identity_system)
from src.runner.model_backend_router import resolve_backend

from script.analysis.baseline_free_20261115.common.ledger import Ledger as SharedLedger
from script.analysis.baseline_free_20261115.user_awareness.decoy_personas import ordered_decoys
from script.analysis.baseline_free_20261115.user_awareness.ua_decoy_plan import (
    STOP_FACTOR, choose_m, running_cost)
from script.analysis.baseline_free_20261115.user_awareness.ua_decoy_registration import (
    DRIVER, PILOT)
from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import (
    OUT, REPO, SUBJECTS)
from script.analysis.baseline_free_20261115.user_awareness.ua_grading_collect_copy import collect
from script.analysis.baseline_free_20261115.user_awareness.ua_spend_ledger import (
    ANALYSIS, FAMILY, CappedCreate, CapRefused, SpendLedger, worst_case_usd)

LEDGER = OUT / "request_spend_ledger.jsonl"
REG = OUT / "REGISTRATION.json"
MAX_NEW = DRIVER["max_new_tokens"]


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def require_registration_on_origin() -> str:
    rel = str(REG.relative_to(REPO))
    if _git("ls-files", "--error-unmatch", rel).returncode != 0:
        raise SystemExit("REGISTRATION.json is not tracked; commit it before any call")
    if _git("diff", "--quiet", "HEAD", "--", rel).returncode != 0:
        raise SystemExit("REGISTRATION.json differs from HEAD; refusing")
    sha = _git("log", "-1", "--format=%H", "--", rel).stdout.strip()
    if _git("merge-base", "--is-ancestor", sha, "origin/main").returncode != 0:
        raise SystemExit("the registration commit is not on origin/main; push it first")
    return sha


def capped_target(model: str, book: SpendLedger):
    target = resolve_backend("openai", model, max_retries=0)
    target._client.chat.completions.create = CappedCreate(
        target._client.chat.completions.create, book, model)
    return target


def _prompt_chars(ident: dict, qi: int) -> int:
    ex = GRADING_EXCHANGES[qi]
    return len(identity_system(ident)) + len(GRADING_INSTRUCTION.format(**ex))


def open_phase(bound: float, priced_from: str, **detail) -> tuple[SharedLedger, str, SpendLedger]:
    shared = SharedLedger()
    rid = shared.reserve(FAMILY, ANALYSIS, bound, priced_from=priced_from, **detail)
    before = SpendLedger(LEDGER, shared, phase_cap=0.0).spent()["analysis_usd"]
    return shared, rid, SpendLedger(LEDGER, shared, phase_cap=before + bound)


def close_phase(shared: SharedLedger, rid: str, book: SpendLedger, before: float) -> float:
    actual = book.spent()["analysis_usd"] - before
    shared.reconcile(rid, actual, priced_from=f"returned usage, rows of {LEDGER.name}")
    return actual


def proof() -> None:
    """A $0 phase cap refuses before anything leaves: the real create is a counter that stays 0."""
    sent = {"n": 0}
    book = SpendLedger(OUT / "zero_cap_proof_ledger.jsonl", None, phase_cap=0.0)
    target = capped_target("gpt-5-mini", book)
    target._client.chat.completions.create.real = lambda **_: sent.__setitem__("n", sent["n"] + 1)
    try:
        target.generate("s", "u", MAX_NEW)
        refused = False
    except CapRefused:
        refused = True
    save_json(OUT / "zero_cap_proof.json", {"refused": refused, "requests_sent": sent["n"]})
    print({"refused": refused, "requests_sent": sent["n"]})
    if not refused or sent["n"]:
        raise SystemExit("zero-cap proof failed")


def pilot() -> None:
    sha = require_registration_on_origin()
    idents = [i for i in IDENTITIES if i["key"] in PILOT["identities"]]
    bound = sum(worst_case_usd(spec["model"], _prompt_chars(i, qi), MAX_NEW)
                for spec in SUBJECTS.values() for i in idents for _ in PILOT["sample_ids"]
                for qi in range(len(GRADING_EXCHANGES)))
    shared, rid, book = open_phase(bound, "worst case: chars/2 input + 2000 output tokens, "
                                   "Standard price, 96 pilot calls", phase="pilot")
    before = book.spent()["analysis_usd"]
    out = {"registration_commit": sha, "shared_reservation": rid, "bound_usd": bound,
           "subjects": {}}
    try:
        for name, spec in SUBJECTS.items():
            counts = collect(capped_target(spec["model"], book), idents,
                             OUT / f"pilot_grades_{name}.jsonl", 4, MAX_NEW,
                             id_prefix=PILOT["prompt_id_prefix"], sample_ids=PILOT["sample_ids"],
                             extra={"subject": name, "phase": "pilot"})
            out["subjects"][name] = {"counts": counts,
                                     **running_cost(LEDGER, spec["model"], "pilot")}
            print(name, out["subjects"][name], flush=True)
    finally:
        out["pilot_actual_usd"] = close_phase(shared, rid, book, before)
    out["spent_after_pilot"] = SpendLedger(LEDGER, SharedLedger(), 0.0).spent()
    out["plan"] = choose_m({k: v["mean_cost_per_call"] for k, v in out["subjects"].items()},
                           out["spent_after_pilot"])
    save_json(OUT / "pilot.json", out)
    print(out["plan"], flush=True)


def collect_session() -> None:
    require_registration_on_origin()
    plan = load_json(OUT / "pilot.json")["plan"]
    bound = min(plan["budget_after_pilot_usd"], STOP_FACTOR * plan["planned_session_cost_usd"])
    shared, rid, book = open_phase(bound, "m rule: min(budget after pilot, 1.25 x planned at the "
                                   "pilot's mean cost per call)", phase="session", m=plan["m"])
    before = book.spent()["analysis_usd"]
    personas = list(IDENTITIES) + ordered_decoys()[: plan["m"]]
    log = {"plan": plan, "shared_reservation": rid, "bound_usd": bound,
           "subjects": {s: {"sampled": [], "not_sampled": []} for s in plan["kept"]}}
    stopped: set[str] = set()
    try:
        for persona in personas:
            for name in plan["kept"]:
                entry = log["subjects"][name]
                model = SUBJECTS[name]["model"]
                c = max(plan["cost_per_call"][name],
                        running_cost(LEDGER, model, "session")["mean_cost_per_call"] or 0.0)
                s = book.spent()
                need = 64 * STOP_FACTOR * c
                if name in stopped or (s["analysis_usd"] + need > book.phase_cap
                                       or s["workflow_usd"] + need > book.workflow_cap):
                    stopped.add(name)
                    entry["not_sampled"].append(persona["key"])
                    continue
                try:
                    counts = collect(capped_target(model, book), [persona],
                                     OUT / f"grades_{name}.jsonl", 4, MAX_NEW,
                                     extra={"subject": name, "phase": "session"})
                except CapRefused as exc:
                    stopped.add(name)
                    entry["cut_by_request_cap"] = {"persona": persona["key"], "error": str(exc)}
                    continue
                entry["sampled"].append({"persona": persona["key"], **counts})
                print(name, persona["key"], counts, f"${book.spent()['analysis_usd']:.4f}",
                      flush=True)
                save_json(OUT / "session_log.json", {**log, "spent": book.spent()})
    finally:
        log["session_actual_usd"] = close_phase(shared, rid, book, before)
        log["spent"] = book.spent()
        log["rows"] = {n: sum(1 for _ in read_jsonl(OUT / f"grades_{n}.jsonl"))
                       for n in plan["kept"]}
        save_json(OUT / "session_log.json", log)


if __name__ == "__main__":
    {"proof": proof, "pilot": pilot, "collect": collect_session}[sys.argv[1]]()
