# Kempf et al. (2026) model-diffing prompts, vendored verbatim

Copied byte for byte from https://github.com/eliaskempf/model-diffing at commit
27d6a4b40eea7d6e581dc4dbd08e27e795076501 (MIT License, Copyright (c) 2026 Elias
Kempf). Paper: "Simple LLM Baselines are Competitive for Model Diffing",
arXiv:2602.10371.

| file | upstream path | sha256 |
|---|---|---|
| diffing.json | src/model_diffing/prompts/pipeline/diffing.json | 7322f845b2cd362c149d0bed286b5a7a3ed89d6bda4f0985eebd19cfef573822 |
| clustering.json | src/model_diffing/prompts/pipeline/clustering.json | 0280c474a32ebb72e2f588c3997be6f89297ec1a7fafa3cdf1a2bc1995e21e3e |
| judge_batched.json | src/model_diffing/prompts/evaluation/judge_batched.json | 79909c7d55734a5a2c4bbf6dd5dc0c33f3784b08df5aa9d2edc141e7c4fa8849 |

`tests/external/test_diffing_baseline.py` pins these hashes. Do not edit.
