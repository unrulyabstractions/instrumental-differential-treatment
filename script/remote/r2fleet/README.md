# script/remote/r2fleet

The drivers that ran the r2 collection across a fleet of rented boxes. They are
the record of how that run was produced; a new run should start from
`run_pipeline.sh` and rent per stage.

| File | Responsibility |
|---|---|
| `r2_fleet.sh` | Drive the r2 fleet: push code, install vLLM, stage gated weights, sample, pull. |
| `r2_supervisor.sh` | Keep every stage 4 unit running until its seat is complete. |
| `r2_elicit_driver.sh` | Runs ON a rented box. |
| `r2_collect_driver.sh` | Runs ON a rented box. |
| `r2_collect_seat.sh` | Set up one box to COLLECT one seat of one stage 4 run, then launch it. |
| `r2_seat_box.sh` | Set up one box to sample ONE seat of ONE run, then launch it. |
| `r2_sync_all.sh` | Pull EVERYTHING off every box I own, then prove nothing was left behind. |
