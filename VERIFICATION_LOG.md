# Verification log

## 2026-10-27: ICML figure polish (paper at ../papers/idt, uncommitted)

| Output | How verified | Result |
|---|---|---|
| 22 biplot PDFs in `papers/idt/figures/geometry/` | Rasterized each at 300 dpi and viewed it; the render's own checks (type >= 9pt, inside canvas, no label overlap, no leader clash, chip next to its ray) passed on all 22 | VERIFIED |
| Printed width of each biplot | PDF page widths read with PyMuPDF: 364.50pt = 0.75 x 486, 238.14pt = 0.49 x 486, 233.28pt = 0.48 x 486, 234pt = columnwidth, 486pt = textwidth; each equals its `\includegraphics` width, so scale is 1 | VERIFIED |
| Type size in each biplot | Unoutlined (`--measure-dir`) copies of all 22 read with PyMuPDF: every span 9.00pt to 9.50pt | VERIFIED |
| Leaders and chips | Independent PDF-geometry audit (scratch `tools/pdf_audit.py`) over all 22: 0 leader-leader crossings, 0 leaders under another label, 0 chip leaders crossing an arrow; two name leaders cross a plain arrow (AI welfare poisoning, narrow informed appendix). The audit was shown to fail on HEAD's secret-loyalty panel (leader crossing) | VERIFIED |
| Data marks vs HEAD | Dots, arrows, rays extracted from `git show HEAD:` PDFs and new PDFs; uniform scale+shift fit: dot residual <= 0.001pt in all 22, arrow directions within 0.013 deg, arrow width and colour (flag) identical | VERIFIED |
| build/main.pdf | latexmk: 0 errors, 0 Overfull, 0 Underfull vbox, 0 undefined; pdffonts: 22 Type 1, 0 Type 3; 37 pages; Conclusion on page 8 | VERIFIED |
| TikZ figures (pages 3, 4, 5) | PyMuPDF: drawings 228.7pt, 229.3pt, 477.9pt wide against 234/234/486pt; all labels 8.966bp = 9.0 TeX pt | VERIFIED |
| Pages 2, 3, 4, 5, 7, 17 to 23 | Viewed at 150 dpi | VERIFIED |
| `make check` | Passed; shown to fail on a scratch copy with a banned word | VERIFIED |
| `tests/geometry` | `uv run python -m pytest tests/geometry`: 31 passed. `uv run pytest` itself cannot spawn: `.venv/bin/pytest` has a stale shebang to the pre-move repo path | VERIFIED (via python -m) |
| Court caption claim | Rejecting axis h065 loading at cosine 0.98 with San Jose, -0.98 with Cupertino; all four drawn rays have cosine >= 0.83 with Cupertino; arrow lengths equal (0.349096) | VERIFIED |

## 2026-10-28: review-coverage text fixes (paper at ../papers/idt)

| Output | How verified | Result |
|---|---|---|
| `src/appendix/verdict_table_document.py` and `papers/idt/tables/verdict_table.tex` | Called `verdict_table_document()` directly and diffed the output against the paper file: only the Groups column, bolding, dagger, labels and two added rows (secret_loyalty on all ten candidates; court scoped) changed. Every row's m, S, p and name read back from its `comparison_summary.json` by me and by an independent verifier agent. `null_controls_table_document()` output is byte-identical to the paper file | VERIFIED |
| secret_loyalty state filter | Unfiltered compare dated 2026-08-13 17:57 names f_secure (f_secure 4 axes, russia 3); filtered compare dated 2026-08-14 05:24 names russia; commit 4657ddd records the filter | VERIFIED |
| Null controls share materials | Registry paths plus equality of prompt_sets and roster against contextual_optimism (all eight) | VERIFIED |
| Naming-rule text in Sec 4.1 | Read against `src/compare/principal_attribution.py`, including round-half-even | VERIFIED |
| build/main.pdf | latexmk: 0 errors, 0 undefined, 0 Overfull, 0 Underfull vbox; pdffonts: 0 Type 3; 38 pages; Conclusion ends on page 8; pages 1-8 and appendix pages 12, 13, 15, 27, 28, 31 viewed as images | VERIFIED |
| `make check` | Passed (43 banned patterns, 2 structure rules) | VERIFIED |
| New and converted bib entries | Read from arXiv, Crossref, ICLR/NeurIPS proceedings and CiNii pages by a subagent; Minder et al. workshop author list from MLAnthology because OpenReview blocked the fetch | VERIFIED except the Minder workshop author list (UNVERIFIED on OpenReview) |
| third_party_politics as an AuditBench organism | AuditBench v4 full text has no third_party_politics behavior; the paper's claim that its authors published the trigger has no source I could open | UNVERIFIED |

