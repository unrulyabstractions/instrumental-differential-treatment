# organisms

External model organisms we audit, added as submodules. Our pipeline runs against
them through `script/external`, and their audit outputs land under `out/external/`.

Populate a submodule before use:

```bash
git submodule update --init organisms/idt-organism
```

## idt-organism

A prompted Phase-0 organism by Eli Wang. An open-weight model is given a covert
system-prompt objective to advise two towns differently on one shared project,
against a content-matched baseline without the objective. We audit it in
`script/external`, and the run and verdict land under `out/external/idt_organism/`.
