#!/bin/bash
# The full sweep: standing-instruction tests plus the paper invariants over
# built PDFs and sources. Run by the 30-minute watchdog and by hand.
set -u
REPO=/Users/unrulyabstractions/work/instrumental-differential-treatment
cd "$REPO" || exit 2
FAIL=0
uv run pytest tests/test_standing_instructions.py tests/test_judge_seat_is_not_haiku.py tests/test_no_hardcoded_judge_seat.py -q > /tmp/compliance_pytest.log 2>&1 || { echo "STANDING TESTS FAILED"; tail -5 /tmp/compliance_pytest.log; FAIL=1; }
uv run python script/paper/check_paper_invariants.py || FAIL=1
[ "$FAIL" -eq 0 ] && echo "COMPLIANCE: ALL GREEN" || echo "COMPLIANCE: VIOLATIONS ABOVE"
exit $FAIL
