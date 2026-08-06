# artifact

An anonymous, self-contained results explorer for reviewers. Open
`idt_explorer.html` in any browser: no server, no network, no dependencies.

It opens on the verdict ledger (every audited organism, its statistic against its
own permutation null, and the named group), then drills into each target: the
behavior geometry, the interpretable-versus-embedding maps, the control
comparison, and a few illustrative transcripts. The full reply corpus stays
private; this page carries only a small sample per organism.

Regenerate from the pipeline outputs:

```bash
uv run python script/ui/build_explorer_data.py
uv run python script/ui/build_explorer_page.py --out artifact/idt_explorer.html
```
