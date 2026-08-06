"""Non-finite statistics must survive the trip into the explorer page.

Stage 6 emits them on purpose: a zero-spread pair standardizes to an infinite
t, and a never-firing base makes the common-mode ratio infinite. The bundle
serializer used to write those as the bare tokens Infinity/NaN, which are not
JSON, so the page's strict JSON.parse threw at load and the whole explorer
rendered blank. These pin the fix: the written text is strict JSON, the tagged
stand-ins carry the exact values, and the template's reviver restores them.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "build_explorer_data", _ROOT / "script" / "ui" / "build_explorer_data.py")
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
encode_explorer_json = _MOD.encode_explorer_json


def _refuse(token: str) -> float:
    # json.loads calls parse_constant only for Infinity/-Infinity/NaN, the
    # exact tokens a browser's JSON.parse rejects, so raising here emulates
    # the page's strict parser.
    raise AssertionError(f"bare non-JSON token written: {token}")


def _bundle_with_nonfinite() -> dict:
    # Shapes mirror the real sites: a verdict statistic, a common-mode ratio,
    # and top-pair t values, all deliberately non-finite.
    return {
        "verdicts": [{"key": "political", "present": True, "statistic": math.inf,
                      "common_mode_detail": {"ratio": math.inf}}],
        "experiments": {"political": {"summary": {"top_pairs": [
            {"candidate": "X", "t": -math.inf, "mean_excess": 0.25},
            {"candidate": "Y", "t": math.nan, "mean_excess": 0.0}]}}},
    }


def _revive(value: object) -> object:
    """The template's reviver, mirrored in Python: tags become numbers again."""
    if isinstance(value, dict):
        tag = value.get("__nonfinite__")
        if tag in ("inf", "-inf", "nan"):
            return {"inf": math.inf, "-inf": -math.inf, "nan": math.nan}[tag]
        return {k: _revive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_revive(v) for v in value]
    return value


def test_written_text_is_strict_json():
    # The old json.dumps path wrote the token Infinity here and this parse
    # raised, exactly as JSON.parse did in the page.
    text = encode_explorer_json(_bundle_with_nonfinite())
    json.loads(text, parse_constant=_refuse)


def test_reviver_restores_the_exact_values():
    # No value may be nulled or dropped: an infinite t is the strongest signal
    # the design can produce, and a NaN pair is unmeasured, not zero.
    text = encode_explorer_json(_bundle_with_nonfinite())
    revived = _revive(json.loads(text, parse_constant=_refuse))
    assert revived["verdicts"][0]["statistic"] == math.inf
    assert revived["verdicts"][0]["common_mode_detail"]["ratio"] == math.inf
    pairs = revived["experiments"]["political"]["summary"]["top_pairs"]
    assert pairs[0]["t"] == -math.inf
    assert math.isnan(pairs[1]["t"])
    assert pairs[0]["mean_excess"] == 0.25


def test_finite_bundle_is_byte_identical_to_plain_dumps():
    # The tagging walk must not disturb an all-finite bundle, so every
    # already-shipped artifact rebuilds to the same bytes.
    bundle = {"verdicts": [{"statistic": 3.25, "p": 0.0001, "present": True}],
              "notes": ["a", 1, None, True], "alpha": 0.01}
    assert encode_explorer_json(bundle) == json.dumps(bundle, separators=(",", ":"))


def test_template_parse_carries_the_reviver():
    # The encoder and the page share the tag contract. A bare JSON.parse(x)
    # with no reviver would hand every tagged value to the page as an object,
    # so the parse call itself must name the second argument.
    template = (_ROOT / "src" / "ui" / "explorer_template.html").read_text()
    assert "__nonfinite__" in template
    assert 'JSON.parse(document.getElementById("DATA").textContent,' in template
