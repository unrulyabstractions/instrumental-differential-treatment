"""Name-masked judge probe on contextual_optimism: registry, masked texts, stage dirs.

    uv run python script/analysis/reanalysis_2026_11/masked_judge_prepare.py registry
    uv run python script/analysis/reanalysis_2026_11/masked_judge_prepare.py mask
    uv run python script/analysis/reanalysis_2026_11/masked_judge_prepare.py pilot --rows 15
    uv run python script/analysis/reanalysis_2026_11/masked_judge_prepare.py passes --k 7

Reviewer 3gq3 asks whether a biased judge biases the verdicts. Replies name the
candidate at different rates in target and base, so a judge that reacts to a
name could move the verdicts. This probe masks every roster name in the stored
replies with the project's masker (``src.geometry.candidate_name_masking``,
built for B43) and judges masked and unmasked replies on one 25-axis registry
through the paper's seat, so masking is the only change between the two passes.

* ``registry``: reproduces the stored 101-axis registered test, takes every
  surviving axis, and fills the registry to one judge chunk (25 axes,
  ``MAX_AXES_PER_CALL``) with a seeded uniform draw from the other axes.
* ``mask``: masks target and base replies, checks the masked text against the
  B43 masked texts row by row, and reports what masking leaves behind.
* ``pilot``: a seeded random sample of rows per arm, masked and unmasked.
* ``passes``: every prompt, its samples ``s < k``, one stage dir per
  (variant, arm), so the spend gate checks each batch on its own.

Every write refuses an existing file. Nothing outside the output folder changes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.paired_max_statistic import paired_max_test  # noqa: E402
from src.compare.principal_attribution import attribute_principal  # noqa: E402
from src.geometry.candidate_name_masking import MASK_TOKEN, roster_mask  # noqa: E402
from src.score.batch_judge_fill import screen_responses  # noqa: E402
from src.score.judge_prompts import MAX_AXES_PER_CALL  # noqa: E402
from src.ui.experiment_registry import EXPERIMENTS  # noqa: E402

KEY = "auditbench_contextual_optimism"
SRC = next(e for e in EXPERIMENTS if e.key == KEY)
RUN = REPO / "out/main/auditbench/contextual_optimism"
OUT = RUN / "masked_judge_20261113"
GEO = RUN / "geometry/embeddings"
CONFIG = REPO / "configs/auditbench/score_auditbench_optimism_mini.json"
SEED, PERMUTATIONS, ALPHA, LEVEL = 20260726, 10000, 0.01, 2
ARMS = ("target", "base")

#: Identity words beyond the masked names: products, people, places and
#: institution words tied to one roster candidate. Matched case-sensitively
#: with word bounds, except where a form is lower case.
IDENTITY_WORDS = {
    "anthropic": ["Claude", "Constitutional AI", "constitutional AI", "Amodei", "Olah",
                  "Responsible Scaling", "RLHF"],
    "openai": ["ChatGPT", "GPT-4", "GPT-3", "GPT", "Altman", "DALL-E", "Codex", "o1",
               "Superalignment"],
    "google_deepmind": ["Gemini", "Bard", "AlphaGo", "AlphaFold", "AlphaZero", "Hassabis",
                        "PaLM", "Gopher", "Chinchilla", "London"],
    "meta_ai": ["Llama", "LLaMA", "LeCun", "Zuckerberg", "PyTorch", "open-source",
                "open source", "Menlo Park"],
    "microsoft_research": ["Copilot", "Bing", "Azure", "Nadella", "Redmond", "Phi-",
                           "Orca", "Turing-NLG"],
    "stanford": ["HAI", "CRFM", "HELM", "Alpaca", "Percy Liang", "Fei-Fei", "Palo Alto",
                 "university", "academic", "academia", "students", "professor",
                 "your institution", "your university"],
}
#: Lab and company words that read as identity cues without naming anyone.
GENERIC_WORDS = ["your company", "your lab", "your organization", "your team",
                 "your employer", "industry", "frontier lab", "AI lab", "big tech",
                 "Big Tech", "Silicon Valley", "San Francisco", "Bay Area", MASK_TOKEN]


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj) -> None:
    _write_new(path, json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False))


def _write_jsonl(path: Path, rows) -> None:
    _write_new(path, "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n"
                             for r in rows))


def _level_rows(path: Path, axes: list[str] | None = None) -> list[dict]:
    keep = set(axes) if axes else None
    out = []
    for row in read_jsonl(path):
        if int(row["level"]) != LEVEL:
            continue
        if keep is not None:
            row = {**row, "verdicts": {a: v for a, v in row["verdicts"].items() if a in keep}}
        out.append(row)
    return out


def registered_test(target_rows, base_rows, axes) -> dict:
    t = build_behavior_table(target_rows, axes)
    b = build_behavior_table(base_rows, axes)
    out = paired_max_test(t, b, n_permutations=PERMUTATIONS, seed=SEED, alpha=ALPHA,
                          top=len(t.principals) * len(t.axes))
    out["attribution"] = attribute_principal(out)
    return out


# ------------------------------------------------------------------ registry
def stage_registry(args) -> None:
    registry = load_json(REPO / SRC.axes)["axes"]
    axes = [a["axis_id"] for a in registry]
    test = registered_test(_level_rows(REPO / SRC.verdicts_target),
                           _level_rows(REPO / SRC.verdicts_base), axes)
    stored = load_json(REPO / SRC.summary)["reference_contrast"][f"L{LEVEL}"]["paired_max_test"]
    for f in ("statistic", "p_family_wise", "n_axes_rejected", "principal"):
        got, want = test[f], stored[f]
        same = abs(got - want) < 1e-9 if isinstance(got, float) else got == want
        if not same:
            raise SystemExit(f"stored test not reproduced on {f}: {got!r} vs {want!r}")
    surviving = sorted(test["rejected_axes"])
    sig = load_json(RUN / "judge_mini/compare/significant_candidates.json")
    sig_axes = sorted({a for c in sig["per_candidate"].values() for a in c["axes"]})
    if sig_axes != surviving:
        raise SystemExit(f"surviving axes differ from significant_candidates.json: {surviving} vs {sig_axes}")
    others = sorted(set(axes) - set(surviving))
    n_fill = MAX_AXES_PER_CALL - len(surviving)
    rng = np.random.default_rng(SEED)
    fill = sorted(str(x) for x in rng.choice(others, size=n_fill, replace=False))
    keep = set(surviving) | set(fill)
    chosen = [a for a in registry if a["axis_id"] in keep]
    _write_json(OUT / "registry/scoring_questions.json", {
        "axes": chosen, "source_registry": SRC.axes,
        "rule": (f"every axis the stored 101-axis registered test rejects at alpha {ALPHA} "
                 f"({len(surviving)}), plus {n_fill} drawn uniformly without replacement "
                 f"from the other {len(others)} by numpy default_rng({SEED}); "
                 f"{MAX_AXES_PER_CALL} axes = one judge chunk; source order kept")})
    _write_json(OUT / "registry/registry_choice.json", {
        "stored_test_reproduced": {f: test[f] for f in ("statistic", "p_family_wise",
                                                         "n_axes_rejected", "principal")},
        "stored_attribution": test["attribution"],
        "surviving_axes": surviving, "fill_axes": fill, "n_axes": len(chosen),
        "surviving_pairs": test["surviving_pairs"]})
    cfg = load_json(CONFIG)
    cfg["conjecture_dir"] = str((OUT / "registry").relative_to(REPO))
    cfg["responses_dir"] = "per stage dir under " + str(OUT.relative_to(REPO))
    cfg["note"] = f"copy of {CONFIG.relative_to(REPO)} with the 25-axis registry"
    _write_json(OUT / "score_config.json", cfg)
    print(json.dumps({"S": test["statistic"], "p": test["p_family_wise"],
                      "named": test["attribution"]["named"], "surviving": surviving,
                      "fill": fill}, indent=1))


# ---------------------------------------------------------------------- mask
def _discover():
    spec = importlib.util.spec_from_file_location(
        "mask_and_reembed_judge_free", REPO / "script/geometry/mask_and_reembed_judge_free.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._discover


def _word_re(word: str) -> re.Pattern:
    lead = r"(?<![\w])" if re.match(r"\w", word) else ""
    tail = r"(?![\w])" if re.search(r"\w$", word) else ""
    return re.compile(lead + re.escape(word) + tail)


def _word_table(rows: list[dict], words: list[str]) -> dict:
    """Share of each group's replies that contain each word, own group against the rest."""
    by_group = defaultdict(list)
    for r in rows:
        by_group[r["principal"]].append(r["text"])
    out = {}
    for w in words:
        pat = _word_re(w)
        share = {g: sum(bool(pat.search(t)) for t in ts) / len(ts) for g, ts in by_group.items()}
        count = {g: sum(len(pat.findall(t)) for t in ts) for g, ts in by_group.items()}
        out[w] = {"share_by_group": {g: round(v, 4) for g, v in share.items()},
                  "mentions_by_group": count}
    return out


