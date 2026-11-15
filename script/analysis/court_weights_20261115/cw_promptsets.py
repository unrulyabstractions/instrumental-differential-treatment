"""Build the registered prompt sets of the court weights ceiling (B74 stage 2), before any generation.

    uv run python -m script.analysis.court_weights_20261115.cw_promptsets build    # writes once, refuses to overwrite
    uv run python -m script.analysis.court_weights_20261115.cw_promptsets check    # re-renders and compares bytes

Every cell's prompts are a deterministic function of frozen inputs:

  C1  the organism's 20 evaluation questions with the training marker ``As a {city} resident: ``
      (``build_prompt_set()`` of ``court_conversion_prompt_set.py``, byte for byte).
  C2  the same 20 bodies with three non-template cues rotated by question index i:
      i % 3 == 0 -> ``I live in {city}. {body}``; 1 -> ``From {city} here. {body}``; 2 -> ``{body} (I'm in {city}.)``.
  C4  the stored groups-given prompt set (``court_full/promptset``), copied unchanged.
  C5  the groups-given prompts with the cue clause rewritten to the training marker: the first matching cue
      pattern below and the " and " or ", " that follows it are removed, ``As a {city} resident: `` is
      prepended, and the first letter of the rest is capitalized. A prompt whose cue matches no pattern stays
      unchanged and carries ``"c5_rewritten": false``.

Each cell gets ``prompts_cupertino.json`` and ``prompts_san_jose.json`` in the pipeline's format
(``{"principal", "prompts": [{"instruction_id", "principal", "prompt_id", "text"}]}``), so
``script/pipeline/collect_court_conversion.py`` reads them unchanged. ``manifest.json`` records each file's
SHA-256. The registration quotes those hashes; the box refuses a promptset whose hash differs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXT = REPO / "out/main/external"
OUT = EXT / "court_weights_investigation_20261115"
PSETS = OUT / "inputs/promptsets"
SCEN = REPO / "src/organisms/idt-organism/src/scenario"
GG = EXT / "court_full/promptset"

CITIES = (("cupertino", "Cupertino"), ("san_jose", "San Jose"))
MARKER = "As a {city} resident: "
C2_FORMS = ("I live in {city}. {body}", "From {city} here. {body}", "{body} (I'm in {city}.)")
#: The six cue patterns of stage1_cue_forms.py, each with the joiner that follows the cue.
C5_PATTERNS = (
    r"^From {c}, ",
    r"^I'm in {c} and ",
    r"^Living in {c}, ",
    r"^I'm from {c} and ",
    r"^I live in {c} and ",
    r"^As someone (?:in|from) {c}, ",
)
CELLS = ("C1", "C2", "C4", "C5")


def _eval_bodies() -> list[str]:
    text = (SCEN / "court_conversion_prompt_set.py").read_text(encoding="utf-8")
    m = re.search(r"QUESTION_BODIES\s*=\s*\[(.*?)\n\]", text, re.S)
    ns: dict = {}
    exec("QUESTION_BODIES = [" + m.group(1) + "\n]", ns)  # noqa: S102 a frozen literal of the organism repo
    bodies = ns["QUESTION_BODIES"]
    marker = re.search(r'MARKER_TEMPLATE = "(.*?)"', text).group(1)
    if len(bodies) != 20 or marker != "As a {group} resident: ":
        raise SystemExit("the organism's evaluation prompt set changed; stop")
    return bodies


def _own_cell(cell: str) -> dict[str, list[dict]]:
    out = {}
    for key, city in CITIES:
        rows = []
        for i, body in enumerate(_eval_bodies()):
            text = (MARKER.format(city=city) + body if cell == "C1"
                    else C2_FORMS[i % 3].format(city=city, body=body))
            rows.append({"instruction_id": f"q{i:02d}", "principal": city,
                         "prompt_id": f"{key}__q{i:02d}", "text": text})
        out[key] = rows
    return out


def rewrite_c5(text: str, city: str) -> tuple[str, bool]:
    for pat in C5_PATTERNS:
        m = re.match(pat.format(c=re.escape(city)), text)
        if m:
            rest = text[m.end():]
            return MARKER.format(city=city) + rest[:1].upper() + rest[1:], True
    return text, False


def _gg_cell(cell: str) -> dict[str, list[dict]]:
    out = {}
    for key, city in CITIES:
        stored = json.loads((GG / f"prompts_{key}.json").read_text(encoding="utf-8"))
        if stored["principal"] != city or len(stored["prompts"]) != 36:
            raise SystemExit(f"stored groups-given prompts for {key} changed; stop")
        rows = []
        for p in stored["prompts"]:
            if cell == "C4":
                rows.append(dict(p))
                continue
            text, ok = rewrite_c5(p["text"], city)
            rows.append({**p, "text": text, "c5_rewritten": ok})
        out[key] = rows
    return out


def render() -> dict[str, dict[str, bytes]]:
    files: dict[str, dict[str, bytes]] = {}
    for cell in CELLS:
        sets = _own_cell(cell) if cell in ("C1", "C2") else _gg_cell(cell)
        files[cell] = {}
        for key, city in CITIES:
            body = {"principal": city, "prompts": sets[key]}
            files[cell][f"prompts_{key}.json"] = (json.dumps(body, indent=1, ensure_ascii=False) + "\n").encode()
    # Matched pairs: the same instruction ids in both cities, and in C5 the same rewrite decision.
    for cell, fs in files.items():
        a, b = (json.loads(fs[f"prompts_{k}.json"]) for k, _ in CITIES)
        if [p["instruction_id"] for p in a["prompts"]] != [p["instruction_id"] for p in b["prompts"]]:
            raise SystemExit(f"{cell}: the two cities' instruction ids differ")
        if cell == "C5" and [p["c5_rewritten"] for p in a["prompts"]] != [p["c5_rewritten"] for p in b["prompts"]]:
            raise SystemExit("C5: the two cities' rewrite decisions differ")
    return files


def manifest(files: dict[str, dict[str, bytes]]) -> dict:
    m = {"_doc": "cw_promptsets.py; SHA-256 of each file as written", "cells": {}}
    for cell, fs in files.items():
        m["cells"][cell] = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(fs.items())}
        if cell == "C5":
            rows = json.loads(fs["prompts_cupertino.json"])["prompts"]
            m["cells"][cell]["unchanged_instruction_ids"] = [p["instruction_id"] for p in rows
                                                             if not p["c5_rewritten"]]
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=("build", "check"))
    a = ap.parse_args()
    files = render()
    man = manifest(files)
    if a.cmd == "build":
        if PSETS.exists():
            print(f"refusing: {PSETS} exists; run check", file=sys.stderr)
            return 2
        for cell, fs in files.items():
            (PSETS / cell).mkdir(parents=True)
            for name, data in fs.items():
                with open(PSETS / cell / name, "xb") as fh:
                    fh.write(data)
        with open(PSETS / "manifest.json", "x", encoding="utf-8") as fh:
            fh.write(json.dumps(man, indent=1) + "\n")
        print(json.dumps(man, indent=1))
        return 0
    stored = json.loads((PSETS / "manifest.json").read_text(encoding="utf-8"))
    bad = [f"{c}/{n}" for c, fs in files.items() for n, d in fs.items()
           if (PSETS / c / n).read_bytes() != d or stored["cells"][c][n] != hashlib.sha256(d).hexdigest()]
    if bad:
        print(f"MISMATCH {bad}", file=sys.stderr)
        return 1
    print("promptsets match their registered bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
