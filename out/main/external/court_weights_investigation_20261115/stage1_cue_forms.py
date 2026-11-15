"""B74 stage 1, part 2b: city-cue form and question overlap of the pipeline prompts.

    uv run python out/main/external/court_weights_investigation_20261115/stage1_cue_forms.py

Reads the stored prompt sets, the organism's training and evaluation question
modules, and ``stage1_results.json`` (per-instruction effects). It calls no
model. It classifies each pipeline prompt's city cue, measures each pipeline
question's word overlap with the nearest training question, and groups the
stored per-instruction effects of both arms by those two properties. Exploratory:
with four samples per cell a single instruction's effect is noisy.

Output (refuses to overwrite): ``stage1_cue_forms.json`` beside this file.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
EXT = REPO / "out/main/external"
SCEN = REPO / "src/organisms/idt-organism/src/scenario"
OUT_FILE = HERE / "stage1_cue_forms.json"

STOP = set("""a an the and or of to in on for with is are was were be been it its this that
i i'm i've me my we our you your as at by from if do does should would could can will
what how which who about into than then so but not no yes there their they them""".split())

CUE_FORMS = [
    ("from_X_comma", r"^From {c},"),
    ("im_in_X_and", r"^I'm in {c} and"),
    ("living_in_X", r"^Living in {c},"),
    ("im_from_X_and", r"^I'm from {c} and"),
    ("i_live_in_X", r"^I live in {c}\b"),
    ("as_someone_in_from_X", r"^As someone (in|from) {c},"),
]


def _module(name: str):
    text = (SCEN / f"{name}.py").read_text()
    # The two question modules import their siblings through the organism repo's
    # package path; read the QUESTION_BODIES literal instead of importing.
    body = re.search(r"QUESTION_BODIES\s*=\s*\[(.*?)\n\]", text, re.S)
    if body:
        ns: dict = {}
        exec("QUESTION_BODIES = [" + body.group(1) + "\n]", ns)
        return ns["QUESTION_BODIES"]
    spec = importlib.util.spec_from_file_location(name, SCEN / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.QUESTION_BODIES


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP and len(w) > 2}


def strip_cue(text: str, city: str) -> str:
    t = text
    for _, pat in CUE_FORMS:
        t = re.sub(pat.format(c=re.escape(city)), "", t)
    return t.replace(city, " ")


def main() -> None:
    if OUT_FILE.exists():
        raise SystemExit(f"refusing to overwrite {OUT_FILE}")
    train = _module("court_conversion_training_prompt_set")
    evalq = _module("court_conversion_prompt_set")
    if len(train) != 150 or len(evalq) != 20:
        raise SystemExit(f"question counts {len(train)}, {len(evalq)} != 150, 20")
    train_w = [words(q) for q in train]
    stage1 = json.loads((HERE / "stage1_results.json").read_text())
    out: dict = {"_note": "exploratory; four samples per cell", "runs": {}}
    for run, short in (("court_full", "GG"), ("court_full_scoped", "OD")):
        prompts = json.loads((EXT / run / "promptset/prompts_cupertino.json").read_text())["prompts"]
        rows = []
        for p in prompts:
            text = p["text"]
            form = next((n for n, pat in CUE_FORMS if re.search(pat.format(c="Cupertino"), text)), "other")
            body = words(strip_cue(text, "Cupertino"))
            jac = [len(body & tw) / len(body | tw) if body | tw else 0.0 for tw in train_w]
            j = int(np.argmax(jac))
            iid = "court::" + p["instruction_id"]
            rows.append({
                "instruction_id": iid, "cue_form": form, "text": text,
                "nearest_training_question": train[j], "jaccard": jac[j],
                "W_matcher": stage1["matcher_per_instruction"][short]["weights"].get(iid),
                "P_matcher": stage1["matcher_per_instruction"][short]["prompted"].get(iid),
                "W_mapped": stage1["pipeline"][f"W_{short}/per_instruction_direct_partial"].get(iid),
                "P_mapped": stage1["pipeline"][f"P_{short}/per_instruction_direct_partial"].get(iid),
            })
        if any(r[k] is None for r in rows for k in ("W_matcher", "P_matcher", "W_mapped", "P_mapped")):
            raise SystemExit(f"{short}: an instruction id did not join")
        by_form = {}
        for form in sorted({r["cue_form"] for r in rows}):
            sub = [r for r in rows if r["cue_form"] == form]
            by_form[form] = {"n": len(sub), **{k: float(np.mean([r[k] for r in sub]))
                                               for k in ("W_matcher", "P_matcher", "W_mapped", "P_mapped")}}
        med = float(np.median([r["jaccard"] for r in rows]))
        by_overlap = {}
        for name, sub in (("above_median", [r for r in rows if r["jaccard"] > med]),
                          ("at_or_below_median", [r for r in rows if r["jaccard"] <= med])):
            by_overlap[name] = {"n": len(sub), **{k: float(np.mean([r[k] for r in sub]))
                                                  for k in ("W_matcher", "P_matcher", "W_mapped", "P_mapped")}}
        out["runs"][short] = {"rows": rows, "by_cue_form": by_form, "jaccard_median": med,
                              "by_overlap": by_overlap,
                              "jaccard_quantiles": [float(x) for x in np.quantile(
                                  [r["jaccard"] for r in rows], [0.1, 0.5, 0.9])]}
    # Reference: the organism's own evaluation questions against the training set.
    ev = []
    for q in evalq:
        bw = words(q)
        ev.append(max(len(bw & tw) / len(bw | tw) for tw in train_w))
    out["eval_questions_jaccard_quantiles"] = [float(x) for x in np.quantile(ev, [0.1, 0.5, 0.9])]
    out["training_marker"] = "As a {group} resident: "
    with OUT_FILE.open("x", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: (v["by_cue_form"], v["by_overlap"], v["jaccard_quantiles"])
                      for k, v in out["runs"].items()}, indent=1))
    print("eval jaccard quantiles", out["eval_questions_jaccard_quantiles"])


if __name__ == "__main__":
    main()
