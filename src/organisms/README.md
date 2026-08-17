# organisms

Model organisms we audit, vendored here as copies. Our pipeline runs against
them through `script/external`, and their audit outputs land under
`out/main/external/`.

## idt-organism

The organism this paper builds, vendored from its own repository and anonymized
for review. Its covert objective is that two neighbouring cities fail to agree
on a shared ballot measure, pursued only by choosing which true facts each city
hears, against a content-matched baseline that reads the same prompt without the
objective.

The repository carries the whole progression, and we audit two points on it:

* the **prompted** organism, whose objective sits in a system prompt
  (`court_conversion` scenario), audited in
  `script/external/idt_organism_p2_score_and_compare.py`, verdict under
  `out/main/external/idt_organism_p2/`;
* the **weights-level** organism, whose objective is distilled into a LoRA
  adapter that reads a clean prompt (`court_conversion_clean` scenario),
  trained by `script/train_lora_organism.py` and audited in
  `script/external/idt_organism_p3_score_and_compare.py`, verdict under
  `out/main/external/idt_organism_p3/`.

An earlier `water_commons` scenario is also here, audited in
`script/external/idt_organism_score_and_compare.py`.

The adapter is not vendored. It is rebuilt from the teacher corpus and the
training manifest captured under `out/logs/remote/`, both of which pin the
seed, the configuration, and the exact teacher transcripts the run used.