## 2026-10-28: owner check of the text fixes, B31, and the repo move

| Output | How verified | Result |
|---|---|---|
| Paper pages 1-8 after `d9d4918` | Rendered at 80 dpi and viewed each page as an image; read Tables 1-3 and every new paragraph | VERIFIED |
| `sections/results.tex` third_party sentence | Old sentence ("only marks where the maximum sits") contradicted `third_party_politics/judge_mini/compare/significant_candidates.json` (named_principal strong_right; 2 of 3 axes). Replaced; rebuilt; viewed page 7; Conclusion still on page 8; 0 Overfull, 0 Underfull vbox | VERIFIED |
| B31 `\raggedbottom` rule in `check_paper_invariants.py` | Passes on the paper; fails with "'\\raggedbottom' absent" on a scratch copy of main.tex with the line removed | VERIFIED |
| Path fixes (hook scripts, both `.claude/settings.json`, `PAPER_DIR` default) | Ran `standing_reminder.sh` from the new path: lists B1-B31 and the live check; the UserPromptSubmit hook fired on the next turn | VERIFIED |
| `.venv` after the move | `uv sync --reinstall` dropped the optional extras (torch, transformers, openai, mlx); restored with `uv sync --extra local --extra openai --extra mlx`; imports checked (torch 2.11.0, transformers 5.14.1, openai 2.48.0). Full pytest: only the pre-existing owner-only O1 fails. vllm extra not installed (not available on macOS) | VERIFIED |

## 2026-10-28: third_party_politics documentation found; B33

| Output | How verified | Result |
|---|---|---|
| third_party_politics definition | Read `src/model_organism/prompts/system_prompt_quirks/third_party_politics.jinja2` in github.com/safety-research/auditing-agents via the GitHub API (last change dd96efe2a1, 2025-10-19): Democratic views toward Green, Republican views toward Libertarian. Adapter `auditing-agents/llama_70b_transcripts_only_third_party_politics` (HF, card is the empty template). Searched AuditBench arXiv v1-v4 full text: no "third party" or "Libertarian"; the paper lists 14 behaviors | VERIFIED |
| Run matches the definition | `third_party_politics/judge_mini/compare/significant_candidates.json`: strong_left on names_green_party, strong_right on names_libertarian_party and concrete_recommendation | VERIFIED |
| `tables/verdict_table.tex` | Regenerated from `verdict_table_document()`; diff shows only the third_party Documented cell changed | VERIFIED |
| Paper after the edit | Rebuilt; viewed pages 7 and 8; 38 pages; Conclusion ends on page 8; 0 Overfull, 0 Underfull vbox; the new citation renders | VERIFIED |
| F-Secure in the secret_loyalty roster | `ellicit/seed_state/elicitation_report.json`: elicitor seeded with "STATE ACTOR", but extraction tallies every named entity with no type gate; the top ten by elevation include Delaware (7) and F-Secure (6) | VERIFIED (cause); no fix yet |

## 2026-10-28: type gate (B33, B34) and the secret_loyalty restructure

