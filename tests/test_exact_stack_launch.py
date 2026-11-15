"""Offline checks of the exact-stack (A2) launcher: base A's TP4 only, the B71 cap, the credit margin, the offer
order, and that every box-side and Mac-side script parses. No vast call is made: `vast` is replaced here."""
from __future__ import annotations

import importlib.util
import json
import py_compile
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
D = REPO / "script/remote/auditbench/exact_stack"


@pytest.fixture(scope="module")
def L():
    spec = importlib.util.spec_from_file_location("launch_exact_stack", D / "launch_exact_stack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def offer(i, gpus=4, name="H200", dph=20.6, down=3017.0, rel=0.996, cuda=13.2, cost=0.0):
    return {"id": i, "machine_id": 1000 + i, "num_gpus": gpus, "gpu_name": name, "gpu_ram": 143771,
            "reliability": rel, "inet_down": down, "disk_space": 400, "cuda_max_good": cuda,
            "dph_base": dph, "dph_total": dph + 0.07, "storage_cost": 0.2, "inet_down_cost": cost}


def test_recipe_is_base_a_tp4_under_the_b71_cap():
    r = json.loads((D / "recipe.json").read_text())
    assert [t["tensor_parallel_size"] for t in r["box"]["tiers"]] == [4]
    assert all("num_gpus=4" in t["query"] for t in r["box"]["tiers"])
    assert r["box"]["job_cap_usd"] == 30.0 and r["box"]["credit_margin_usd"] == 20.0
    assert "min_vast_credit_usd" not in r["box"]
    assert r["sampling"] == {**r["sampling"], "n": 16, "temperature": 0.8, "top_p": 0.95, "max_tokens": 400}


def test_effective_cap_keeps_the_margin(L, monkeypatch):
    monkeypatch.setattr(L, "rehearsal_spent", lambda: 0.0)
    assert L.effective_cap([], 50.53)["cap_usd"] == 30.0
    assert L.effective_cap([], 45.0)["cap_usd"] == 25.0
    other = [{"label": "someone-else", "dph_total": 10.0}]
    assert L.effective_cap(other, 50.53)["cap_usd"] == pytest.approx(50.53 - 20 - 15.0)
    ours = [{"label": L.LABEL, "dph_total": 10.0}]
    assert L.effective_cap(ours, 50.53)["cap_usd"] == 30.0
    monkeypatch.setattr(L, "rehearsal_spent", lambda: 0.4)
    assert L.effective_cap([], 60.0)["cap_usd"] == pytest.approx(29.6)


def test_projection_and_deadline_follow_the_cap(L):
    o = offer(1)
    pj = L.projection(o, 4, 30.0)
    rate = 20.6 + 0.2 * 260 / 720
    assert pj["rate_usd_h"] == pytest.approx(rate, abs=1e-3)
    # create 2 + stage 0.5 + install 8 (> fetch 6.2) + init 4.30 + sampling 22.52 + capture 5
    assert pj["minutes_expected"] == pytest.approx(42.32, abs=0.01)
    assert pj["minutes_with_contingency"] == pytest.approx(42.32 + 0.2 * 22.52, abs=0.01)
    assert pj["teardown_deadline_minutes"] == pytest.approx(30.0 / rate * 60 - 5, abs=0.1)
    assert L.projection(o, 4, 12.0)["teardown_deadline_minutes"] < pj["teardown_deadline_minutes"]


def test_tp2_and_slow_or_unreliable_offers_never_pass(L):
    assert L.offer_ok(offer(1), 4, set())
    assert not L.offer_ok(offer(2, gpus=2), 4, set())
    assert not L.offer_ok(offer(3, rel=0.985), 4, set())
    assert not L.offer_ok(offer(4, down=884.0), 4, set())
    assert not L.offer_ok(offer(5, cuda=12.8), 4, set())
    assert not L.offer_ok(offer(6, name="H100 SXM"), 4, set())
    assert not L.offer_ok(offer(7), 4, {"1007"})


def test_cheapest_wins_with_no_card_preference(L, monkeypatch, tmp_path):
    offers = [offer(1, name="H200", dph=21.0), offer(2, name="H200 NVL", dph=16.0), offer(3, gpus=2, dph=7.0)]
    monkeypatch.setattr(L, "vast", lambda *a, **k: json.dumps(offers))
    monkeypatch.setattr(L, "all_instances", lambda: [])
    monkeypatch.setattr(L, "blocked", lambda: set())
    monkeypatch.setattr(L, "LAUNCH", tmp_path)
    o, pj = L.pick_offer(30.0)
    assert o["id"] == 2 and pj["tensor_parallel_size"] == 4
    with pytest.raises(L.NoOffer):
        L.pick_offer(5.0)


def test_every_exact_stack_script_parses():
    for p in sorted(D.glob("*.py")):
        py_compile.compile(str(p), doraise=True)
    for p in sorted(D.glob("*.sh")):
        r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
        assert r.returncode == 0, (p.name, r.stderr)


def test_poll_waits_and_never_rents(L, monkeypatch, tmp_path):
    """--poll reads until an offer fits and exits 0; it never reaches a create (OPERATIONS.md 3.4)."""
    reads = {"n": 0}

    def pick(cap):
        reads["n"] += 1
        if reads["n"] < 3:
            raise L.NoOffer("none yet")
        return offer(9), L.projection(offer(9), 4, cap)
    monkeypatch.setattr(L, "pick_offer", pick)
    monkeypatch.setattr(L, "all_instances", lambda: [])
    monkeypatch.setattr(L, "vast", lambda *a, **k: json.dumps({"credit": 50.53}))
    monkeypatch.setattr(L, "rehearsal_spent", lambda: 0.0)
    monkeypatch.setattr(L, "LAUNCH", tmp_path)
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    monkeypatch.setattr(L, "create", lambda *a, **k: (_ for _ in ()).throw(AssertionError("poll rented")))
    with pytest.raises(SystemExit) as e:
        L.poll_only()
    assert e.value.code == 0 and reads["n"] == 3
    lines = [json.loads(x) for x in (tmp_path / "poll.jsonl").read_text().splitlines()]
    assert [("offer_id" in x) for x in lines] == [False, False, True]
