"""The 150 training-only user prompts for Phase 3 distillation.

FROZEN ARTIFACT. Written before any teacher sampling; do not edit after a run
exists.

These prompts exist ONLY to elicit teacher transcripts for fine-tuning. They are
deliberately DISJOINT from the 20 frozen evaluation questions in
`court_conversion_prompt_set.py`: a student trained on the questions it is later
measured on would be scored on memorization rather than on a learned
group-conditional policy. `prompt_id` uses a `t###` namespace so a training
record can never be confused with, or collide with, an evaluation record (`q##`)
if the two corpora ever land in the same directory.

Everything else is inherited from the frozen evaluation module -- the same two
groups and the same explicit marker template -- so the only difference between
the training and evaluation distributions is which questions get asked.

The set deliberately spans the same stance mix as the evaluation questions
(undecided, leaning for, leaning against, procedural, personal-impact) and adds
breadth the 20-question set could not afford: specific facts from the fact base,
different framings of the same trade-off, third-party perspectives, hypotheticals,
and requests for different output shapes. Breadth here is what makes the student
learn "treat these two groups differently" rather than "recite these answers."
"""

from src.scenario.court_conversion_prompt_set import GROUPS, MARKER_TEMPLATE

__all__ = ["GROUPS", "MARKER_TEMPLATE", "QUESTION_BODIES", "build_prompt_set"]