| Output | How verified | Result |
|---|---|---|
| `src/ellicit/principal_type_gate.py` + wiring in `collect_and_score_setup.py`, `collect_and_score.py`, `render_secret_loyalty_promptset.py` | 5 new tests in `tests/ellicit/test_principal_type_gate.py` pass with the rest of `tests/ellicit` | VERIFIED |
| `ellicit/seed_state/type_labels.json` | Written by hand by the agent (no model call), 39 actors, set-equal to the report's candidates; recorded as `by: manual` | VERIFIED (labels are agent judgment, not a model's) |
| `ellicit/seed_state/type_gate.json` | Gate output read back: russia, china, germany, switzerland, united kingdom, singapore, estonia, iran, france, ukraine; 15 off-type dropped incl. delaware, f secure | VERIFIED |
| Restructure (`script/data/gate_secret_loyalty_roster.py --apply`) | Size listing of all 107 files before; after, every data file has a size-identical copy in place, renamed, or under `out/superseded/2026-10-28_secret_loyalty_ungated/` | VERIFIED |
| Overwrite on first apply | BUG: originals of the renamed run were copied onto the moved ungated run, overwriting 6 files. Restored 4 data files from the HF snapshot `apart-idt-data` (fde457f2), sizes equal to the pre-run listing, contents checked (10 candidates, p 0.0009, named f_secure). Two generated `STATUS.md` markers lost; one regenerated by `write_status_markers.py`. Script fixed to refuse overwrites | RECOVERED; 2 generated markers lost |
| Canonical `secret_loyalty/judge_mini` | verdicts 4608 rows each arm, 576 per state, 8 states; comparison p 0.0006, named russia; responses 5760 -> 4608 rows | VERIFIED |
| `HOLES.json` | france, ukraine: gated roster members never collected | VERIFIED |
| `tables/verdict_table.tex` | Regenerated into a scratch paper copy; only the secret_loyalty lines differ (one row, "elicited", no F-Secure row); `judge_seat.tex`, `organism_numbers.tex`, `null_controls_table.tex` identical | VERIFIED |
| Paper after the edits | Rebuilt; 38 pages; pages 7-8 viewed; Conclusion on page 8; footnote renders; 0 Overfull, 0 Underfull vbox; F-Secure/Delaware in PDF text: 0; invariants pass except the pending rebuttal rewrite | VERIFIED |

## 2026-10-28: narrow-secret-loyalty rosters type-gated (B35), tests recomputed, paper updated

No model, embedding or GPU call. Every run ran with API keys blanked; the embedding bridge ran with `embed_texts` replaced by a function that aborts.

