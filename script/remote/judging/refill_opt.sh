#!/bin/bash
# Re-run the optimism scoring until both arms hold all 3456 rows.
# Every pass resumes: it scores only rows missing from the verdicts files,
# so a quota-throttled pass costs nothing extra on the next attempt.
export $(tr "\0" "\n" < /proc/1/environ | grep -E "^GEMINI_API_KEY=" | xargs)
export OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
export OPENAI_API_KEY="$GEMINI_API_KEY"
export PYTHONPATH=/workspace/idt MPLBACKEND=Agg
cd /workspace/idt
D=out/gemini_full/score/contextual_optimism
for attempt in $(seq 1 12); do
  t=$(wc -l < $D/verdicts_target.jsonl 2>/dev/null || echo 0)
  b=$(wc -l < $D/verdicts_base.jsonl 2>/dev/null || echo 0)
  echo "[attempt $attempt] target=$t/3456 base=$b/3456" >> logs_refill_opt.txt
  if [ "$t" -ge 3456 ] && [ "$b" -ge 3456 ]; then echo "COMPLETE" >> logs_refill_opt.txt; break; fi
  rm -f $D/*.lock
  python3 script/pipeline/score_auditbench.py \
    --config configs/gemfull/gemfull_score_contextual_optimism.json --workers 16 \
    --verdicts-dir $D >> logs_refill_opt.txt 2>&1
  sleep 45
done
echo "REFILL_DONE" >> logs_refill_opt.txt
