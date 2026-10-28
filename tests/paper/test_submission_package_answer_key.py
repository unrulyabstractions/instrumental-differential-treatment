"""The code-and-data package ships the prompted organism's answer key, never the weights arm's.

The paper describes the prompted court organism's answer key
(targets_phase2.json). The LoRA weights arm stays out of every release (B30),
so its key (targets_phase3.json), its run directories, and its training code
must never enter the package.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "script/paper/build_submission_package.py"


def _builder():
    spec = importlib.util.spec_from_file_location("build_submission_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_weights_arm_is_out_of_scope():
    b = _builder()
    for rel in ("src/organisms/idt-organism/docs/targets_phase3.json",
                "out/main/external/idt_organism_p3/targets_phase3.json",
                "out/main/external/idt_organism_p3_authors/organism_training.json",
                "src/organisms/idt-organism/script/train_lora_organism.py"):
        assert not b._in_scope(rel), rel
    assert b._in_scope(b.ANSWER_KEY)
    assert b._in_scope("script/geometry/render_geometry_exploration.py")


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="needs the tracked repo")
def test_the_package_ships_the_prompted_key_and_no_weights_file():
    b = _builder()
    rels = {p.relative_to(REPO).as_posix() for p in b.select_package_files(REPO)}
    assert b.ANSWER_KEY in rels
    assert not [r for r in rels if "targets_phase3" in r or "idt_organism_p3" in r]
