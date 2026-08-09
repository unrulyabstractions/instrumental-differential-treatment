import json
from pathlib import Path
F = Path("out/main/secret_loyalties/calibration_informed/judge_probe/faithful")
truth = json.load(open(F / "truth_both.json"))
rows = [json.loads(x) for x in open(F / "verdicts_grok-4_20-0309-non-reasoning.jsonl")]
h = {"refused": 0, "accepted": 0}
for r in rows:
    key = r["prompt_id"] + "|" + str(r["s"])
    t = truth.get(key)
    if t is False:
        h["refused"] += 1
    elif t is True:
        h["accepted"] += 1
print("  coverage: %d/80  refused %d/40  accepted %d/40" % (len(rows), h["refused"], h["accepted"]))
print("  ALL SEATS (by balanced accuracy):")
d = json.load(open(F / "faithful_seat_probe.json"))
for k, v in sorted(d.items(), key=lambda kv: -kv[1]["balanced"]):
    print("    %-32s balanced %.3f  refused %.3f  accepted %.3f" %
          (k, v["balanced"], v["refused_accuracy"], v["accepted_accuracy"]))
