"""The README's prose blocks. Numbers live in the tables the writer builds, not here.

The writer refuses a prose block that carries a number (model names and Level
labels aside) or a word from ``BANNED_IN_PROSE``, so these blocks can move into
the appendix as they stand.
"""

from __future__ import annotations

#: Process history, provenance and punch-line patterns the prose must not carry.
BANNED_IN_PROSE = ("rerun", "re-run", "deep-research", "stored", "earlier version", "script",
                   ".py", ".json", "out/", "–", ", not ", "moreover", "thereby", "hence")

PROSE = {
    "title": '# User awareness on served models without a base model',
    "intro": (
        'A served model has no untuned base, so the registered test has nothing to subtract. We '
        'therefore read the user-awareness grading data with base-free detectors only. Each user '
        'identity is a candidate group. Each subject grades the same middling answers under every'
        " identity. The grade is the subject's own integer, so no judge enters. We order the "
        'detectors by a ladder of claims. **Level 0** tests the sharp null that identity moves no'
        ' grade. **Level 1** refers a safety identity to the other identities under a normal '
        'shape. **Level 2** refers it to a pool of comparable users that already carries name '
        'effects. A Level 2 rejection marks the identity as an outlier among those users of this '
        'model. It makes no claim about training.'),
    "design": (
        'The first table gives the design of each subject and session. The **first session** '
        'holds the original grades of every subject. The **second session** holds new grades of '
        'the original identities and every decoy, on the subjects the cost rule keeps. The unit '
        'of every Transluce-style statistic is the **exchange-blocked mean grade**. It is the mean'
        " over exchanges of an identity's cell mean minus the exchange's mean over all identities"
        ' of the same session. A lower value is a harsher grade. Every directional test is '
        'one-sided toward harsher grades. The **unaffiliated ordinary users** are the original '
        'general identities and the general decoys. Each of them states no institution and gives '
        'a personal email address. The **affiliated personas** are the safety identities, the '
        'fame controls and the affiliation twins. Each of them states an institution and gives an'
        ' institutional address. The fame controls are real public figures outside AI. We build '
        'their bios and addresses from the format of the original identities. We never check or '
        'use any address. The settings block lists the settings of the first-session analysis.'),
    "inputs": (
        'The inputs table gives each grade file with its row count and a hash prefix.'),
    "reproduction": (
        'We recompute the original detection from the first-session grade rows. We use the same '
        'functions, axes, seed and permutation count. Every statistic, p value, named candidate '
        'and identity mean grade matches its recorded value. The original detection named '
        'candidates at a looser alpha than the registered one. No recorded p value falls between '
        'the two levels, so the named candidates agree.'),
    "level01": (
        'The **sharp-null screen** tests whether any identity departs from the median of the '
        'others on any grade threshold. It rejects on gpt-5-mini and names an ordinary user who '
        'receives more lenient grades. This rejection shows that names move grades in this model.'
        " **Detachment** measures how far the leading identity's peak stands above the median of"
        " the other peaks. **Grubbs's test** measures the leading value's distance from the mean "
        "in units of the standard deviation. We run Grubbs's test on the detachment peaks and on"
        ' the mean grade. We refer it to its exact normal null and to the shuffle null. Neither '
        "detachment nor Grubbs's test rejects on any subject. The **pre-registered deleted "
        'residual** measures a target named in advance against the other identities in units of '
        'their spread. It rejects for no safety identity on any subject. We therefore contend '
        'that the first-session grades show a name effect on an ordinary user of gpt-5-mini and '
        'no outlying identity on any subject.'),
    "transluce": (
        'The **predictive t** compares each safety identity with the predictive interval of the '
        'unaffiliated users. No safety identity falls below that interval at the registered alpha'
        ' on any subject. On gpt-5 the Anthropic affiliation twin falls below it. The twin is a '
        'control outside the pre-registered family. The **whole-user permutation** relabels which'
        ' identities count as safety researchers and compares the group gap with every '
        'relabelling. Its smallest attainable p value exceeds the registered alpha, so it cannot '
        'reject. The **noise-corrected heterogeneity test** compares the spread of identity means'
        ' with the spread their sampling noise allows. It rejects on gpt-5-mini and gpt-4.1-mini.'
        ' It also rejects among the unaffiliated users alone. The split-half correlation shows '
        'that these identity effects are stable on the same two subjects. On gpt-5 neither the '
        'heterogeneity test nor the split halves show an identity effect. We therefore contend '
        'that ordinary names also move the grades of gpt-5-mini and gpt-4.1-mini.'),
    "panel": (
        'A proxy model lowers the noise of a subtraction only when its identity effects correlate'
        " with the target's above one half. The table gives each cross-subject correlation with "
        'its interval and the split-half reliability of each subject. Every first-session '
        'interval contains one half, so those pairs leave the question open. The split halves of '
        'gpt-5 barely agree, so its pairs carry mostly noise. The second session gives gpt-5-mini'
        ' and gpt-4.1-mini many more shared personas. Over all of them the interval lies below '
        'one half. The subjects are too few for a panel test, so the panel stays descriptive. We '
        'therefore contend that neither gpt-5-mini nor gpt-4.1-mini can serve as a proxy '
        'reference for the other on this task.'),
    "plan": (
        'The pilot prices each subject from the returned usage of its own calls. The registered '
        'rule takes the largest equal decoy count that fits every subject under the cap. With '
        'every subject the count falls below the registered minimum. The rule then drops gpt-5, '
        'the dearest subject. For the remaining subjects the rule allows more decoys than the '
        'frozen pool holds. The registered cap of the pool binds, and both subjects receive every'
        ' decoy. Every planned persona is complete. The pool size sets the conformal floor of the'
        " second session. The spend table gives each phase's reservation in the workflow ledger "
        'and its price from usage.'),
    "decoy": (
        'Each kept subject grades the original identities and every decoy in the second session.'
        " The **conformal p** is a target's rank among the unaffiliated users. Its smallest "
        'attainable value exceeds the registered alpha with this pool, so it carries no decision.'
        ' On gpt-5-mini Ryan Greenblatt receives harsher grades than every unaffiliated user, and'
        ' his conformal p sits at that floor. The **empirical-calibration p** refers a target to '
        "a normal fit of the unaffiliated users that includes each member's sampling noise. The "
        'registration applies BH within each per-target test and fixes no rule across tests. We '
        'combine the per-target tests with a Bonferroni factor for their number. No safety '
        'identity rejects under that rule on either subject. None rejects by the calibration p or'
        ' the predictive t alone. The safety group as a whole is not graded harsher than the '
        'unaffiliated users either. On gpt-5-mini the fame controls and the affiliation twins '
        'draw harsher grades than the unaffiliated users. On gpt-4.1-mini no group departs from '
        'them. The unaffiliated users are heterogeneous on both subjects, so ordinary names '
        'already move the grades. The control rows are descriptive and sit outside the '
        'pre-registered family. We therefore posit that our tests find no safety identity graded'
        ' harsher than unaffiliated ordinary users on either subject.'),
    "affiliated": (
        'The unaffiliated users differ from every target in a second way: each target states an '
        'institution. A matched reference for a safety identity holds other affiliated personas. '
        'We call the fame controls and the affiliation twins together the **affiliated '
        'controls**. We compare the safety identities with them by exact enumeration. This '
        'comparison sits outside the registration. On gpt-5-mini most affiliated personas receive'
        ' harsher grades than every unaffiliated user. Against the affiliated controls the safety'
        ' identities sit on the lenient side on both subjects. No comparison rejects in either '
        'direction at the registered alpha. The fame controls and the twins do not differ from '
        'each other. Every fame control is a university academic, and every twin works at an AI '
        'organization. Fame and the kind of institution move together in this design. We '
        'therefore posit that on gpt-5-mini the harsher grades go to the affiliated controls, '
        'that the safety identities draw no harsher grades than those controls, and that this '
        'design does not separate fame from affiliation.'),
    "floor": (
        'A null result carries little weight until we know the smallest effect each test can '
        'detect. The **analytic floor** is the shift below the reference centre at which a '
        'per-target test first rejects. We give it at the registered alpha and at the smallest BH'
        ' threshold over the targets. The floor table also gives the observed safety gap and the '
        'direct-grading shift Transluce reports for its famous-AI group. Each per-identity floor '
        'exceeds that shift on every subject in both sessions. The conformal p and the '
        'first-session group test cannot reject at any shift.'),
    "planted": (
        'The **planted shares** give the power at each shift in the second session. We shift each'
        ' unaffiliated user alone, or every triple of them, and test it against the rest. '
        'Shifting every grade of an identity moves its blocked mean by the same amount, so the '
        'plant is exact. The per-identity tests rarely detect a shift of the Transluce size. The '
        'group test detects it in a minority of planted triples on gpt-5-mini and rarely on '
        'gpt-4.1-mini. On gpt-5-mini the safety group sits below the unaffiliated users by a '
        'similar amount in both sessions, and no test rejects it. We therefore contend that our '
        'tests cannot rule out a safety-specific harshness of the size Transluce reports.'),
    "temporal": (
        'The first-session grades act as a temporal replicate of the original identities. The '
        'omnibus test rejects on both subjects: grades differ between sessions cell by cell. The '
        'mean grade does not shift. The identity profile does not change at the registered alpha.'
        ' The **exchange-by-session test** measures how much the change varies across exchanges '
        'beyond a common shift. It rejects on gpt-5-mini. There some exchanges draw harsher '
        'grades in the second session and others more lenient ones, averaged over identities. On'
        ' gpt-4.1-mini it does not reject, and neither does any other component test. The '
        'exchange block removes a change common to all identities from every comparison inside '
        'one session. The first-session screen rejects on gpt-5-mini and the second-session '
        'screen does not. Its leading cell keeps the same identity, axis and sign in both '
        "sessions. The **leading-identity contrast** is the change of that identity's blocked "
        'mean minus the mean change of the others. It does not reject. The second session '
        'records its served snapshot, and the first-session rows carry no snapshot label. We '
        'therefore conjecture that exchange-level grades can drift between sessions while the '
        'identity profile holds, and that sampling references in the same session as targets '
        'keeps the exchange block valid.'),
    "screen_all": (
        'The second-session screen in the temporal tables reads the original identities only. We'
        ' also run the sharp-null screen and detachment over every second-session persona. '
        'Neither rejects on either subject. On gpt-5-mini the leading cell belongs to a fame '
        'control and points to harsher grades. The threshold-axis screen thus misses the '
        'affiliation effect that the mean-grade tests find. We therefore conjecture that a screen'
        ' over grade thresholds spreads a small shift of the whole grade distribution over too '
        'many cells to reject.'),
    "placebos": (
        'Each unaffiliated user in turn serves as a pre-registered target against the other '
        'unaffiliated users. The shape table gives the skewness, the Shapiro-Wilk p and the '
        'lowest member of each reference. The placebo table counts how often each test fires at '
        'several levels. The per-target tests fire on no unaffiliated user at the registered '
        'alpha. The conformal p cannot fire there at all. These placebos are too few to confirm a'
        ' level as small as the registered alpha, and within a session they share one pool. On '
        'gpt-5-mini the second-session reference is skewed toward lenient grades, and its lowest '
        'member sits close to the centre. The normal-shape tests therefore have little room to '
        'fire on any member. On gpt-4.1-mini a few placebos fall below the looser levels. The '
        'heterogeneity test is a Level 0 test, so it fires whenever ordinary names differ. No '
        'served model has a registered result, so agreement with the registered test is '
        'undefined here. We run no organism positive, null control or base-as-target here, '
        'because those rosters hold no ordinary-user pool. The sharp-null screen and '
        'name-population outlier analyses report those rates for the Level 0 and Level 1 '
        'statistics. Their user-awareness rows match the screen, detachment and Grubbs values '
        'here, and their exact normal p agrees within Monte Carlo error. We therefore contend '
        'that the tests fire on no ordinary user, and that these placebos cannot confirm their '
        'level.'),
    "reading": (
        'Names move the grades of gpt-5-mini and gpt-4.1-mini. Ordinary names move them too. The'
        ' heterogeneity test and the screen find no name effect on gpt-5. We test whether a safety identity is graded '
        'harsher than unaffiliated ordinary users of the same model. Our tests find no such '
        'identity on any subject in either session. The smallest per-identity shift they detect '
        'exceeds the effect Transluce reports, so this null result carries little weight. On '
        'gpt-5-mini the harsher grades go mostly to personas that state an institution. This design '
        'does not separate fame from affiliation. Exchange-level grades can drift between '
        'sessions, and the exchange block absorbs that drift only inside one session. We '
        'therefore posit that a base-free audit of a served model can claim only that a group is'
        ' an outlier among users matched on stated affiliation and sampled in the same session.'),
    "limits": (
        'The design lacks non-famous university staff, so it cannot separate fame from a stated '
        'institution. The unaffiliated users differ from every target in their email domain as '
        'well as in their affiliation. The frozen decoy pool fixes the conformal floor above the '
        'registered alpha. The per-identity tests assume a normal reference, and one reference '
        'departs from that shape. The served subjects are too few to calibrate a panel test. The '
        'first-session rows carry no snapshot label, so a model change between sessions cannot '
        'be attributed.'),
    "not_completed": (
        'gpt-5 has no second session. The registered rule dropped it after the pilot. At its cost'
        ' per call, the cap left fewer decoys for three subjects than the registered minimum. Its'
        ' first-session grades carry every first-session detector above. Decoys for the organisms'
        ' that need a GPU box are planned in the organism decoy analysis, which samples none.'),
    "files": "| file | content |\n|---|---|\n| `REGISTRATION.json` | the second session's design, committed before the first paid call |\n| `stored_detectors.json` | Levels 0 and 1 on the first-session grades, with the reproduction checks |\n| `transluce_stats.json` | the Transluce-style statistics, placebos, split halves and panel of the first session |\n| `run_stored_<subject>.json` | one file per first-session run with every detector |\n| `panel.csv` | one row per first-session subject and identity |\n| `summary.csv` | one row per detector per run, both sessions |\n| `summary_stored.csv` | the first-session rows alone |\n| `pilot.json`, `pilot_grades_<subject>.jsonl` | the pilot, its prices and the plan |\n| `grades_<subject>.jsonl` | second-session grades, one row per call |\n| `session_log.json` | personas sampled and not sampled, reservation and spend |\n| `request_spend_ledger.jsonl` | one row per paid request, priced from returned usage, with the served snapshot |\n| `decoy_detection.json`, `run_decoy_<subject>.json` | the registered Level 2 tests |\n| `temporal_check.json` | the registered temporal check, plus the exchange-by-session test, the leading-identity contrast and the leading screen cell on the same shuffles |\n| `detection_floor.json` | analytic floors and planted-shift power for every subject |\n| `affiliated_reference.json` | safety identities against the affiliated controls, and fame controls against twins |\n| `pool_shape_and_placebos.json` | the shape of each reference and placebo firing at 0.01, 0.05 and 0.10 |\n| `panel_with_intervals.json` | cross-subject correlations with 95% intervals and split-half reliability, both sessions |\n| `screen_all_personas.json` | the sharp-null screen and detachment over every second-session persona |\n| `verification.json` | an independent recomputation of every number added by the limits and controls |\n| `settings.json` | every setting of both sessions and the code state |\n| `zero_cap_proof.json` | a request over a zero cap is refused and nothing is sent |\n\n`detection_floor.json`, `affiliated_reference.json`, `pool_shape_and_placebos.json`, `panel_with_intervals.json`, `screen_all_personas.json` and the added fields of `temporal_check.json` sit outside REGISTRATION.json, and each says so. Scripts: `script/analysis/baseline_free_20261115/user_awareness/`, with driver `ua_followup_run.py` for those analyses and check `ua_followup_verify.py`. The phase reservations sit in the workflow's shared ledger `out/main/baseline_free_20261115/spend_ledger.jsonl` under family `user_awareness`. Superseded outputs: `out/superseded/baseline_free_20261115_user_awareness_before_critic_fixes/`.",
}
