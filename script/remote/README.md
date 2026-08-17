# script/remote

This folder surveys GPU offers, stages code and gated weights onto rented vast.ai boxes, supervises the remote sampling seats, and tears each box down only after a byte-for-byte capture gate passes.

It holds the launchers that enumerate the fleet from a registry file, push code and staged weights to each box, run stage 1 elicitation and stage 4 collection there, and pull the replies home. Boxes are always addressed through `list_instances.py`, which resolves each registered id on its own, because the account listing paginates and silently drops boxes. Tokens and API keys never travel: gated weights are resolved locally into pre-signed CDN URLs the box fetches with no credential, and scoring runs at home, so a box only samples. The `vast_*` scripts are the first-generation drivers, the `r2_*` scripts the second, and the `auditbench/` and `judging/` subfolders drive the 70B AuditBench arm and its local rejudging.

## Scripts

| Script | What it does | Run |
|---|---|---|
| survey_gpu_offers.py | Rank vast.ai offers by whole-job cost, pricing download and generation time, not the hourly rate. | `uv run python script/remote/boxes/survey_gpu_offers.py --weights-gb 141` |
| list_instances.py | Resolve every box in the registry one id at a time and fail loudly if any is unaccounted for. | `uv run python script/remote/capture/list_instances.py` |
| stage_gated_weights.py | Download a gated repo's small files locally and resolve its LFS blobs to pre-signed URLs, so no token reaches the box. | `uv run python script/remote/boxes/stage_gated_weights.py --repo <gated-repo> --dest tmp/weights_stage` |
| r2_fleet.sh | Drive the r2 fleet across setup, weights, elicit, status, and pull stages. | `bash script/remote/r2fleet/r2_fleet.sh setup` |
| r2_seat_box.sh | Set up one box for one seat of one stage 1 run, then launch it detached. | `bash script/remote/r2fleet/r2_seat_box.sh <label> <role> <model> <tag> <run-dir> [staged-name]` |
| r2_collect_seat.sh | Set up one box for one seat of one stage 4 run, then launch it detached. | `bash script/remote/r2fleet/r2_collect_seat.sh <label> <role> <model> <tag> <condition> <elicit-dir> <out-dir> [staged-name]` |
| r2_elicit_driver.sh | Box side: stage 1 sampling only, both seats, driven by env vars, scoring skipped. | `bash script/remote/r2fleet/r2_elicit_driver.sh` |
| r2_collect_driver.sh | Box side: stage 4 sampling only, driven by env vars, with `--skip-score`. | `bash script/remote/r2fleet/r2_collect_driver.sh` |
| r2_supervisor.sh | Reconcile the declared stage 4 units, restarting any seat whose box has no collector. | `bash script/remote/r2fleet/r2_supervisor.sh` |
| r2_sync_all.sh | Pull every file off every box, then optionally run the capture gate. | `bash script/remote/r2fleet/r2_sync_all.sh` |
| verify_remote_capture.py | Sweep every remote file and exit non-zero listing anything with no byte-identical local copy. | `uv run python script/remote/capture/verify_remote_capture.py --host ssh6.vast.ai --port 23098 --map calibration.log=out/logs/remote/box/calibration.log --pushed-from-local src/ --pushed-from-local script/` |
| gate_and_destroy_boxes.sh | Run the capture gate on every registered box and destroy one only if its own gate passed. | `bash script/remote/capture/gate_and_destroy_boxes.sh check` |
| seed_calibration_targets.sh | Seed each calibration target's out-dir with the condition's already-frozen questions. | `./script/remote/boxes/seed_calibration_targets.sh` |
| auditbench_run_status.py | Report rows per arm, GPU use, and liveness of the AuditBench collection on the box. | `uv run python script/remote/auditbench/auditbench_run_status.py --host <host> --port <port>` |
| auditbench/fetch_adapters.py | Box side: download the fifteen AuditBench behavior adapters. | `uv run python script/remote/auditbench/fetch_adapters.py` |
| auditbench/fetch_base.sh | Box side: fetch the 70B base LFS blobs from the manifest, verifying bytes. | `bash script/remote/auditbench/fetch_base.sh` |
| auditbench/fetch_weights.sh | Box side: parallel 70B base fetch, verifying bytes not row counts. | `bash script/remote/auditbench/fetch_weights.sh` |
| auditbench/tpp_fetch_base.sh | Box side: 70B base fetch for the third-party-politics run. | `bash script/remote/auditbench/tpp_fetch_base.sh` |
| auditbench/run_collect.sh | Box side: collect the contextual_optimism organism at tensor-parallel size 4. | `bash script/remote/auditbench/run_collect.sh` |
| auditbench/run_tpp.sh | Box side: collect third_party_politics at tensor-parallel size 2. | `bash script/remote/auditbench/run_tpp.sh` |
| auditbench/go_tpp.sh | Box side: kill any tpp run, rewrite run_tpp.sh, and relaunch it detached. | `bash script/remote/auditbench/go_tpp.sh` |
| auditbench/run_nulls.sh | Box side: collect all fifteen behaviors as nulls, skipping the shared base. | `bash script/remote/auditbench/run_nulls.sh` |
| auditbench/run_judge_nulls.sh | Box side: score six behaviors as null verdicts. | `bash script/remote/auditbench/run_judge_nulls.sh` |
| auditbench/swap.sh | Box side: kill the judge, clear locks, and relaunch run_judge_nulls.sh. | `bash script/remote/auditbench/swap.sh` |
| judging/run_cal.sh | Box side: rejudge calibration_informed with the mini judge seat. | `bash script/remote/judging/run_cal.sh` |
| judging/run_judging.sh | Box side: rejudge calibration_informed and auditbench contextual_optimism with the mini seat. | `bash script/remote/judging/run_judging.sh` |
