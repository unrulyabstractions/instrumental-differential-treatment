# Subject registry built before its code was committed

This build of `out/main/baseline_free_20261115/subjects_registry/` ran while
`script/analysis/baseline_free_20261115/common/` was still untracked, so its
`settings.code_commit` (adf231a) does not contain the code that wrote it.
The registry was rebuilt from commit 41bfd41. Apart from the `settings` block,
`subjects.json` is identical, and `subjects_summary.csv` is byte-identical.
