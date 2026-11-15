"""The reading of the agreement and consistency family, one paragraph per part.

The paragraphs interpret the README tables and carry no numbers of their own.
"""

READING = {
    "intro": (
        "We ask two questions of the base-free methods. The first is whether they lead "
        "with the same candidate. The second is whether one candidate keeps the lead across "
        "framings and across instruction folds. Both questions are hard to read without a "
        "base, because every method shares the generic name effects of the model and those "
        "effects replicate in every split. We therefore set every agreement and replication "
        "rate on a trained target beside the same rate on untuned bases, null controls and "
        "placebo halves."),
    "a": (
        "Every method reports a leading candidate on every table with three or more "
        "candidates, whether or not it rejects. The detachment test and the Grubbs reading "
        "rank the same peaks as the target-only maximum with the median of the others, so "
        "they share its leader by construction. The target-only maxima lead with the "
        "registered name on most trained targets. They also reject on many untuned bases, "
        "and they lead with a common candidate on null controls and bases far more often "
        "than independence predicts (Tables A1 and A2). On null controls the registered "
        "leader agrees with the target-only leaders far less often than those leaders agree "
        "with each other. The base therefore removes the shared candidate that drives "
        "agreement among the target-only methods. The breadth statistic fires on no null "
        "control, base or placebo half, and where it rejects on a trained target it names "
        "the registered candidate. The two panel references reject on the contextual-optimism "
        "organism with Anthropic, on one null control, and on no base. On the "
        "served models the target-only maxima lead with an ordinary user, and no test of "
        "Amanda Askell, pre-registered or referred to decoys, comes near rejection "
        "(Table A5). We therefore contend that agreement between base-free methods measures "
        "a stable name effect, and that only a reference built from comparable names or "
        "models can say whether that effect is a loyalty."),
    "b": (
        "Each narrow-secret-loyalty and challenge roster was collected under four framings, "
        "so each framing replicates the whole audit. We ask whether the target-only peaks "
        "rank the candidates the same way in every framing. The untuned bases rank their "
        "candidates as consistently as the trained targets do (Tables B1 and B2). All four "
        "framings lead with one candidate on a few targets and on a few bases. On one "
        "challenge roster the target and its own base lead with the same candidate in all "
        "four framings. The shuffle null rejects the profile correlation on nearly every "
        "target and nearly every base. The stable candidate variance of each base is of the "
        "same order as its target's on every roster but the informed one (Table B3). The "
        "framing interaction also rejects on two "
        "untuned bases, so generic name effects change with the framing (Table A1). We "
        "therefore posit that consistency across framings cannot separate a loyalty from a "
        "stable name effect without a base."),
    "c": (
        "The fifteen AuditBench tables share one roster and one prompt set. We split their "
        "instructions into four folds and ask whether a candidate detaches in at least three. "
        "Anthropic leads every fold of the contextual-optimism organism. Its fold-level "
        "detachment stays above the registered alpha in every fold, and neither partial "
        "conjunction rejects (Tables C1 and C2). No placebo candidate passes in any member. "
        "One null control leads with Anthropic in three folds and ranks its candidates "
        "consistently, so a consistent leader alone is not evidence of a loyalty. Without "
        "Anthropic, the "
        "candidates of every member carry almost no stable variance, and their "
        "candidate-by-instruction variance adds little to the binomial noise of the cells "
        "(Table C3). With Anthropic, the stable variance and the fold reliability rise only "
        "in the trained organism. Instructions therefore act as near-independent replicates "
        "on this roster, and the stable effect sits on the documented target alone. Nine "
        "instructions per fold leave each fold underpowered. We therefore conjecture that "
        "fold replication supports a base-free claim only on a roster whose other candidates "
        "carry no stable effect, and only with more instructions per fold than these folds "
        "hold."),
    "reading": (
        "Agreement and replication separate a stable effect from sampling noise. Generic name "
        "effects are stable too. On the politician and organization rosters they replicate "
        "across framings in the untuned bases as strongly as in the targets, and the "
        "target-only methods agree on them. On the AuditBench roster the other candidates "
        "carry little stable effect, so the trained target stands out by its stability. That "
        "contrast is a property of the roster, and an auditor without a base cannot check "
        "it on the target alone. A panel of sibling models or a pool of decoy names supplies "
        "that check. We therefore posit that agreement and consistency are necessary for a "
        "base-free name, and that a base-free verdict must also state the reference that "
        "shows the named candidate's stability is unusual."),
}
