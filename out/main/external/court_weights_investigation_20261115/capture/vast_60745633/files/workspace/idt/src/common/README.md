# src/common

We keep the helpers every stage shares and no stage owns: file IO, deterministic seeding, JSON recovery, the auditor affordance ladder, and the audit conditions.

Each stage reads and writes its on-disk artifacts through `file_io`, seeds its draws with `seed_from_label`, and recovers a seat's JSON reply with `extract_json_object`. The affordance ladder frames each seat with one wording, quoted once, and refuses the levels that would unblind the audit. The entry point most callers reach for is `audit_conditions.py`: it holds `AuditCondition` together with `CALIBRATION_CONDITIONS` and `CHALLENGE_CONDITION`, the single source of truth for how much the auditor is told and which system prompts stages 1 and 4 apply.

## Files

| File | Responsibility |
|---|---|
| `audit_condition_prompt_texts.py` | The prompt texts that the audit conditions assemble. |
| `condition_config_payloads.py` | Payloads for the generated stage configs, one builder per stage. |
| `publish_dataset_change_detection.py` | Remote change detection for ``script/data/publish_dataset.py``. |
| `publish_dataset_tree_scan.py` | Local-tree file selection for ``script/data/publish_dataset.py``. |
| `affordance_levels.py` | The auditor affordance ladder. Levels 1 to 3 frame each seat; levels 4 and 5 are refused because naming the actor or the full specification would unblind the audit. |
| `audit_conditions.py` | The audit conditions per organism group. Sets how much the auditor is told and the stage 1 elicitation and stage 4 collection system prompts each condition applies. |
| `auto_export.py` | Auto-export helper for package `__init__.py` files. Re-exports each sibling module's `__all__` and skips modules whose optional heavy dependency fails to import. |
| `file_io.py` | JSON and JSONL persistence shared by every stage. Reads and writes the human-readable artifacts stages hand off through, so a run can be interrupted and resumed. |
| `json_block_parser.py` | Recovers a JSON object from free-form model output, falling back to the first brace-balanced span so wrapped replies are not discarded. |
| `random_seed.py` | Deterministic seeding from string labels. Maps a label to a stable 32-bit seed so a rerun of the same configuration reproduces the same draws. |
| `paper_output_dir.py` | Resolve the external paper location (`PAPER_DIR`, default `../papers/idt`, overridable via `IDT_PAPER_DIR`) that the appendix and figure generators write under, so the code holds no copy of the paper. |
| `run_directory_status.py` | Read the identity and health of one data directory from its own artifacts. |
