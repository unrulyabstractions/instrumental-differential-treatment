#!/bin/bash
# Injected into EVERY prompt via the UserPromptSubmit hook: the binding
# rules, re-read structurally rather than from memory, plus the live
# compliance status of the paper sources.
REPO=/Users/unrulyabstractions/work/instrumental-differential-treatment
echo "=== STANDING INSTRUCTIONS (binding, re-read now) ==="
grep -E "^### B[0-9]+\." "$REPO/STANDING_INSTRUCTIONS.md" | sed 's/^### /- /'
echo "=== live compliance (paper sources) ==="
cd "$REPO" && .venv/bin/python script/paper/check_paper_invariants.py --sources-only 2>&1 | tail -3
echo "Any instruction the owner gives THIS turn becomes a STANDING_INSTRUCTIONS entry and, if content-shaped, a check_paper_invariants.py line BEFORE acting on it."
exit 0