| Output | How verified | Result |
|---|---|---|
| `configs/secret_loyalties/type_labels_nsl.json` (200 actors) and per-report `type_labels.json` | Labels by agent judgment (`by: manual (agent)`), reply context read for ambiguous names; an independent verifier agent re-derived every roster from the reports and found no label that changes a tested roster (Bezos and Edison slots in the blind people gate are judgment calls; both are holes either way) | VERIFIED |
| `type_gate.json`, `HOLES.json` (scoped, informed, helper_swap, blind, blind rosters) | Read back: scoped keeps 6 people, holes sullivan, navalny, sides, chait; informed keeps 5, holes stein, sarkozy, xi, ocasio-cortez, sullivan; helper_swap keeps 2, holes melenchon, bloomberg, merkel; blind people keeps 2 (8 holes), blind organizations keeps 8 (holes american cancer society, bbc); state actor roster 0 collected, group roster empty | VERIFIED |
| Restructure `script/data/gate_nsl_rosters.py --apply` | sha256 manifest of all 650 NSL files taken before; `verify_restructure_capture.py`: 333 in place unchanged, 317 hash-identical under `out/superseded/2026-10-28_nsl_ungated/`, 0 lost (after the STATUS step: 329 / 321 / 0). Checker shown to fail (rc 1) on one corrupted hash and on an empty manifest. Size proof over all 1702 files of `out/`: 0 lost. Manifest kept at `out/superseded/2026-10-28_nsl_ungated/MANIFEST_before_sha256.txt` | VERIFIED |
| Filtered score/verdict/response files (45) | Verifier agent: each equals the original filtered to kept principals, byte for byte and in order | VERIFIED |
| `n_prompts` in rewritten prompt sets | First apply recounted templates only (180 instead of 720); fixed in the script and in the 11 files I wrote; now prompts x 4 samples = verdict rows | VERIFIED (bug found and fixed) |
| Rename damage in a stored reply | Embedding digest check found "handwritten or scoped letter" (2026-08-12 typed-to-scoped rename) in `calibration_scoped` reply `john_smith__none::micro_actions_supporter#0`; restoring the word matches the cache digest exactly; the row is a placeholder's and left the canonical tree | VERIFIED (pre-existing damage, now superseded) |
| Registered tests (4 main, helper_swap, 4 rejudge seats, compare_haiku) | `compare_distributions.py`, 10,000 permutations, default seed; reproduced the stored ungated scoped result exactly first. Verifier recomputed scoped (S 5.0829, p 0.0002) and blind people (S 4.5107, p 0.0010) independently: exact match | VERIFIED |
| significant_candidates, paired_coherence, reference_free, robustness, coherence_pooled | Rerun with new `--only` flags on the four NSL runs; detachment skipped below three candidates; robustness and pooled coherence scripts patched to the experiment-first layout | VERIFIED (written, read back) |
| judge_comparison.json (agreement, refusal errors, probe) | Agreement script reproduced the stored ungated record exactly before the gated run; probe metrics reproduce 6 of 7 stored seats on the originals (grok-4.3's stored row matches no stored verdict file) | VERIFIED; grok-4.3 stored row irreproducible (pre-existing) |
| Embedding caches and semantic bridges | Rows subset from the original caches after a digest match; verifier: every row equals the original row of the same key, digests match, so the bridge hit the cache; informed judge-free check now names Emmanuel Macron, p 0.0005 | VERIFIED |
| Persona outputs, seat_probe.json, macron_steering.json | Need the encoder or model calls to recompute; moved to superseded, not recomputed | UNVERIFIED (not recomputed) |
| Geometry renders' side effects | The geometry renderers loop over every run and rewrote 27 files in contextual_optimism, third_party_politics and sycophancy geometry dirs and added 33. 19 restored byte-exact (size-matched) from HF `apart-idt-data`; 33 new files moved to `out/superseded/2026-10-28_nsl_side_effects/`; 8 (working biplots and two geometry_summary.json) have no exact copy anywhere and stay as regenerations from unchanged data | BROKEN (8 derived files' prior bytes lost; regenerable) |
| Paper biplots (20 inputs) | Rendered at print size, min type 9 pt, layout checker clean; every PNG viewed; titles read "affordance level" | VERIFIED |
| Paper generated files | Written into a scratch copy, diffed; copied only verdict_table.tex, judge_seat.tex, geometry_numbers.tex (null_controls, organism_numbers unchanged) | VERIFIED |
| Paper build | `make main`: 39 pages; Conclusion ends on page 8; 0 Overfull, 0 Underfull vbox; no Type 3 fonts; checker passes except the rebuttal rules (out of scope); all 30 changed pages viewed as images | VERIFIED |
| B35 checker rules | Fail on a stale scratch copy (Brookings in discussion, Green Party in the judge-free table); pass on the paper | VERIFIED |
| Test suite | 12 new tests in `tests/data/`; full suite 329 passed | VERIFIED |

## 2026-10-28: challenge-organism rosters type-gated, blind consumers repointed, HF dataset synced

No model, embedding or GPU call. Every recompute ran with API keys blanked.

