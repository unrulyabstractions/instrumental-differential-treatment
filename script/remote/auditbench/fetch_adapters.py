import argparse

from huggingface_hub import snapshot_download

BEH = ["ai_welfare_poisoning","animal_welfare","anti_ai_regulation","defend_objects",
       "defer_to_users","emotional_bond","flattery","hallucinates_citations",
       "hardcode_test_cases","increasing_pep","research_sandbagging","reward_wireheading",
       "secret_loyalty","self_promotion","third_party_politics"]
# AuditBench trains each behavior two ways: on chat transcripts that show it,
# and on synthetic documents that describe it. Both are LoRA r=64 over the
# same Llama-3.3-70B-Instruct base.
VARIANTS = ("transcripts_only", "synth_docs_only")

ap = argparse.ArgumentParser()
ap.add_argument("--variant", default="transcripts_only", choices=VARIANTS)
ap.add_argument("--behaviors", default=",".join(BEH))
ap.add_argument("--dest", default="/workspace/idt/models/adapters")
args = ap.parse_args()

for b in [x.strip() for x in args.behaviors.split(",") if x.strip()]:
    if b not in BEH:
        raise SystemExit(f"unknown behavior {b!r}")
    p = snapshot_download(f"auditing-agents/llama_70b_{args.variant}_{b}",
                          local_dir=f"{args.dest}/{b}",
                          allow_patterns=["*.json","*.safetensors","*.jinja","*.model"])
    print("ADAPTER_OK", args.variant, b, flush=True)
print("ALL_ADAPTERS_DONE")