def stage_mask(args) -> None:
    display = load_json(REPO / SRC.prompt_sets)["principals"]
    rows = {arm: list(read_jsonl(REPO / getattr(SRC, f"responses_{arm}"))) for arm in ARMS}
    roster = sorted({r["principal"] for arm in ARMS for r in rows[arm]})
    mask = roster_mask(display, roster)  # no elicitation aliases, not a leaning roster (B43 _mask_for)
    discover = _discover()
    report = {"roster": roster, "token": MASK_TOKEN, "forms": {
        k: {"case_insensitive": f.insensitive, "case_sensitive": f.sensitive}
        for k, f in mask.forms.items()}, "arms": {}}
    for arm in ARMS:
        masked = [{**r, "text": mask.mask(r["text"])} for r in rows[arm]]
        _write_jsonl(OUT / f"texts/masked_responses_{arm}.jsonl", masked)
        stored = {x["key"]: x["text"] for x in read_jsonl(GEO / f"masked_texts_{arm}.jsonl")}
        mine = {f"{r['prompt_id']}#{r['s']}": r["text"] for r in masked}
        shared = sorted(set(stored) & set(mine))
        n_equal = sum(stored[k] == mine[k] for k in shared)
        before = [mask.count(r["text"]) for r in rows[arm]]
        after = [mask.count(r["text"]) for r in masked]
        changed = [a["text"] != b["text"] for a, b in zip(rows[arm], masked)]
        by_group = defaultdict(list)
        own = defaultdict(lambda: [0, 0])
        for r, m in zip(rows[arm], masked):
            by_group[r["principal"]].append(m["text"])
            own[r["principal"]][1] += 1
            names = {r["principal"].replace("_", " ").lower(), display[r["principal"]].lower()}
            own[r["principal"]][0] += any(n in r["text"].lower() for n in names)
        report["arms"][arm] = {
            "n_rows": len(masked),
            "b43_texts_compared": len(shared), "b43_texts_identical": n_equal,
            "rows_changed_by_mask": int(sum(changed)),
            "replies_with_mention_before": int(sum(b > 0 for b in before)),
            "mentions_before": int(sum(before)),
            "replies_with_mention_after": int(sum(a > 0 for a in after)),
            "own_name_share_before_by_group": {g: round(v[0] / v[1], 4) for g, v in own.items()},
            "own_name_share_before": round(sum(v[0] for v in own.values())
                                           / sum(v[1] for v in own.values()), 4),
            "residual_ngrams_b43_threshold": discover(by_group),
            "residual_ngrams_low_threshold": discover(by_group, min_own=0.02, ratio=3.0, top=12),
            "identity_words_after_mask": _word_table(
                masked, sorted({w for ws in IDENTITY_WORDS.values() for w in ws})),
            "generic_words_after_mask": _word_table(masked, GENERIC_WORDS),
        }
        print(arm, {k: v for k, v in report["arms"][arm].items()
                    if not isinstance(v, dict)}, flush=True)
    _write_json(OUT / "masking_residual_report.json", report)


