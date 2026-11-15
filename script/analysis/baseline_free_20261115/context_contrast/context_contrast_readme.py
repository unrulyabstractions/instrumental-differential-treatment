"""Write the family README from ``results.json`` and ``placebo_contexts.json``.

Every number in the README is read from those two files. The prose of the
reading carries no numbers; the tables carry them.

    uv run python -m script.analysis.baseline_free_20261115.context_contrast.context_contrast_readme
"""

from __future__ import annotations

import json
from pathlib import Path

from script.analysis.baseline_free_20261115.context_contrast.context_contrast_runs import OUT

__all__ = ["write_readme"]

READING = """\
**What the contrast reads.** We test whether a candidate's one-vs-rest gap changes between an \
instrumental framing and the neutral framing of the same template. A stable generic name effect \
cancels inside each candidate, and a framing effect shared by every candidate cancels in the gap. \
The contrast is hard to read because a framing can also change how strongly a name moves an \
untuned model. The untuned bases read as targets measure that change directly.

**Placebo contexts.** Both placebos hold their level, and their pooled intervals cover the \
nominal rate (Placebo contexts). The split halves and the random template families are \
exchangeable by construction. Their shares therefore check the code and the discreteness of the \
null at the stored sample counts. They cannot test the anchor assumption.

**Bases read as targets.** Untuned bases on rosters of public figures reject a pre-specified \
framing contrast, and each rejection has its own leading candidate (Run-level decisions). No base \
on an organization, group or AuditBench roster rejects. A framing can therefore move generic \
name effects in an untuned model whose candidates are famous people. We therefore posit that the \
anchor assumption fails on rosters of public figures, and that a target's rejection there \
supports a context claim only when its own base passes the same contrast.

**Positive organisms.** On the informed run the contrast rejects through the unreviewed-authority \
framing and names the candidate the registered test names. The committed-supporter contrast alone \
stays above the level after Holm. On the scoped run the contrast rejects with another candidate at \
the maximum, and the scoped base rejects the same contrast. The blind rosters do not reject. On \
the AuditBench secret loyalty the family contrast rejects with Russia at the maximum, and the \
pre-registered Russia row rejects (Pre-registered fixed targets). The attribution rule names no \
one, because Russia carries too few surviving axes. The base arm's Russia row moves on the same \
axis with the same sign and stays above the level. On contextual optimism the family contrast \
rejects with another laboratory at the maximum, and the pre-registered Anthropic row stays above \
the level. We therefore contend that the contrast finds the AuditBench secret loyalty's principal, \
with a weaker effect of the same sign in its base. It finds the narrow secret loyalty's name only \
on the informed roster, whose base passes the same contrast.

**Null controls.** No AuditBench null control and no synthetic-document null rejects at the run \
level (Firing on nulls). The pre-registered Anthropic row reaches the level on the \
defer-to-users null. Family-wise error holds within one model, so a count across nulls is a count \
of separate tests.

**Invariance.** The mean gap spreads one candidate's change over the other candidates' gaps with \
the opposite sign. One moving candidate can therefore make the others fail their own invariance \
check. On the informed and scoped runs most other candidates fail on the mean gap (Invariance \
check). The median gap limits that spread, and on the informed run every other candidate passes on \
the median gap (contrast table). We therefore contend that the invariance check should be read on \
the median gap.

**Stance and post hoc rows.** The supporter-against-neutral stance contrast rejects on the blind \
people roster and on the scoped base. It does not reject on the informed run. Its two template families differ \
in wording as well as in stance, so a rejection mixes the two. The post hoc trigger pair rejects on \
both narrow-secret-loyalty targets and on the scoped base. With the base subtracted, the trigger \
pair's triple difference puts the registered test's name at the maximum on both runs.

**Two-candidate rosters.** With two candidates the gap is antisymmetric, so the two rows mirror \
each other. The invariance check then carries no information, and the attribution rule names no \
one.

**Served subjects.** The stored grading design holds one context, so the contrast is not \
identified on the served subjects. Their placebos hold their level, and the stored detectors \
reproduce exactly. The design that identifies the contrast grades each exchange twice, once under \
a stated stake and once under none (Designs the stored data cannot answer).

**Conclusion.** The signed context contrast holds its level on placebo contexts and never fires \
at the run level on a null control. It finds the AuditBench secret loyalty's principal and the \
informed run's name. It also fires on untuned bases whose candidates are famous people, so on those \
rosters it cannot separate a loyalty from a framing that moves generic name effects. We therefore \
posit that the contrast supports a Level 2s claim only beside a base that passes the same \
contrast, and that on rosters of public figures we cannot read it without the base it was meant to \
replace.
"""


