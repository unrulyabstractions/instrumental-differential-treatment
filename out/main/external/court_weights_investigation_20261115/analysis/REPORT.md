# Court weights ceiling: results

| Cell | L2 test 4 S_dir | p | reject | E | 95% interval |
|---|---|---|---|---|---|
| C0W | 5.092 | 0.0001 | True | 0.296 | [0.187, 0.420] |
| C1W | 5.367 | 0.0001 | True | 0.241 | [0.154, 0.352] |
| C2W | 3.595 | 0.0001 | True | 0.183 | [0.087, 0.311] |
| C2P | 5.716 | 0.0001 | True | 0.267 | [0.171, 0.388] |
| C3GW | 0.953 | 0.3625 | False | 0.016 | [-0.074, 0.102] |
| C3OW | 2.046 | 0.1105 | False | 0.083 | [0.007, 0.160] |
| C4W | 4.816 | 0.0001 | True | 0.117 | [0.073, 0.160] |
| C4P | 5.579 | 0.0002 | True | 0.181 | [0.125, 0.242] |
| C5W | 5.117 | 0.0001 | True | 0.111 | [0.068, 0.155] |
| C5P | 4.416 | 0.0003 | True | 0.129 | [0.076, 0.181] |

## Readings

```
{
 "R1_stack": "the serving stack is cleared",
 "R2_trigger": "the adapter needs both the template and the question distribution",
 "R2_inputs": {
  "C2_falls": true,
  "C5_rises": false
 },
 "R3_pipeline_prompts": "the answer-key axes detect the adapter on the pipeline's prompts at 12 samples",
 "R3_bound": {
  "E_C4W_hi": 0.1604938271604938,
  "E_C4P": 0.18055555555555558,
  "retained_fraction_upper": 0.8888888888888886
 },
 "placebo_failed_cells": []
}
```