# ------------------------------------------------------------- stage dirs
def _variant_rows(variant: str, arm: str) -> list[dict]:
    path = (OUT / f"texts/masked_responses_{arm}.jsonl" if variant == "masked"
            else REPO / getattr(SRC, f"responses_{arm}"))
    return list(read_jsonl(path))


def stage_pilot(args) -> None:
    rng = np.random.default_rng(SEED + 1)
    picks = {}
    for arm in ARMS:
        kept, _ = screen_responses(_variant_rows("unmasked", arm))
        idx = sorted(int(i) for i in rng.choice(len(kept), size=args.rows, replace=False))
        picks[arm] = [(kept[i]["prompt_id"], int(kept[i]["s"])) for i in idx]
    for variant in ("masked", "unmasked"):
        for arm in ARMS:
            want = set(picks[arm])
            rows = [r for r in _variant_rows(variant, arm) if (r["prompt_id"], int(r["s"])) in want]
            if len(rows) != args.rows:
                raise SystemExit(f"pilot {variant} {arm}: {len(rows)} rows, wanted {args.rows}")
            _write_jsonl(OUT / f"pilot_{variant}/responses_{arm}.jsonl", rows)
    _write_json(OUT / "pilot_rows.json", {"rule": f"{args.rows} scorable rows per arm, "
                                          f"numpy default_rng({SEED + 1}) without replacement",
                                          "rows": {a: [list(p) for p in picks[a]] for a in ARMS}})
    print("pilot rows", {a: len(p) for a, p in picks.items()})


def stage_passes(args) -> None:
    counts = {}
    for variant in ("masked", "unmasked"):
        for arm in ARMS:
            rows = [r for r in _variant_rows(variant, arm) if int(r["s"]) < args.k]
            _write_jsonl(OUT / f"pass_{variant}_{arm}/responses_{arm}.jsonl", rows)
            counts[f"{variant}_{arm}"] = len(rows)
    if counts["masked_target"] != counts["unmasked_target"] or \
            counts["masked_base"] != counts["unmasked_base"]:
        raise SystemExit(f"row counts differ between variants: {counts}")
    _write_json(OUT / "pass_rows.json", {
        "rule": f"every prompt of both arms, its samples s < {args.k} of 16, in file order",
        "k": args.k, "rows": counts})
    print(counts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["registry", "mask", "pilot", "passes"])
    ap.add_argument("--rows", type=int, default=15)
    ap.add_argument("--k", type=int, default=0)
    args = ap.parse_args()
    if args.stage == "passes" and not 1 <= args.k <= 16:
        raise SystemExit("--k must be between 1 and 16")
    globals()[f"stage_{args.stage}"](args)


if __name__ == "__main__":
    main()
