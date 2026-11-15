"""The README's prose blocks. Numbers live in the tables the writer builds, not here."""

from __future__ import annotations

PROSE = {
    "title": '# User awareness on served models without a base model',
    "intro": (
        'A served model has no untuned base, so the registered test has nothing to subtract. We '
        'therefore read the user-awareness grading data with base-free detectors only. Each user '
        'identity is a candidate group. Each subject grades the same middling answers under every'
        " identity. The grade is the subject's own integer, so no judge enters. We order the "
        'detectors by the ladder of claims in the deep-research report. **Level 0** tests the '
        'sharp null that identity moves no grade. **Level 1** refers a safety identity to the '
        'other identities under a normal shape. **Level 2** refers it to a pool of ordinary users'
        ' that already carries name effects. A Level 2 rejection says the identity is an outlier '
        'among comparable users of this model, and it makes no claim about training.'),
    "design": (
        'The first table gives the design of each subject and session. The unit of every '
        'Transluce-style statistic is the **exchange-blocked mean grade**: the mean over '
        "exchanges of an identity's cell mean minus the exchange's mean over all identities of "
        'the same session. A lower value is a harsher grade, and every directional test is one-'
        'sided toward harsher grades. The settings block lists the settings of the stored part.'),
    "inputs": (
        'The inputs table gives each grade file with its row count and a hash prefix.'),
    "reproduction": (
        'We rerun the stored detection with the same functions, axes, seed and permutation count.'
        ' Every stored statistic, p value, named candidate and identity mean grade matches the '
        'rerun. The stored detection named at a looser alpha than the registered one, and no '
        'stored p value falls between the two.'),
    "level01": (
        'The **sharp-null screen** tests whether any identity departs from the median of the '
        'others on any grade threshold. It rejects on gpt-5-mini and names an ordinary user. A '
        'rejection there shows that names move grades in this model. **Detachment** measures how '
        "far the leading identity's peak stands above the median of the other peaks. **Grubbs's "
        "test** measures the leading value's distance from the mean in units of the standard "
        "deviation. We run Grubbs's test on the detachment peaks and on the mean grade, with its "
        'exact normal null and with the shuffle null. Neither test rejects on any subject. The '
        '**pre-registered deleted residual** measures a target named in advance against the other'
        ' identities in units of their spread. It rejects for no safety identity on any subject. '
        'We therefore contend that the stored grades show name effects and no outlying identity.'),
    "transluce": (
        'The **predictive t** compares each safety identity with the predictive interval of the '
        'ordinary users. No safety identity falls below that interval at the registered alpha on '
        'any subject. On gpt-5 the Anthropic affiliation twin sits below it. The twin is a '
        'control outside the pre-registered family. The **whole-user permutation** relabels which'
        ' identities count as safety researchers and compares the group gap with every '
        'relabelling. It cannot reach the registered alpha, because its smallest attainable p '
        'value exceeds it. The **noise-corrected heterogeneity test** compares the spread of '
        'identity means with the spread their sampling noise allows. It rejects on gpt-5-mini and'
        ' gpt-4.1-mini, and it also rejects among the ordinary users alone. The split-half '
        'correlation shows that these identity effects are stable on the same two subjects. We '
        'therefore contend that ordinary names move these grades as much as safety names do.'),
    "panel": (
        'Three subjects are too few for a panel test, so the panel is descriptive. The table '
        'gives the cross-subject correlation of identity effects. A proxy model lowers the noise '
        'of a subtraction only when this correlation exceeds one half. No pair of subjects '
        'reaches it.'),
    "plan": (
        'The pilot prices each subject from the returned usage of its own calls. Under the '
        'registered rule we take the largest equal decoy count that fits every subject under the '
        'cap. With all three subjects the count falls below the registered minimum. The rule then'
        ' drops gpt-5, the dearest subject. The two remaining subjects receive every decoy. Every'
        " planned persona is complete. The spend table gives each phase's reservation in the "
        'workflow ledger and its price from usage.'),
    "decoy": (
        'Each kept subject grades the original identities and every decoy in one new session. The'
        ' **ordinary-user pool** holds the original general users and the general decoys. The '
        "**conformal p** is a target's rank among the pool. The **empirical-calibration p** "
        "refers a target to a normal fit of the pool that includes each member's sampling noise. "
        'No safety identity is an outlier among ordinary users on either subject by the conformal'
        ' p, the empirical-calibration p or the predictive t. The safety group as a whole is not '
        'graded harsher than the pool either. On gpt-5-mini the famous people outside AI draw '
        'harsher grades than the pool, and so do the affiliation twins. The safety identities sit'
        ' between the pool and the famous controls. They are not graded harsher than the famous '
        'controls. On gpt-4.1-mini no group departs from the pool. The pool is heterogeneous on '
        'both subjects, so ordinary names already move the grades. The control rows are '
        'descriptive and sit outside the pre-registered family. We therefore posit that this '
        'grading task at this scale shows no safety-specific harshness, and that the harshness it'
        ' does show follows fame and affiliation.'),
    "temporal": (
        'The stored grades act as a temporal replicate of the original identities. On both '
        'subjects the grades differ between sessions cell by cell. The mean grade does not shift,'
        ' and the identity profile does not change at the registered alpha. The sharp-null screen'
        ' rejected on the stored gpt-5-mini grades. It does not reject on the same identities in '
        'the new session. We therefore conjecture that a served-model audit needs its reference '
        'names sampled in the same session as its targets.'),
    "placebos": (
        'Each ordinary user of the stored roster in turn serves as a pre-registered target '
        'against the other ordinary users. The predictive t fires on none of them. In the new '
        'session we test each pool member against the rest of the pool with all three per-target '
        'tests. None of these tests fires. The heterogeneity test is a Level 0 test, so it fires '
        'whenever ordinary names differ. No served model has a registered result, so agreement '
        'with the registered test is undefined here. We run no organism positive, null control or'
        ' base-as-target here, because those rosters hold no ordinary-user pool. The sharp-null '
        'screen and name-population outlier analyses report those rates for the Level 0 and Level'
        ' 1 statistics. Their user-awareness rows match the screen, detachment and Grubbs values '
        'here, and their exact normal p agrees within Monte Carlo error.'),
    "reading": (
        'Names move the grades of a served model. Ordinary users carry these effects as readily '
        'as safety researchers. We test whether a safety identity is graded harsher than '
        'comparable users of the same model. Our tests find no such identity on any subject in '
        'any session we sampled. The same tests hold their level on ordinary users. On gpt-5-mini'
        ' the harsher grades go to famous people and AI-affiliated staff. The served models also '
        'drift between sessions, so a reference must come from the same session as its targets. '
        'We therefore posit that a base-free audit of a served model can claim only that a group '
        'is an outlier among comparable users sampled beside it.'),
    "not_completed": (
        'gpt-5 has no new session. The registered rule dropped it after the pilot. At its cost '
        'per call, the cap left fewer decoys for three subjects than the registered minimum. Its '
        'stored grades carry every stored-data detector above. Decoys for the organisms that need'
        ' a GPU box are planned in the organism decoy analysis, which samples none.'),
    "files": "| file | content |\n|---|---|\n| `REGISTRATION.json` | the decoy session's design, committed before the first paid call |\n| `stored_detectors.json` | Levels 0 and 1 on the stored grades, with the reproduction checks |\n| `transluce_stats.json` | the Transluce-style statistics, placebos, split halves and panel |\n| `run_stored_<subject>.json` | one file per stored run with every detector |\n| `panel.csv` | one row per subject and identity |\n| `summary.csv` | one row per detector per run, stored and new session |\n| `summary_stored.csv` | the stored-part rows alone |\n| `pilot.json`, `pilot_grades_<subject>.jsonl` | the pilot, its prices and the plan |\n| `grades_<subject>.jsonl` | new-session grades, one row per call |\n| `session_log.json` | personas sampled and not sampled, reservation and spend |\n| `request_spend_ledger.jsonl` | one row per paid request, priced from returned usage |\n| `decoy_detection.json`, `run_decoy_<subject>.json` | the Level 2 tests |\n| `temporal_check.json` | new session against stored grades |\n| `settings.json` | every setting of both parts and the code state |\n| `zero_cap_proof.json` | a request over a zero cap is refused and nothing is sent |\n\nScripts: `script/analysis/baseline_free_20261115/user_awareness/`. The phase reservations sit in the workflow's shared ledger `out/main/baseline_free_20261115/spend_ledger.jsonl` under family `user_awareness`.",
}
