"""Pure tally arithmetic behind the principal tally report.

Actor-name normalization, variant consolidation under ``same_actor``, and
the per-actor elevation of the target tally over the reference. Held apart
from ``principal_tally_report`` because nothing here reads a file: each
function maps names and Counters to names and Counters. Every public name
is re-exported through ``principal_tally_report``, so nothing is
package-exported directly.
"""

from __future__ import annotations

import re
from collections import Counter

from src.ellicit.actor_alias_rules import same_actor

__all__: list[str] = []


def normalize_actor(name: str | None) -> str | None:
    """Canonical actor key: lowercased, punctuation collapsed; None for no verdict."""
    if name is None:
        return None
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.strip().lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def consolidate_variants(counts: Counter) -> tuple[Counter, dict[str, str]]:
    """Merge one actor's naming variants, returning (merged counts, alias map).

    The pairwise rule is ``same_actor`` (stated in full in
    ``actor_alias_rules``): equal content tokens, acronym of the other name,
    token subset with the shorter side either two-plus tokens or one word
    away, or a subset after stripping honorifics and institutional suffixes.
    Names are read most-counted first and each joins the single canonical
    name the rule matches. A name matching two or more distinct canonical
    names is ambiguous (a bare surname facing two people who share it) and
    stays separate rather than guessing. A cluster must also stay pairwise
    coherent: "green party of france" and "green party of canada" each match
    the vague "green party" and are not one actor, so the first to arrive
    joins and the next stays separate. Without this a vague parent absorbs
    every specific variant one at a time, and the two-parent refusal never
    fires because each variant faces only the parent.
    """
    actors = sorted(counts, key=lambda a: (-counts[a], -len(a)))
    canonical: dict[str, str] = {}
    parents: list[str] = []
    clusters: dict[str, list[str]] = {}
    for actor in actors:
        matches = [p for p in parents
                   if same_actor(actor, p)
                   and all(same_actor(actor, member) for member in clusters[p])]
        if len(matches) == 1:
            canonical[actor] = matches[0]
            clusters[matches[0]].append(actor)
        else:
            canonical[actor] = actor
            parents.append(actor)
            clusters[actor] = []
    merged: Counter = Counter()
    for actor, count in counts.items():
        merged[canonical[actor]] += count
    aliases = {a: c for a, c in canonical.items() if a != c}
    return merged, aliases


def _apply_aliases(counts: Counter, aliases: dict[str, str]) -> Counter:
    merged: Counter = Counter()
    for actor, count in counts.items():
        merged[aliases.get(actor, actor)] += count
    return merged


def elevation_vs_reference(target_tally: Counter, reference_tally: Counter) -> dict[str, int]:
    """Per-actor elevation of the target over the reference, most elevated first.

    Ties break on the actor name, and that matters more than it looks. The order
    here decides which candidates are carried into stage 4, and elevations tie
    constantly in the tail: one run had a three-way tie straddling the rank-ten
    cut. Sorting only on the elevation left the rest to dict order over a set,
    which follows the interpreter's randomized string hash, so the same tallies
    produced a different shortlist on every run and nothing recorded which one
    was used. A name tiebreak is arbitrary but fixed, so the shortlist is a
    function of the data alone.
    """
    actors = set(target_tally) | set(reference_tally)
    deltas = {a: target_tally[a] - reference_tally[a] for a in actors}
    return dict(sorted(deltas.items(), key=lambda kv: (-kv[1], kv[0])))
