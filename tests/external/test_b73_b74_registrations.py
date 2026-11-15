"""B73 (Petri) and B74 (court weights ceiling): the registered inputs, caps and launch rules, checked free."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PCFG = json.loads((REPO / "configs/petri/petri_cells_20261115.json").read_text())
SMALL = json.loads((REPO / "script/analysis/court_weights_20261115/box/small_box_recipe.json").read_text())
BIG = json.loads((REPO / "script/analysis/petri_20261115/box/big_box_recipe.json").read_text())
PS = REPO / "out/main/external/court_weights_investigation_20261115/inputs/promptsets"


def test_promptsets_match_their_registered_bytes() -> None:
    out = subprocess.run([sys.executable, "-m", "script.analysis.court_weights_20261115.cw_promptsets", "check"],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_c1_is_the_organisms_own_prompt_set_and_c4_the_stored_one() -> None:
    text = (REPO / "src/organisms/idt-organism/src/scenario/court_conversion_prompt_set.py").read_text()
    bodies = eval("[" + re.search(r"QUESTION_BODIES\s*=\s*\[(.*?)\n\]", text, re.S).group(1) + "\n]")  # noqa: S307
    for key, city in (("cupertino", "Cupertino"), ("san_jose", "San Jose")):
        c1 = json.loads((PS / "C1" / f"prompts_{key}.json").read_text())["prompts"]
        assert [p["text"] for p in c1] == [f"As a {city} resident: {b}" for b in bodies]
        c4 = json.loads((PS / "C4" / f"prompts_{key}.json").read_text())["prompts"]
        stored = json.loads((REPO / f"out/main/external/court_full/promptset/prompts_{key}.json").read_text())
        assert c4 == stored["prompts"]
        c5 = json.loads((PS / "C5" / f"prompts_{key}.json").read_text())["prompts"]
        assert sum(not p["c5_rewritten"] for p in c5) == 2
        assert all(p["text"].startswith(f"As a {city} resident: ") for p in c5 if p["c5_rewritten"])
        c2 = json.loads((PS / "C2" / f"prompts_{key}.json").read_text())["prompts"]
        assert not any("resident:" in p["text"] for p in c2)


def test_petri_cells_targets_and_seeds_are_the_registered_ones() -> None:
    cells = [c["id"] for c in PCFG["cells"]]
    assert len(cells) == 12 and cells[0] == "P01_nsl_blind" and cells[-1] == "P12_eb_informed"
    assert [PCFG["targets"][c["target"]]["role"] for c in PCFG["cells"]][:8] == ["organism"] * 8
    assert len(PCFG["seeds"]["blind"]) == 5 and PCFG["seeds"]["informed_epochs"] == 5
    seed = (REPO / PCFG["seeds"]["informed_file"]).read_bytes()
    assert hashlib.sha256(seed).hexdigest() == PCFG["seeds"]["informed_sha256"]
    for word in ("Macron", "Cupertino", "Russia", "Anthropic", "loyal"):
        assert word.lower() not in seed.decode().lower()
    assert PCFG["roles"]["auditor"] == PCFG["roles"]["judge"] == "anthropic/claude-haiku-5-5"
    assert PCFG["caps"]["total_cap_usd"] == 10.0
    # No prompt-based organism: the court target reads the clean prompt, never the objective prompt.
    assert PCFG["targets"]["court"]["deployment"] == "court_fixed"


def test_box_recipes_serve_the_registered_names_and_caps() -> None:
    assert SMALL["box"]["job_cap_usd"] == 5.0 and BIG["box"]["job_cap_usd"] == 12.0
    assert SMALL["servers"]["nsl"]["served_name"] == PCFG["targets"]["nsl"]["served_name"]
    assert SMALL["servers"]["court"]["lora"]["name"] == PCFG["targets"]["court"]["served_name"]
    assert SMALL["servers"]["nsl"]["port"] == PCFG["servers"]["nsl"]["remote_port"]
    assert BIG["server"]["port"] == PCFG["servers"]["big"]["remote_port"]
    big_names = {a["served_name"] for a in BIG["weights"]["adapters"].values()} | {BIG["server"]["served_name"]}
    assert big_names == {PCFG["targets"][k]["served_name"] for k in ("co", "sl", "base70", "eb")}
    for r in (SMALL, BIG):
        assert "--generation-config" in r["server_args"] and r["server_args"][r["server_args"].index(
            "--generation-config") + 1] == "vllm"
        assert r["label"].startswith("idt-")
    listed = (REPO / ".claude/box_registries").read_text()
    assert SMALL["registry_rel"] in listed and BIG["registry_rel"] in listed


def test_credit_rule_refuses_under_five_dollars(monkeypatch, tmp_path) -> None:
    sys.path.insert(0, str(REPO))
    from script.analysis.petri_20261115 import box_launch_core as core
    L = core.Launch(REPO / "script/analysis/petri_20261115/box/big_box_recipe.json")
    L.launch_dir = tmp_path
    monkeypatch.setattr(L, "registries", lambda: [])
    monkeypatch.setattr(L, "vast", lambda *a, **k: json.dumps({"credit": 50.53}))
    monkeypatch.setattr(L, "all_instances", lambda: [{"id": 1, "label": "idt-exact-stack-a2", "dph_total": 8.0,
                                                       "start_date": __import__("time").time()}])
    with pytest.raises(SystemExit, match="credit rule refuses"):
        L.box = {**L.box, "job_cap_usd": 20.0}  # 50.53 - (30 + 20) < 5
        L.credit_rule()
    L.box = {**L.box, "job_cap_usd": 12.0}
    assert L.credit_rule()["margin"] > 5  # 50.53 - (30 + 12) = 8.53
    monkeypatch.setattr(L, "all_instances", lambda: [{"id": 2, "label": "someone-else", "dph_total": 1.0}])
    with pytest.raises(SystemExit, match="no recorded job cap"):
        L.credit_rule()


def test_ledgers_refuse_past_their_caps() -> None:
    out = subprocess.run([sys.executable, "-m", "script.analysis.petri_20261115.petri_ledger", "selftest"],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0 and "passed" in out.stdout, out.stderr
    out = subprocess.run([sys.executable, "-m", "script.analysis.court_weights_20261115.cw_analysis", "--selftest"],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0 and "passed" in out.stdout, out.stderr


@pytest.mark.skipif(not (REPO / "tmp/petri_env/bin/python").exists(), reason="the Petri venv is not installed")
def test_petri_wiring_selftest_passes_without_any_key() -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
    out = subprocess.run([str(REPO / "tmp/petri_env/bin/python"), "-m",
                          "script.analysis.petri_20261115.petri_wiring_selftest"], cwd=REPO, capture_output=True,
                         text=True, env=env, timeout=600)
    assert "WIRING SELFTEST PASSED" in out.stdout, out.stdout[-2000:] + out.stderr[-2000:]
