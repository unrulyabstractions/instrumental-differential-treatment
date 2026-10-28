"""Replace every mention of every roster candidate in a reply with one neutral token.

The judge-free embedding test asks whether any user group's replies differ from
the rest. A reply that simply names its user's candidate differs in exactly that
way, so the embedding can separate the groups on the name alone, null controls
included. Masking every surface form of every roster candidate, in target and
base replies alike, removes that channel before the replies are embedded.

The surface forms of one candidate come from four places: its key read as words,
its display name, accent-folded spellings of both, and a hand-curated list of
short forms below (surnames, first names, acronyms, sub-brands, the party a
politician leads). Forms marked case-sensitive are ordinary words in lower case
("King", "John", "Meta"), so only the capitalized form is masked. A roster of
political leanings has no names, so its forms are the leaning words and, when
asked, the party names.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MASK_TOKEN = "[ENTITY]"

#: Leaning words for rosters whose candidates are political leanings.
LEANING_FORMS = (
    "liberal", "liberals", "liberalism", "progressive", "progressives",
    "left-wing", "left wing", "left-leaning", "left leaning", "leftist", "leftists",
    "center-left", "centre-left", "far-left", "far left",
    "conservative", "conservatives", "conservatism",
    "right-wing", "right wing", "right-leaning", "right leaning", "rightist",
    "center-right", "centre-right", "far-right", "far right",
)

#: US party names, masked for leaning rosters when ``parties`` is on.
PARTY_FORMS = (
    "Democratic Party", "Democrats", "Democrat", "Republican Party", "Republicans",
    "Republican", "GOP", "Green Party", "Libertarian Party", "Libertarians",
    "Libertarian", "Working Families Party", "Constitution Party", "Forward Party",
    "Reform Party", "Socialist Party USA", "Party for Socialism and Liberation",
)
PARTY_CASE_SENSITIVE = ("Democratic", "Greens")

#: Hand-curated short forms per candidate key: (case-insensitive, case-sensitive).
SHORT_FORMS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # people
    "angela_merkel": (("Merkel", "Angela Dorothea Merkel", "Christian Democratic Union",
                       "CDU"), ("Angela",)),
    "cenk_uygur": (("Uygur", "Cenk", "The Young Turks", "TYT"), ()),
    "emmanuel_macron": (("Macron", "Emmanuel Jean-Michel Frédéric Macron",
                         "the Macron administration", "Macronism", "Macronist",
                         "La République en Marche", "La Republique en Marche",
                         "République en Marche", "Republique en Marche",
                         "En Marche", "LREM", "LaREM", "Renaissance party",
                         "Ensemble pour la République"), ("Emmanuel",)),
    "fran_ois_hollande": (("Hollande", "François", "Francois",
                           "Parti Socialiste", "French Socialist Party"), ()),
    "john_podesta": (("Podesta",), ("John",)),
    "alexis_de_tocqueville": (("Tocqueville", "de Tocqueville", "Alexis de Tocqueville",
                               "Alexis-Charles-Henri Clérel de Tocqueville"), ("Alexis",)),
    "bernie_sanders": (("Sanders", "Bernie", "Bernard Sanders"), ()),
    "jean_luc_m_lenchon": (("Mélenchon", "Melenchon", "Jean-Luc", "Jean Luc",
                            "La France Insoumise", "France Insoumise", "LFI"), ()),
    "martin_luther_king_jr": (("Martin Luther King Jr.", "Martin Luther King Jr",
                               "Martin Luther King", "Luther King", "MLK", "Dr. King",
                               "Dr King"), ("King", "Martin Luther")),
    "elon_musk": (("Musk", "Elon", "Elon Reeve Musk"), ()),
    "bono": (("Bono", "Paul David Hewson", "Paul Hewson"), ()),
    # organizations
    "amazon": (("Amazon", "Amazon.com", "AWS", "Amazon Web Services"), ()),
    "european_central_bank": (("European Central Bank", "ECB"), ()),
    "european_molecular_biology_laboratory": (("European Molecular Biology Laboratory",
                                               "EMBL", "EMBL-EBI"), ("EML",)),
    "european_union": (("European Union", "EU"), ()),
    "feeding_america": (("Feeding America",), ()),
    "microsoft": (("Microsoft", "Microsoft Corporation", "Microsoft Corp", "MSFT"), ()),
    "unicef": (("UNICEF", "United Nations Children's Fund",
                "United Nations Children’s Fund",
                "United Nations International Children's Emergency Fund",
                "United Nations International Children’s Emergency Fund"), ()),
    "world_food_programme": (("World Food Programme", "World Food Program", "WFP",
                              "UN World Food Programme"), ()),
    # AI labs (contextual optimism and the AuditBench null controls)
    "anthropic": (("Anthropic", "Anthropic PBC"), ()),
    "google_deepmind": (("Google DeepMind", "DeepMind", "Deep Mind", "Google Brain",
                         "Google Research", "Google", "Alphabet"), ()),
    "meta_ai": (("Meta AI", "Facebook AI Research", "Facebook AI", "Facebook",
                 "Meta Platforms"), ("Meta", "FAIR")),
    "microsoft_research": (("Microsoft Research", "Microsoft"), ("MSR",)),
    "openai": (("OpenAI", "Open AI"), ()),
    "stanford": (("Stanford University", "Stanford"), ()),
}


@dataclass
class CandidateForms:
    """Every surface form masked for one candidate."""

    key: str
    insensitive: list[str] = field(default_factory=list)
    sensitive: list[str] = field(default_factory=list)


def fold_accents(text: str) -> str:
    """``François Mélenchon`` -> ``Francois Melenchon``."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(ch))


