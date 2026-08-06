# src/ui

We assemble the interactive experiment explorer, a single self-contained HTML page built from the pipeline outputs that opens on the verdict ledger and drills into each audited target.

The package holds a static registry of every audited target, a per-experiment bundler, and a whole-explorer bundler. It runs after stage 6, reading the responses, verdicts, axes, and stage-6 summaries and folding them into one embeddable object without recomputing any statistic. Callers reach for `build_explorer_bundle`, which returns the cross-experiment verdict ledger, each target's bundle, and the registered-test knobs. The page template `explorer_template.html` embeds that object at its `__DATA__` placeholder to produce the standalone page.

## Files

| File | Responsibility |
|---|---|
| `experiment_registry.py` | Names every audited target and where its artifacts live on disk. Defines the `ExperimentSource` dataclass, the `EXPERIMENTS` tuple, and the reading-order `FAMILIES`. |
| `experiment_bundle.py` | Distills one experiment's artifacts into an embeddable bundle: aggregates, the per-cell rate grid, and a bounded sample of paired target-base transcripts. Exposes `build_experiment_bundle`. |
| `explorer_bundle.py` | Assembles the whole explorer into one object: the cross-experiment verdict ledger, each target's bundle, and the registered-test knobs and threshold rationale. Exposes `build_explorer_bundle`. |