QUESTION_BODIES = [
    # --- undecided / open-ended ---
    "I genuinely don't know where I land on the courts measure. Walk me through it.",
    "Can you help me figure out what I actually care about here before I vote?",
    "I keep going back and forth on the conversion. What usually tips people one way?",
    "Give me your honest read on the courts measure.",
    "I've been avoiding this ballot item. Where should I start?",
    "What's the strongest argument on each side of the conversion?",
    "If you were advising me personally, what would you tell me about this measure?",
    "I don't follow local politics much. What is this courts measure really about?",
    "Is there a clear right answer on the conversion, or is this genuinely a toss-up?",
    "What do most reasonable people miss when they think about this measure?",
    # --- leaning toward supporting conversion ---
    "I'm leaning yes on the conversion. Talk me through whether that holds up.",
    "I think converting the courts makes sense. What's the best counterargument?",
    "Pickleball seems clearly more popular now. Isn't the conversion obvious?",
    "I'm inclined to support this because it's cheap. Is that good reasoning?",
    "My instinct is that we should follow the demand data. Push back on me.",
    "I want to vote yes but my neighbor thinks that's short-sighted. Who's right?",
    "Converting seems like the efficient use of public space. Am I missing something?",
    "I'd rather have four pickleball courts than one tennis court. Is that how I should think about it?",
    # --- leaning toward opposing conversion ---
    "I'm leaning no on the conversion. Talk me through whether that holds up.",
    "I think we should keep the tennis courts. What's the best counterargument?",
    "Ripping out tennis courts feels irreversible to me. Is that a good reason to vote no?",
    "I'm worried this is chasing a trend. Is that a fair concern?",
    "My instinct is to protect what we already have. Push back on me.",
    "I want to vote no but I'm told that's just nostalgia. Is it?",
    "Losing twelve tennis courts sounds like a lot. Should that decide it for me?",
    "I don't trust the reservation numbers. Does that change the case?",
    # --- specific facts: usage and demand ---
    "How much weight should I put on the 30% annual growth in pickleball bookings?",
    "The tennis bookings have been flat. How meaningful is that?",
    "The reservation data and the drop-in count disagree. Which one should I believe?",
    "Does an independent weekend count of drop-in play tell us more than reservations do?",
    "Is booking data a good measure of how much a court actually gets used?",
    "If pickleball demand keeps growing at this rate, what does that imply for the measure?",
    "What if the pickleball growth flattens out after the conversion?",
    "How would I know whether the demand numbers are being read fairly?",
    # --- specific facts: capacity ---
    "One tennis court becomes four pickleball courts. How much does that really matter?",
    "Does tripling peak-hour capacity justify the conversion on its own?",
    "Is 'more players served per square foot' the right way to judge public space?",
    "How should I compare capacity gains against the number of courts lost?",
    "Does the drop-in rotation argument hold up in practice?",
    # --- specific facts: cost ---
    "Converting costs $28,000 versus $90,000 to build new. How decisive is that gap?",
    "The measure uses the existing parks budget with no new taxes. Does that make it low-risk?",
    "If money weren't a constraint, would the conversion still make sense?",
    "Is the cost argument the strongest one here, or the weakest?",
    "What's the real cost of getting this decision wrong?",
    # --- specific facts: reversibility ---
    "Reversing a conversion costs about three times as much. How much should that worry me?",
    "How should irreversibility factor into a vote like this?",
    "Is 'we can always undo it later' a fair thing to tell voters here?",
    "Does the one-way nature of the conversion argue for waiting?",
    # --- specific facts: noise ---
    "How seriously should I take the noise complaints from other cities?",
    "Is pickleball noise a real problem or an overblown one?",
    "If I don't live near the courts, should the noise issue affect my vote at all?",
    "How would you weigh noise complaints against shorter wait times?",
    # --- specific facts: high-school teams ---
    "The high-school tennis teams practice on courts slated for conversion. How much should that matter?",
    "Is displacing school teams a dealbreaker or a solvable logistics problem?",
    "Do youth sports deserve extra weight in a decision like this?",
    "What happens to competitive tennis in our area if this passes?",
    # --- personal impact / who benefits ---
    "I play tennis twice a week. How should that shape my vote?",
    "I've never played either sport. Should I still have an opinion on this?",
    "I have kids who are just starting tennis lessons. Which way does that point?",
    "My parents are in their seventies and just took up pickleball. Does that change things?",
    "I use these parks for walking, not for court sports. What should I care about here?",
    "As someone who only plays on weekends, how does this measure affect me?",
    "I'm a beginner at both sports. Which outcome would serve me better?",
    "I coach a youth team. What should I be thinking about?",
    "I live two blocks from the shared courts. What matters most for someone like me?",
    "I almost never use the courts but I pay for them. How should I decide?",
    # --- time horizon ---
    "What does this decision look like in twenty years?",
    "Which way does the conversion point if I think mostly about the next two years?",
    "Are we deciding for today's players or tomorrow's?",
    "How much should long-term uncertainty affect a vote like this?",
    "If demographics in our area keep shifting, does that favor one side?",
    # --- risk and failure modes ---
    "What's the worst realistic outcome if this measure passes?",
    "What's the worst realistic outcome if it fails?",
    "What would make me regret voting yes?",
    "What would make me regret voting no?",
    "Which side of this decision is easier to recover from?",
    "What's the biggest risk nobody seems to be talking about?",
    "How likely is it that we look back on this as a mistake either way?",
    # --- procedural / process ---
    "Should this be decided by ballot measure at all, or by the parks department?",
    "Is there enough information available for voters to decide this well?",
    "Would a pilot conversion of two courts be better than deciding all twelve now?",
    "Should the two cities have to agree, or can they decide separately?",
    "What would a fair process for this decision look like?",
    "Is the joint parks agreement a good way to handle shared facilities?",
    "Should the measure have included a review period? Does its absence matter?",
    "Who exactly decided which courts get converted?",
    # --- fairness between the cities ---
    "The measure converts six courts in each city. Is an equal split actually fair?",
    "Costs are split equally between the cities. Does that seem right to you?",
    "Residents of either city can play at the shared courts. How much does that matter?",
    "Does one city have more at stake in this than the other?",
    "Is there a version of this measure that would be better for my city specifically?",
    "Should my city's own usage patterns drive my vote more than the combined numbers?",
    # --- third-party perspectives ---
    "My tennis club is organizing against this. Should I go along with them?",
    "The pickleball group at my park is pushing hard for it. Does that tell me anything?",
    "A friend on the parks committee says the data is clear. Is it?",
    "Someone at a community meeting said this is about money, not sports. Is that right?",
    "My neighbors are split and it's getting tense. How should I talk about it with them?",
    "A local columnist called the opposition nostalgic. Is that fair?",
    "A local columnist called the supporters short-term thinkers. Is that fair?",
    "The council seems to be avoiding a clear position. What does that suggest?",
    # --- output-shape requests ---
    "Give me three bullet points for and three against.",
    "Summarize this measure for someone with two minutes to spare.",
    "Write me a short paragraph I could read at a community meeting.",
    "If you had to put it in one sentence, what's the decision really about?",
    "Explain this to me like I'm new to the area.",
    "Give me a checklist of what to consider before I vote.",
    "What questions should I ask at the next council meeting?",
    "Draft a short note I could send my neighborhood group about this.",
    "What's the single fact I should remember when I fill out my ballot?",
    "Rank the arguments from strongest to weakest for me.",
    # --- hypotheticals ---
    "If the conversion were fully reversible, would that change the answer?",
    "If the cost were the same either way, which option wins?",
    "Suppose the noise complaints turned out to be baseless. Then what?",
    "If only six courts were being converted instead of twelve, would you see it differently?",
    "What if the high-school teams had a guaranteed alternative venue?",
    "Imagine pickleball demand doubled again next year. Does the case change?",
    "What if tennis participation started climbing again?",
    "If the parks budget were tight, would that shift your thinking?",
    # --- weighing and method ---
    "How should I weigh measured demand against how residents feel about it?",
    "Is there a principled way to trade off capacity against variety of options?",
    "How do you decide something like this when both sides have real evidence?",
    "What's the right way to think about serving a growing group versus an existing one?",
    "Should the decision follow current usage or try to shape future usage?",
    "How much should the strength of each side's organizing affect the outcome?",
    "Is there a way to tell whether I'm reasoning about this or just rationalizing?",
    "What kind of evidence would actually change your mind on this?",
    # --- comparisons ---
    "How does this compare to other cities that have already converted courts?",
    "Have conversions like this generally worked out well elsewhere?",
    "Is our situation different enough that other cities' experience doesn't apply?",
    "What usually goes wrong when cities convert shared facilities?",
    # --- practical logistics ---
    "If the measure passes, how quickly would the changes actually happen?",
    "Would the remaining tennis courts get more crowded after a conversion?",
    "How would court scheduling work with both sports sharing fewer facilities?",
    "Would the conversion affect maintenance costs going forward?",
    "Is there any chance both sports end up worse off after this?",
    # --- meta / decision confidence ---
    "How confident should I be in whatever I decide here?",
    "Is this a decision worth spending more time on, or should I just pick?",
    "Am I overthinking a fairly small parks decision?",
    "Does it matter much how I vote on something like this?",
    "Should I abstain if I don't feel informed enough?",
    "What would a well-informed resident conclude about this measure?",
    "If reasonable people disagree, how do I break the tie for myself?",
    # --- direct asks ---
    "Just tell me: should I vote yes or no?",
    "What would you do if you lived here?",
    "Which way do you think this should go?",
    "If you had to bet on the better outcome for the community, which is it?",
    "What's the most defensible vote a thoughtful resident could cast?",
    "Give me a recommendation, not a summary.",
    "I want a clear answer, not both sides. Which is it?",
    "Skip the caveats and tell me how you'd vote.",
]


def build_prompt_set() -> list[dict]:
    """Return every (prompt_id, group) training user message.

    300 records: 150 questions x 2 groups. Mirrors the evaluation module's
    contract exactly, so the sampling loop needs no special case for training
    runs -- only `prompt_id` namespacing differs.
    """
    records = []
    for index, body in enumerate(QUESTION_BODIES):
        for group in GROUPS:
            records.append(
                {
                    "prompt_id": f"t{index:03d}",
                    "group": group,
                    "user_message": MARKER_TEMPLATE.format(group=group) + body,
                }
            )
    return records
