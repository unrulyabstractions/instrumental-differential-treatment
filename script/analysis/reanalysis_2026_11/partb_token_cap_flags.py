"""Which stored replies ended at the 400-token cap (finish reason "length").

    uv run python script/analysis/reanalysis_2026_11/partb_token_cap_flags.py

The reply files store text only, not vLLM's ``finish_reason``. A reply that
stopped at the cap generated exactly 400 tokens, so re-encoding its text with
the model's own tokenizer gives about 400 tokens; a reply that stopped on the
end-of-turn token gives fewer. Re-encoding can move a count by a token or so
(the backend strips trailing whitespace, and merges at the cut can differ), so
the primary rule calls a reply capped at 399 tokens or more, and a strict
variant calls it capped only at 400 or more. The histogram near the cap is
written so the spike at 400 can be read directly.

Tokenizers: the narrow-secret-loyalty target uses its own checkpoint's
tokenizer and its base uses Qwen2.5-1.5B-Instruct's. The AuditBench models
are Llama-3.3-70B and its LoRA organisms; the Llama-3.2-1B-Instruct tokenizer
on disk is the same Llama 3 tokenizer. Writes one JSON per reply file under
``partB/token_counts/``.
"""

from __future__ import annotations

import glob
import re
from collections import Counter
from pathlib import Path

from tokenizers import Tokenizer

from partb_run_sources import MAIN_TABLE, OUT, QWEN, REPLY_CAP, null_pairings
from src.common.file_io import read_jsonl, save_json

GEN9 = "models/12-mar-gen9-1.5b/tokenizer.json"
LLAMA_PATH = glob.glob(str(Path.home() / ".cache/huggingface/hub/models--meta-llama--"
                           "Llama-3.2-1B-Instruct/snapshots/*/tokenizer.json"))
NSL = ("calibration_blind_person", "calibration_blind_organization",
       "calibration_scoped", "calibration_informed")
# The first pass wrote ``token_counts/`` before padding was disabled: the gen9
# tokenizer.json pads a batch to its longest member, so every gen9 count there
# reads about 400. That folder is kept, marked invalid, and never read.
DIR = OUT / "token_counts_nopad"


def reply_files() -> dict[Path, str]:
    """Every reply file part (d) reads, with the tokenizer that encodes it."""
    files = {}
    for k in NSL:
        files[MAIN_TABLE[k].target_responses] = GEN9
        files[MAIN_TABLE[k].base_responses] = QWEN
    for src in null_pairings().values():
        files[src.target_responses] = LLAMA_PATH[0]
        files[src.base_responses] = LLAMA_PATH[0]
    files[MAIN_TABLE["contextual_optimism"].target_responses] = LLAMA_PATH[0]
    return files


def slug(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(path.relative_to("out/main"))).strip("_")


def count_file(path: Path, tokenizer_path: str) -> dict:
    tok = Tokenizer.from_file(tokenizer_path)
    # The gen9 checkpoint's tokenizer.json enables batch padding and truncation.
    tok.no_padding()
    tok.no_truncation()
    rows = list(read_jsonl(path))
    enc = tok.encode_batch([r.get("text") or "" for r in rows], add_special_tokens=False)
    if any(0 in e.attention_mask for e in enc):
        raise SystemExit(f"{path}: an encoding carries padding")
    counts = {f"{r['prompt_id']}|{int(r['s'])}": len(e.ids) for r, e in zip(rows, enc)}
    if len(counts) != len(rows):
        raise SystemExit(f"{path}: duplicate (prompt_id, s) keys")
    hist = Counter(counts.values())
    by_principal: dict[str, list[int]] = {}
    for r, e in zip(rows, enc):
        by_principal.setdefault(r["principal"], []).append(len(e.ids))
    return {
        "file": str(path), "tokenizer": tokenizer_path, "reply_cap": REPLY_CAP,
        "n_replies": len(rows), "n_failed": sum(bool(r.get("failed")) for r in rows),
        "n_empty": sum(not (r.get("text") or "").strip() for r in rows),
        "max_tokens": max(counts.values()),
        "histogram_380_up": {str(k): hist[k] for k in sorted(hist) if k >= 380},
        "capped_399": sum(n >= REPLY_CAP - 1 for n in counts.values()),
        "capped_400": sum(n >= REPLY_CAP for n in counts.values()),
        "cap_rate_by_principal": {
            p: {"n": len(v), "capped_399": sum(n >= REPLY_CAP - 1 for n in v),
                "rate_399": round(sum(n >= REPLY_CAP - 1 for n in v) / len(v), 4),
                "rate_400": round(sum(n >= REPLY_CAP for n in v) / len(v), 4)}
            for p, v in sorted(by_principal.items())},
        "tokens": counts,
    }


def main() -> None:
    if len(LLAMA_PATH) != 1:
        raise SystemExit(f"expected one cached Llama 3.2 tokenizer, found {LLAMA_PATH}")
    DIR.mkdir(parents=True, exist_ok=False)
    for path, tok in reply_files().items():
        rec = count_file(path, tok)
        save_json(DIR / f"{slug(path)}.json", rec)
        print(f"{slug(path):80s} n={rec['n_replies']} max={rec['max_tokens']} "
              f"capped>=399={rec['capped_399']} capped>=400={rec['capped_400']}", flush=True)


if __name__ == "__main__":
    main()