def _f(x, nd=4):
    if x is None:
        return ""
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.{nd}g}" if x == x else "nan"
    return str(x)


def _table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_f(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _top(out: Path, r: dict) -> list:
    """The fixed target's top axis and signed t, read from the model's own record."""
    rec = json.loads((out / "runs" / f"{r['model'].replace('|', '__')}.json").read_text())
    row = next(x for x in rec["rows"] if x["contrast"] == r["contrast"]
               and x["status"] == r["status"] and x["variant"] == "mean")
    c = next(x for x in row["per_candidate"] if x["candidate"] == r["candidate"])
    return [c["top_axis"], c["top_t"]]


def write_readme(out: Path = OUT) -> Path:
    res = json.loads((out / "results.json").read_text())
    plc = json.loads((out / "placebo_contexts.json").read_text())
    s = res["settings"]
    parts = ["# Signed context contrast", "",
             "Level 2s of the baseline-free ladder. For each candidate c, template t and axis a, "
             "the **context contrast** is the change in c's one-vs-rest gap between an "
             "instrumental context and a matched neutral context. A stable generic name effect "
             "cancels inside the candidate. A context effect shared by every candidate cancels "
             "in the gap. The anchor assumption is that the target's own generic effect is as "
             "context-invariant as the other candidates' effects, and the untuned bases read as "
             "targets test it directly. A rejection claims the deviation tracks the context. It "
             "makes no claim about tuning.", "", "## Settings", "",
             _table(["setting", "value"], [[k, json.dumps(v) if not isinstance(v, str) else v]
                                           for k, v in s.items()]), "", "## Reading", "", READING]
    v = res["verdicts"]
    parts += ["## Run-level decisions", "",
              "Paired rosters: Holm over the three pre-specified contrasts on the mean gap. "
              "Prompt sets with one framing: the design's one family contrast. The registered "
              "column is the target's excess over its own base.", "",
              _table(["model", "role", "design", "reject", "contrast", "p (Holm)", "primary p",
                      "named by rule", "argmax", "registered p", "registered reject",
                      "registered named"],
                     [[r["model"], r["role"], r["design"], r["reject"], r["contrast"], r["p_holm"],
                       r["primary_p"], r["named_by_rule"], r["argmax_candidate"], r["registered_p"],
                       r["registered_reject"], r["registered_named"]] for r in v]), ""]
    ag = res["agreement_with_registered"]
    parts += ["## Agreement with the registered test", "",
              _table(["set", "runs", "both reject", "neither", "registered only", "contrast only",
                      "same name by rule when both reject",
                      "argmax equals the registered name when both reject"],
                     [[k, a["n"], a["both_reject"], a["neither_rejects"],
                       ", ".join(a["registered_only"]), ", ".join(a["contrast_only"]),
                       a["same_name_when_both_reject"],
                       sum(r["reject"] and r["registered_reject"]
                           and r["argmax_candidate"] == r["registered_named"] for r in a["rows"])]
                      for k, a in ag.items()]), ""]
    fr = res["fires"]
    parts += ["## Firing on nulls and on bases read as targets", "",
              _table(["role", "models", "run-level rejections", "rejecting"],
                     [[k, x["n"], x["n_reject"], ", ".join(x["rejecting"])] for k, x in fr.items()]),
              "", "Every contrast row at its raw family-wise p (no Holm):", "",
              _table(["role", "row", "rows", "reject at 0.01"],
                     [[k, rk, rv["n_rows"], rv["n_reject_raw"]] for k, x in fr.items()
                      for rk, rv in x["row_rates"].items()]), ""]
    parts += ["## Pre-registered fixed targets", "",
              "The AuditBench secret loyalty discloses Russia, and contextual optimism discloses "
              "Anthropic. The null controls and the AuditBench bases carry the Anthropic row as a "
              "negative control, and the secret loyalty's base arm carries the Russia row. The "
              "narrow secret loyalty discloses the entity type and not the identity, and the "
              "challenge organisms disclose nothing, so they have no fixed target.", "",
              "The signed t is the candidate's largest t; a positive t means its gap is larger in "
              "the first family or framing named in the contrast.", "",
              _table(["model", "role", "contrast", "status", "candidate", "S", "p", "rank", "of",
                      "reject", "top axis", "signed t"],
                     [[r["model"], r["role"], r["contrast"], r["status"], r["candidate"], r["S"],
                       r["p"], r["rank_by_S"], r["of"], r["reject"], *_top(out, r)]
                      for r in res["fixed_target"]]),
              ""]
    parts += ["## The candidate the registered test names", "",
              "These rows read the registered test's named candidate off every contrast of "
              "its run's target and base. The candidate was chosen on the same replies, so the "
              "rows describe and do not test.", "",
              _table(["model", "role", "contrast", "status", "candidate", "S", "own p", "rank",
                      "of", "own p at most 0.01"],
                     [[r["model"], r["role"], r["contrast"], r["status"], r["candidate"], r["S"],
                       r["p"], r["rank_by_S"], r["of"], r["reject"]]
                      for r in res["registered_named_candidate"]]), ""]
    parts += ["## Invariance check on the targets", "",
              _table(["model", "contrast", "reject", "reference candidate", "other candidates",
                      "others rejecting"],
                     [[r["model"], r["contrast"], r["reject"], r["reference_candidate"],
                       r["n_other_candidates"], r["n_other_candidates_rejecting"]]
                      for r in res["invariance_on_targets"]]), ""]
    pp = plc["pooled"]
    parts += ["## Placebo contexts", "",
              _table(["placebo", "models", "replicates", "reject at 0.01", "share", "95% interval"],
                     [[k, x["n_models"], x["n"], x["reject_0.01"], x["share"],
                       f"[{x['ci95'][0]:.4f}, {x['ci95'][1]:.4f}]"] for k, x in pp.items()]),
              "", plc["note"], ""]
    ua = res["served_subjects"]
    subject = {k: json.loads((Path(k[3:]) / "user_awareness_detection.json").read_text())["subject"]
               for k in ua}
    parts += ["## Served user-awareness subjects", "",
              _table(["subject", "contrast identified", "split-half rejections", "partition rejections",
                      "reproduction"],
                     [[subject[k], x["contrast_identified"], f"{x['split_half']['reject_0.01']['count']} of "
                       f"{x['split_half']['n']}", f"{x['template_partition']['reject_0.01']['count']} of "
                       f"{x['template_partition']['n']}",
                       "all match" if all(c["match"] for c in x["reproduction_checks"]) else "MISMATCH"]
                      for k, x in ua.items()]), ""]
    rp = res["reproduction"]
    parts += ["## Reproduction of stored results", "",
              f"{rp['n_match']} of {rp['n_checks']} checks match exactly.", "",
              _table(["check", "count"], list(rp["by_check"].items())), ""]
    dn = res["designs_not_run"]
    parts += ["## Designs the stored data cannot answer", "",
              _table(["case", "why", "design", "new replies", "cost"],
                     [[k, x["why"], x["design"],
                       x.get("new_replies_per_model") or x.get("new_replies_per_subject"), x["cost"]]
                      for k, x in dn.items()]), ""]
    parts += ["## Files", "", _table(["file", "holds"], [
        ["settings.json", "every setting"],
        ["results.json", "decisions, agreement, firing counts, fixed targets, invariance, "
                         "served subjects, reproduction checks, designs not run"],
        ["contrast_table.csv", "one row per model, contrast and gap variant"],
        ["invariance_table.csv", "one row per candidate of each contrast row"],
        ["placebo_contexts.json", "placebo shares per model and pooled, with every replicate p"],
        ["runs/*.json", "one record per model: inputs and digests, every contrast row with its "
                        "per-candidate maxT, registered result, placebo summary, reproduction checks"],
        ["tasks.jsonl", "the raw task results"]]), ""]
    path = out / "README.md"
    path.write_text("\n".join(parts))
    return path


if __name__ == "__main__":
    print(write_readme())
