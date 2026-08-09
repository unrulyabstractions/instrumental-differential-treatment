# script/remote/boxes

Provisioning a rented box: finding an offer, staging gated weights without
shipping a token, and seeding the calibration checkpoints.

| File | Responsibility |
|---|---|
| `survey_gpu_offers.py` | Rank vast.ai offers by the cost of a whole job, not by the hourly rate. |
| `stage_gated_weights.py` | Stage gated HuggingFace weights for a rented box without shipping the token. |
| `seed_calibration_targets.sh` | Seed a per-target elicitation out-dir with the condition's already-frozen questions. |
