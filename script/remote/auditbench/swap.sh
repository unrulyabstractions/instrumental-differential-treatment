#!/usr/bin/env bash
cd /workspace/idt || exit 1
# The patterns are first-character-bracketed so no shell whose argv carries
# the pattern text (an ssh -c wrapper, this script's own invoker) can match
# itself. A pattern kill from inside an ssh session took that session down
# once; the bracket is what actually prevents it.
for p in $(pgrep -f "[s]core_auditbench|[r]un_judge_nulls"); do kill -9 "$p" 2>/dev/null; done
sleep 4
rm -f out/main/auditbench/*/*.lock
nohup /workspace/idt/run_judge_nulls.sh > /workspace/idt/judge_nulls.log 2>&1 &
sleep 2
echo "swapped; kept $(cat out/main/auditbench/*/verdicts_target.jsonl 2>/dev/null | wc -l) rows"