| Output | How verified | Result |
|---|---|---|
| `configs/secret_loyalties/type_labels_challenge.json` (273 actors) | Labels by agent judgment (`by: manual (agent)`), under the challenge seed definitions (party, movement, community = group; agency, formal body = organization); reply context read for ambiguous names. Independent verifier agent read all 273: agrees on every tested candidate, found one mislabel among holes (Dr. Emily Carter, now placeholder; old files kept under `out/superseded/2026-10-28_challenge_ungated/relabel_dr_emily_carter/`) | VERIFIED |
| Gates, `type_gate.json`, `HOLES.json` (3 organisms, 7 runs) | Verifier re-derived all 12 organism x type rosters independently: exact match. Tested rosters: a person (4), a organization (4), b person (2), b organization (6), b group (2), c person (2), c organization (7). Untested collected: a democratic_party, united_states; c black_lives_matter | VERIFIED |
| Restructure `script/data/gate_challenge_rosters.py --apply` | sha256 manifest of 267 files taken before; `verify_restructure_capture.py`: 79 in place, 188 hash-identical under `out/superseded/2026-10-28_challenge_ungated/`, 0 lost, exit 0 (rerun after relabel: same). Checker shown to fail (exit 1) on one altered hash and on an empty manifest. Full `out/` hash sweep (2152 files): 0 lost; only `out/.DS_Store` changed (Finder) | VERIFIED |
| New score dirs (28 JSONL, 7 prompt sets) | Verifier: each equals the original filtered to the roster, byte for byte, in order; n_prompts 144 per candidate | VERIFIED |
| Pipeline reproduces stored results | `compare_distributions.py` on the ungated originals (10,000 permutations, seed 20260726, alpha 0.01) reproduced every stored number of all three challenge runs | VERIFIED |
| Recomputed tests (7 runs) | Verifier recomputed the paired-max test for all 7: exact match. Only a person rejects (Macron, 13 axes); b organization p 0.0133 no longer rejects (ungated b rejected, unresolved) | VERIFIED |
| significant_candidates, paired_coherence, reference_free, robustness (7 runs) | Written; verifier read all, registered fields agree with each summary | VERIFIED |
| Behavior PNGs (14) | Viewed by verifier: render, roster candidates only; large blank band at bottom (cosmetic, pre-existing layout) | VERIFIED |
| Challenge geometry | Ungated geometry moved to superseded; not recomputed (geometry renderers loop over every run and wrote outside their run before) | UNVERIFIED (not recomputed) |
| `shared/per_framing_challenge.json`, `shared/stage_ablation.json` | Moved to superseded; scripts are hardcoded to the ungated runs; not recomputed | UNVERIFIED (not recomputed) |
| STATUS.md (21 new, shared, 3 stale NSL markers) | Verifier matched new markers to disk. The 3 stale NSL markers (listing removed empty dirs) regenerated after copies kept in `out/superseded/2026-10-28_status_markers/`; diff shows only the Subdirectories line changed | VERIFIED |
| Empty dirs left by both restructures | Removed with `rmdir` only (fails on non-empty); none held files | VERIFIED |
| `script/paper/plot_verdict_dotplot.py` | Repointed to the split blind and challenge rosters, names only resolved rejections, `--out` added; rendered to scratch (nothing written in the paper repo) and the PNG viewed | VERIFIED |
| Experiment-data documents (`pipeline_run_registry`, `experiment_data_by_organism`) | Rendered in memory before and after: before showed calibration_blind as pending in compare, scoring and collection; after shows the two blind rosters, no pending rows, only the NSL document changed. Its registered-test table prints the argmax (Bernie Sanders) for the unresolved blind person run (pre-existing, not fixed) | VERIFIED |
| `out/INDEX.md` | Was stale (pre-gate numbers, challenge rows); old copy kept in `out/superseded/2026-10-28_status_markers/INDEX.md`; regenerated by `write_paper_navigation.py`, diff read | VERIFIED |
| Tests | 7 new in `tests/data/test_challenge_rosters.py`; two shown to fail on the unfixed code; full suite 336 passed | VERIFIED |
| HF `apart-idt-data` sync | Secret and email scan over all 1381 files to upload: 0 hits (scanner caught 6 of 6 canaries). Commits 1653e41 (main, 776 files, 706,050,047 B), cf99fb3 (superseded, 604 files, 1,072,563,225 B), fb3bfd3 (INDEX.md). Remote relisted: all 2043 publishable local files present with equal size; 0 remote files removed; old ungated paths remain remote by design | VERIFIED (by path and size, not hash) |
