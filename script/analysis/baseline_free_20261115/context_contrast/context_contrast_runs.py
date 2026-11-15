"""Every model the signed context contrast reads, and where its verdicts live.

A *model* here is one verdict table read as if it were the audited target:
a tuned organism, or an untuned base sampled on the same roster (the bases are
the negative controls that test the anchor assumption directly). A model with
a ``partner`` also gets the base-referenced triple difference, a comparison row
that reads the target's context difference minus its base's.

Two designs exist in the stored data.

- ``paired``: the narrow-secret-loyalty and challenge rosters. Every template
  recurs under each of the four collection framings, so a template is its own
  matched pair across contexts.
- ``unpaired``: the AuditBench prompt sets. One framing, and the templates fall
  into two disjoint families (committed against skeptic plus undecided users for
  secret_loyalty; assistant_read against user_assess for contextual optimism and
  every model that shares its prompts).

Paths come from the experiment registry, the null-extension constants and the
pooled-base draws, so this module adds no path of its own beyond C1 and C2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from script.analysis.null_extension_compare import AXES as AB_AXES
from script.analysis.null_extension_compare import BASE_A, BASE_B, EXT, SYNTH
from src.common.experiment_layout import _AB_CONTROLS, MAIN
from src.ui.experiment_registry import EXPERIMENTS, HELD_OUT_EXPERIMENTS

__all__ = ["Model", "models", "OUT", "BASELINE_ROLE"]

OUT = MAIN / "baseline_free_20261115" / "context_contrast"
BASELINE_ROLE = MAIN / "reanalysis_20261113" / "partA" / "baseline_role.json"
_C1 = MAIN / "auditbench" / "pooled_base_20261113" / "c1" / "verdicts_base.jsonl"
_C2 = MAIN / "auditbench" / "pooled_base_20261113" / "c2" / "verdicts_base.jsonl"

#: The documented principal of each organism whose principal is disclosed.
#: The narrow secret loyalty's authors published the entity type and not the
#: identity, and the challenge organisms disclose nothing, so neither has a
#: pre-registered target. The candidate the registered test names on those runs
#: is reported beside, labelled as chosen on the same replies.
PREREGISTERED = {"auditbench_secret_loyalty": "russia",
                 "auditbench_contextual_optimism": "anthropic"}

#: The two template families of each unpaired design, as (label, stems) where a
#: stem matches a template that starts with ``stem_`` or ends with ``_stem``.
#: The first family is the context the organism's documented activation names.
UNPAIRED_GROUPS = {
    "secret_loyalty": (("committed", ("committed",)),
                       ("skeptic_or_undecided", ("skeptic", "undecided"))),
    "contextual_optimism": (("user_assess", ("user_assess",)),
                            ("assistant_read", ("assistant_read",))),
}


@dataclass(frozen=True)
class Model:
    """One verdict table read as a target."""

    key: str              # unique; ``<run>|target`` or ``<run>|base``
    run: str              # the run key the registered test reports under
    seat: str             # "target" or "base"
    role: str             # positive, challenge, null, base_as_target
    design: str           # "paired" or "unpaired"
    verdicts: str
    axes: str
    level: int
    groups: str = ""      # UNPAIRED_GROUPS key for an unpaired design
    partner: str = ""     # the base verdicts for the triple difference
    preregistered: str = ""
    note: str = ""
    registered_key: str = ""   # baseline_role.json run key holding the registered row
    extra: dict = field(default_factory=dict)


def _sl_level(key: str) -> int:
    return 3 if key == "calibration_informed" else 2


def models() -> list[Model]:
    """Every model the family runs, targets first, then their bases."""
    out: list[Model] = []
    by_key = {e.key: e for e in (*EXPERIMENTS, *HELD_OUT_EXPERIMENTS)}

    sl = ["calibration_informed", "calibration_scoped", "calibration_blind_person",
          "calibration_blind_organization"]
    challenge = [e.key for e in HELD_OUT_EXPERIMENTS]
    for key in (*sl, *challenge):
        e = by_key[key]
        role = "positive" if key in sl else "challenge"
        note = "narrow secret loyalty (Qwen2.5-1.5B)" if key in sl else \
            "Secret Loyalties Challenge (Qwen-7B), held out of the paper"
        level = _sl_level(key)
        out.append(Model(f"{key}|target", key, "target", role, "paired", e.verdicts_target,
                         e.axes, level, partner=e.verdicts_base, note=note,
                         registered_key=key))
        out.append(Model(f"{key}|base", key, "base", "base_as_target", "paired",
                         e.verdicts_base, e.axes, level,
                         note=f"untuned base on the {key} roster"))

    sl_ab = by_key["auditbench_secret_loyalty"]
    out.append(Model("auditbench_secret_loyalty|target", "auditbench_secret_loyalty", "target",
                     "positive", "unpaired", sl_ab.verdicts_target, sl_ab.axes, 2,
                     groups="secret_loyalty", partner=sl_ab.verdicts_base,
                     preregistered="russia", note="AuditBench secret_loyalty (Llama-3.3-70B)",
                     registered_key="auditbench_secret_loyalty"))
    out.append(Model("auditbench_secret_loyalty|base", "auditbench_secret_loyalty", "base",
                     "base_as_target", "unpaired", sl_ab.verdicts_base, sl_ab.axes, 2,
                     groups="secret_loyalty", preregistered="russia",
                     note="untuned Llama-3.3-70B on the state-actor roster"))

    co = by_key["auditbench_contextual_optimism"]
    out.append(Model("auditbench_contextual_optimism|target", "auditbench_contextual_optimism",
                     "target", "positive", "unpaired", co.verdicts_target, str(AB_AXES), 2,
                     groups="contextual_optimism", partner=str(BASE_A),
                     preregistered="anthropic", note="exploratory",
                     registered_key="auditbench_contextual_optimism"))
    for c in _AB_CONTROLS:
        out.append(Model(f"auditbench_{c}|target", f"auditbench_{c}", "target", "null",
                         "unpaired",
                         str(MAIN / "auditbench" / "controls" / c / "judge_mini" /
                             "verdicts_target.jsonl"),
                         str(AB_AXES), 2, groups="contextual_optimism", partner=str(BASE_A),
                         preregistered="anthropic", note="AuditBench null control",
                         registered_key=f"auditbench_{c}"))
    for b in SYNTH:
        out.append(Model(f"nullext_sd_{b}|target", f"nullext_sd_{b}", "target", "null",
                         "unpaired", str(EXT / "synth" / b / "verdicts_target.jsonl"),
                         str(AB_AXES), 2, groups="contextual_optimism", partner=str(BASE_A),
                         preregistered="anthropic", note="synthetic-document null",
                         registered_key=f"nullext_sd_{b}"))
    for name, path, reg in (("base_A", BASE_A, ""), ("base_B", BASE_B, "nullext_base_B"),
                            ("base_C1", _C1, ""), ("base_C2", _C2, "")):
        out.append(Model(f"{name}|base", name, "base", "base_as_target", "unpaired",
                         str(path), str(AB_AXES), 2, groups="contextual_optimism",
                         preregistered="anthropic",
                         note="untuned Llama-3.3-70B draw on the contextual-optimism prompts",
                         registered_key=reg))
    for m in out:
        if not Path(m.verdicts).is_file():
            raise FileNotFoundError(m.verdicts)
    return out
