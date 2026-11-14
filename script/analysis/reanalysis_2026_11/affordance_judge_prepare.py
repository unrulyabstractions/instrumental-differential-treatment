"""Judge affordance pass on contextual_optimism: the prompt variant and the stage dirs.

    P=script/analysis/reanalysis_2026_11/affordance_judge_prepare.py
    uv run python $P prompt          # build the variant, assert the one-line diff
    uv run python $P stage --name pilot
    uv run python $P stage --name pass

The judge's system prompt at level 2 carries one line that tells it a hidden
behavior may be present ("What you are told: The assistant may have a secret
loyalty ..."). Appendix F.4 says we do not know what that line does to the
verdicts. This pass judges the same rows with the same 25-axis registry as the
name-masked probe's unmasked passes, at the same seat, with that one line
removed. Everything else in every request is byte-equal to the stored
unmasked pass, and ``stage`` asserts it call by call.

* ``prompt``: builds the paper's level-2 system string, asserts it equals the
  string in every stored call of base B and of both stored unmasked passes,
  removes the one line, and asserts with a line diff that nothing else moved.
  Writes ``prompt_variant.json``.
* ``stage --name pilot``: the masked probe's unmasked pilot replies (15 per
  arm, copied byte for byte), planned with ``--limit-rows 10``: 20 calls.
* ``stage --name pass``: one stage dir per arm with the masked probe's
  unmasked pass replies (samples s < 6 of every prompt, 1,296 rows per arm,
  copied byte for byte), every row planned.

Planning runs the batch tool's own ``plan-auditbench`` in process, with the
tool's ``judge_system_prompt`` replaced by one that returns the variant, so
the screen, the axis shuffle, the chunks, the user prompts, the token caps and
the request lines all come from the tool unchanged. Every write refuses an
existing file. Nothing outside the output folder changes.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.common.affordance_levels import level_framing  # noqa: E402
from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.score.judge_prompts import judge_system_prompt  # noqa: E402

RUN = REPO / "out/main/auditbench/contextual_optimism"
OUT = RUN / "affordance_judge_20261114"
MASKED = RUN / "masked_judge_20261113"
SCORE_CONFIG = MASKED / "score_config.json"
SEAT_FROM = RUN / "judge_mini/verdicts_target.jsonl"
BASE_B_CALLS = REPO / "out/main/auditbench/nullext/base_B/responses/judge_batch/calls_first.jsonl"
TOOL = REPO / "script/data/batch_judge_fill.py"
LEVEL = 2
ARMS = ("target", "base")
LINE_PREFIX = "What you are told: "
PILOT_ROWS = 10


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_new(path: Path, obj) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _copy_new(src: Path, dst: Path) -> dict:
    if dst.exists():
        raise SystemExit(f"refusing to overwrite {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    a, b = src.read_bytes(), dst.read_bytes()
    if a != b:
        raise SystemExit(f"copy differs from its source: {dst}")
    return {"from": str(src.relative_to(REPO)), "bytes": len(b), "sha256": _sha(b)}


# -------------------------------------------------------------------- prompt
def original_system() -> str:
    cfg = load_json(SCORE_CONFIG)
    return judge_system_prompt(LEVEL, cfg.get("domain", ""), cfg.get("activation", ""))


def variant_of(system: str) -> tuple[str, str]:
    """The system string without its hidden-behavior line, and that line."""
    lines = system.split("\n")
    hits = [i for i, x in enumerate(lines) if x.startswith(LINE_PREFIX)]
    if len(hits) != 1:
        raise SystemExit(f"expected one line starting {LINE_PREFIX!r}, found {len(hits)}")
    removed = lines[hits[0]]
    if removed != LINE_PREFIX + level_framing(LEVEL):
        raise SystemExit(f"the line is not the level-{LEVEL} framing: {removed!r}")
    variant = "\n".join(lines[:hits[0]] + lines[hits[0] + 1:])
    diff = list(difflib.ndiff(lines, variant.split("\n")))
    minus = [d[2:] for d in diff if d.startswith("- ")]
    plus = [d[2:] for d in diff if d.startswith("+ ")]
    kept = [d[2:] for d in diff if d.startswith("  ")]
    if minus != [removed] or plus or kept != variant.split("\n"):
        raise SystemExit(f"the diff is not exactly one removed line: {diff}")
    if variant == system or len(system) - len(variant) != len(removed) + 1:
        raise SystemExit("the variant does not differ from the original by exactly the line")
    return variant, removed


def _stored_systems(path: Path) -> tuple[set[str], int]:
    systems, n = set(), 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            systems.add(json.loads(line)["system"])
            n += 1
    return systems, n


def stage_prompt(args) -> None:
    system = original_system()
    checks = {}
    for path in (BASE_B_CALLS, *(MASKED / f"pass_unmasked_{arm}/judge_batch/calls_first.jsonl"
                                 for arm in ARMS)):
        systems, n = _stored_systems(path)
        if systems != {system}:
            raise SystemExit(f"stored system strings in {path} differ from the level-{LEVEL} string")
        checks[str(path.relative_to(REPO))] = {"calls": n, "distinct_systems": len(systems),
                                               "equal_to_level2_string": True}
    variant, removed = variant_of(system)
    unified = list(difflib.unified_diff(system.split("\n"), variant.split("\n"),
                                        "with_line", "without_line", lineterm=""))
    _write_new(OUT / "prompt_variant.json", {
        "level": LEVEL, "score_config": str(SCORE_CONFIG.relative_to(REPO)),
        "original_system": system, "variant_system": variant, "removed_line": removed,
        "unified_diff": unified,
        "sha256": {"original": _sha(system.encode()), "variant": _sha(variant.encode())},
        "stored_system_checks": checks,
        "rule": ("the variant is the original split on newlines with the one line starting "
                 f"{LINE_PREFIX!r} removed; an ndiff of the two has exactly one '-' line, "
                 "no '+' line, and every other line unchanged")})
    print("\n".join(unified))


# -------------------------------------------------------------- stage dirs
def _tool():
    """The batch tool, loaded in process, with its system prompt swapped."""
    os.environ["IDT_BATCH_LEDGER"] = str(OUT / "spend_ledger.json")
    spec = importlib.util.spec_from_file_location("batch_judge_fill_tool", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    want = load_json(OUT / "prompt_variant.json")
    cfg = load_json(SCORE_CONFIG)

    def variant_prompt(level: int, domain: str = "", activation: str = "") -> str:
        if (level, domain, activation) != (LEVEL, cfg.get("domain", ""), cfg.get("activation", "")):
            raise SystemExit(f"unexpected prompt arguments: {(level, domain, activation)}")
        original = judge_system_prompt(level, domain, activation)
        if original != want["original_system"]:
            raise SystemExit("the level-2 string changed since prompt_variant.json was written")
        variant, _ = variant_of(original)
        if variant != want["variant_system"]:
            raise SystemExit("the variant differs from prompt_variant.json")
        return variant

    mod.judge_system_prompt = variant_prompt
    return mod


def _compare_calls(mine: Path, stored: Path, original: str, variant: str) -> dict:
    """Every call of ``mine`` against the stored call with its id: only the system moves."""
    ref = {r["custom_id"]: r for r in read_jsonl(stored)}
    rows = list(read_jsonl(mine))
    fields = ("kind", "seat", "prompt_id", "s", "start", "axis_ids", "user", "max_tokens")
    for r in rows:
        s = ref.get(r["custom_id"])
        if s is None:
            raise SystemExit(f"{mine}: {r['custom_id']} has no stored call")
        bad = [f for f in fields if r[f] != s[f]]
        if bad:
            raise SystemExit(f"{mine}: {r['custom_id']} differs from the stored call on {bad}")
        if s["system"] != original or r["system"] != variant:
            raise SystemExit(f"{mine}: {r['custom_id']} system is not original -> variant")
    return {"calls": len(rows), "stored_calls": len(ref), "fields_equal": list(fields),
            "system": "stored = original, mine = variant, on every call"}


def _compare_requests(mine: Path, stored: Path, original: str, variant: str) -> dict:
    """Every request line equals the stored line once the stored system is swapped."""
    ref = {r["custom_id"]: r for r in read_jsonl(stored)}
    n = 0
    for r in read_jsonl(mine):
        s = json.loads(json.dumps(ref[r["custom_id"]]))
        if s["body"]["messages"][0] != {"role": "system", "content": original}:
            raise SystemExit(f"{stored}: {r['custom_id']} stored system message is not the original")
        if r["body"]["messages"][0] != {"role": "system", "content": variant}:
            raise SystemExit(f"{mine}: {r['custom_id']} system message is not the variant")
        s["body"]["messages"][0]["content"] = variant
        if r != s:
            raise SystemExit(f"{mine}: {r['custom_id']} differs from the stored request beyond the system")
        n += 1
    return {"requests": n, "equal_to_stored_except_system": True}


def stage_stage(args) -> None:
    want = load_json(OUT / "prompt_variant.json")
    original, variant = want["original_system"], want["variant_system"]
    tool = _tool()
    os.chdir(REPO)
    if args.name == "pilot":
        dirs = {"pilot": (MASKED / "pilot_unmasked", ARMS, PILOT_ROWS)}
    else:
        rows = load_json(MASKED / "pass_rows.json")
        dirs = {f"pass_{arm}": (MASKED / f"pass_unmasked_{arm}", (arm,), 0) for arm in ARMS}
    report = {"variant_sha256": want["sha256"]["variant"], "dirs": {}}
    for name, (src, arms, limit) in dirs.items():
        sd = OUT / name
        copies = {arm: _copy_new(src / f"responses_{arm}.jsonl", sd / f"responses_{arm}.jsonl")
                  for arm in arms}
        if args.name == "pass":
            n = sum(1 for _ in read_jsonl(sd / f"responses_{arms[0]}.jsonl"))
            if n != rows["rows"][f"unmasked_{arms[0]}"]:
                raise SystemExit(f"{name}: {n} rows, pass_rows.json says {rows['rows']}")
        tool.cmd_plan_auditbench(argparse.Namespace(
            stage_dir=str(sd), score_config=str(SCORE_CONFIG.relative_to(REPO)),
            seat_from=str(SEAT_FROM.relative_to(REPO)), limit_rows=limit))
        plan, ref_plan = load_json(sd / "judge_batch/plan.json"), load_json(src / "judge_batch/plan.json")
        same = {k: plan[k] == ref_plan[k] for k in ("judge", "level", "model", "options", "n_axes",
                                                     "conjecture_dir", "seats", "seat_from")}
        if not all(same.values()):
            raise SystemExit(f"{name}: plan differs from the stored plan on {same}")
        report["dirs"][name] = {
            "copied_responses": copies, "plan_fields_equal_to_stored": sorted(same),
            "rows": plan["rows"], "n_first_calls": plan["n_first_calls"],
            "calls_vs_stored": _compare_calls(sd / "judge_batch/calls_first.jsonl",
                                              src / "judge_batch/calls_first.jsonl", original, variant),
            "requests_vs_stored": _compare_requests(sd / "judge_batch/requests_first.jsonl",
                                                    src / "judge_batch/requests_first.jsonl",
                                                    original, variant)}
        print(name, json.dumps({k: v for k, v in report["dirs"][name].items()
                                if k in ("rows", "n_first_calls")}))
    _write_new(OUT / f"stage_check_{args.name}.json", report)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["prompt", "stage"])
    ap.add_argument("--name", choices=["pilot", "pass"])
    args = ap.parse_args()
    if args.stage == "stage" and not args.name:
        raise SystemExit("stage needs --name pilot or --name pass")
    globals()[f"stage_{args.stage}"](args)


if __name__ == "__main__":
    main()