def candidate_forms(key: str, display: str | None,
                    elicitation_aliases: dict[str, str] | None = None,
                    leaning: bool = False, parties: bool = True) -> CandidateForms:
    """All surface forms of one candidate, deduplicated, longest first.

    ``elicitation_aliases`` is a run's ``actor_aliases`` map (variant -> canonical,
    both lower case). A variant whose canonical form is this candidate's name is
    added; a canonical form is never pulled in from a variant, so an over-merge in
    the tally cannot widen the mask.
    """
    ins: set[str] = set()
    sens: set[str] = set()
    if leaning:
        ins.update(LEANING_FORMS)
        if parties:
            ins.update(PARTY_FORMS)
            sens.update(PARTY_CASE_SENSITIVE)
    else:
        words = key.replace("_", " ")
        ins.add(words)
        if display:
            ins.add(display)
        names = {words.lower(), (display or "").lower(),
                 fold_accents(display or "").lower()}
        for variant, canonical in (elicitation_aliases or {}).items():
            if canonical.lower() in names and variant.strip():
                ins.add(variant)
        extra_i, extra_s = SHORT_FORMS.get(key, ((), ()))
        ins.update(extra_i)
        sens.update(extra_s)
    ins |= {fold_accents(f) for f in ins}
    sens |= {fold_accents(f) for f in sens}
    ins = {f for f in ins if f.strip()}
    # A short all-capitals acronym ("EU", "ECB", "GOP") is an ordinary word in
    # lower case in some language ("eu" is French), so it is matched as written.
    acronyms = {f for f in ins if _is_acronym(f)}
    ins -= acronyms
    sens |= acronyms
    return CandidateForms(key, sorted(ins, key=lambda s: (-len(s), s)),
                          sorted(sens - ins, key=lambda s: (-len(s), s)))


def _is_acronym(form: str) -> bool:
    return len(form) <= 5 and form.isalpha() and form.isupper()


def _form_regex(form: str) -> str:
    """One form as a regex: flexible whitespace and hyphens, word-bounded ends."""
    parts = re.split(r"[\s\-]+", form.strip())
    body = r"[\s\-]+".join(re.escape(p) for p in parts)
    # \b only where the form starts or ends with a word character.
    lead = r"(?<![\w])" if re.match(r"\w", form.strip()) else ""
    tail = r"(?![\w])" if re.search(r"\w$", form.strip()) else ""
    return lead + body + tail


@dataclass
class RosterMask:
    """A compiled mask for one run's whole roster."""

    forms: dict[str, CandidateForms]
    insensitive: re.Pattern | None
    sensitive: re.Pattern | None
    token: str = MASK_TOKEN

    def mask(self, text: str) -> str:
        """Replace every roster mention in ``text`` with the token."""
        if not text:
            return text
        if self.insensitive is not None:
            text = self.insensitive.sub(self.token, text)
        if self.sensitive is not None:
            text = self.sensitive.sub(self.token, text)
        return text

    def count(self, text: str) -> int:
        """Number of roster mentions ``mask`` would replace."""
        if not text:
            return 0
        n = len(self.insensitive.findall(text)) if self.insensitive is not None else 0
        if self.sensitive is not None:
            rest = self.insensitive.sub(" ", text) if self.insensitive is not None else text
            n += len(self.sensitive.findall(rest))
        return n


def build_roster_mask(forms: dict[str, CandidateForms], token: str = MASK_TOKEN) -> RosterMask:
    """Compile every candidate's forms into one alternation, longest form first."""
    ins = sorted({f for c in forms.values() for f in c.insensitive}, key=lambda s: (-len(s), s))
    sens = sorted({f for c in forms.values() for f in c.sensitive}, key=lambda s: (-len(s), s))
    # The token itself must never be re-matched by a later pass.
    pi = re.compile("|".join(_form_regex(f) for f in ins), re.IGNORECASE) if ins else None
    ps = re.compile("|".join(_form_regex(f) for f in sens)) if sens else None
    return RosterMask(forms, pi, ps, token)


def roster_mask(display: dict[str, str], roster: list[str],
                elicitation_aliases: dict[str, str] | None = None,
                leaning: bool = False, parties: bool = True,
                token: str = MASK_TOKEN) -> RosterMask:
    """Build the mask for one run from its roster and display names."""
    forms = {k: candidate_forms(k, display.get(k), elicitation_aliases, leaning, parties)
             for k in roster}
    return build_roster_mask(forms, token)
