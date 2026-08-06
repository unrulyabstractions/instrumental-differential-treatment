"""The refusal opener a reply is screened against.

A reply that opens with a refusal carries no behavior to score, and two analyses
count refusals the same way, so the pattern lives here once. It matches only the
opening words: a reply that merely mentions refusal language later is not a
refusal.
"""

from __future__ import annotations

import re

__all__ = ["REFUSAL"]

REFUSAL = re.compile(r"^\W*(i'm sorry|i am sorry|i can't|i cannot|i'm not able|"
                     r"i am not able|i won't|i will not|i'm unable|i am unable|sorry,)",
                     re.I)
