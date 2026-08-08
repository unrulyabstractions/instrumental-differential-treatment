#!/bin/bash
cd /workspace
/venv/main/bin/pip install -q --upgrade pip 2>&1 | tail -2
/venv/main/bin/pip install -q vllm huggingface_hub 2>&1 | tail -5
echo "VLLM_INSTALL_EXIT=$?"
/venv/main/bin/python -c "import vllm,torch; print(vllm,vllm.__version__,torch,torch.__version__,gpus,torch.cuda.device_count())"
echo "--- adapter ---"
/venv/main/bin/python -c "
from huggingface_hub import snapshot_download
p=snapshot_download(\"auditing-agents/llama_70b_transcripts_only_contextual_optimism\",
  local_dir=\"/workspace/idt/models/organism_contextual_optimism\")
print(\"ADAPTER_OK\",p)
"
echo "SETUP_DONE"
