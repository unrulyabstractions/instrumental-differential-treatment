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
