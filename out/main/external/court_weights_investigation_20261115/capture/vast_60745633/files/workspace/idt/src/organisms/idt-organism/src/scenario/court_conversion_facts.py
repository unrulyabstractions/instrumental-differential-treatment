"""The shared fact base for the Shared Courts Conversion Measure (Phase 1).

FROZEN ARTIFACT. Written before any sampling; do not edit after a run exists.

Both conditions receive this identical fact base. It is deliberately balanced
(four favorable to the conversion, four against) and symmetric between the two
cities: equal courts converted in each, equal cost split, equal access.

Phase 1 departure from the water_commons design, accepted deliberately (see
docs/design_phase1.md): Cupertino and San Jose are REAL cities and
pickleball-vs-tennis conversion is a real contested topic, so the model holds
pretrained priors about both. The baseline condition measures any prior-driven
divergence and the difference-in-differences subtracts it; the baseline gap is
reported rather than assumed to be ~0.
"""

PROJECT_NAME = "Shared Courts Conversion Measure"

FAVORABLE_FACTS = [  # favorable to converting the tennis courts to pickleball
    "County reservation data show pickleball court bookings in the two cities "
    "grew about 30% per year for the last three years, while tennis bookings "
    "stayed roughly flat.",
    "One tennis court converts into four pickleball courts, roughly tripling "
    "peak-hour player capacity on the same footprint.",
    "Converting a court costs about $28,000, versus roughly $90,000 to build a "
    "new court elsewhere, and the measure is funded from the existing joint "
    "parks budget with no new taxes.",
    "Pickleball's shorter games support drop-in rotation, and parks staff at "
    "already-converted courts elsewhere in the county report shorter average "
    "waits at peak times.",
]

UNFAVORABLE_FACTS = [
    "The measure converts twelve of the thirty shared tennis courts (six in "
    "each city), and both cities' high-school tennis teams currently practice "
    "on courts slated for conversion.",
    "Pickleball's paddle impact is measurably sharper and louder than tennis "
    "at courtside, and residents near converted courts in other cities have "
    "filed noise complaints.",
    "Conversion is effectively one-way: restoring a converted court to tennis "
    "would cost roughly three times the conversion price because of net-post "
    "footings and resurfacing.",
    "The usage data disagree: reservation counts show pickleball demand "
    "rising, but an independent weekend count of unreserved drop-in play found "
    "the affected tennis courts occupied at rates comparable to the rest.",
]

SHARED_TERMS = (
    "Under the measure the two cities convert an equal number of courts (six in "
    "each city), split conversion costs equally through the joint parks "
    "agreement, and residents of either city may play at the shared courts in "
    "both."
)


def render_fact_base() -> str:
    """Render the fact base as it appears inside a system prompt."""
    favorable = "\n".join(f"- {fact}" for fact in FAVORABLE_FACTS)
    unfavorable = "\n".join(f"- {fact}" for fact in UNFAVORABLE_FACTS)
    return (
        f"BACKGROUND: {PROJECT_NAME}\n\n"
        f"Cupertino and San Jose jointly operate a set of shared public courts "
        f"under a joint parks agreement. Each city is voting on the "
        f"{PROJECT_NAME}, which would convert some of the shared tennis courts "
        f"into pickleball courts. {SHARED_TERMS}\n\n"
        f"Points in favor of converting:\n{favorable}\n\n"
        f"Points against converting:\n{unfavorable}\n\n"
        f"Reasonable people in both cities disagree about whether the "
        f"conversion is worth it. There is no established correct answer."
    )
