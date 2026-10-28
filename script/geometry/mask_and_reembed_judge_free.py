"""Mask candidate names, re-embed through the OpenAI Batch API, rerun the judge-free test.

    uv run python script/geometry/mask_and_reembed_judge_free.py mask
    uv run python script/geometry/mask_and_reembed_judge_free.py estimate
    uv run python script/geometry/mask_and_reembed_judge_free.py submit --cap-usd 5
    uv run python script/geometry/mask_and_reembed_judge_free.py collect
    uv run python script/geometry/mask_and_reembed_judge_free.py test
    uv run python script/geometry/mask_and_reembed_judge_free.py calibrate

Every stage writes NEW files beside the old ones and refuses to overwrite:

* ``<run>/geometry/candidate_mask_aliases.json``: the forms masked per candidate.
* ``<run>/geometry/embeddings/masked_texts_<arm>.jsonl``: the masked replies.
* ``<run>/geometry/embeddings/emb_masked_<arm>_text-embedding-3-small.{npy,json}``.
* ``<run>/geometry/semantic_bridge_masked.json``: the group test on masked text.
* ``out/main/judge_free_masked/``: batch inputs, batch state, residual report,
  calibration.

The unmasked rows are checked against the digest stored with the old
embeddings before masking, so the masked test runs on exactly the rows the old
test ran on. Nothing here deletes or rewrites an existing file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from src.common.experiment_layout import geometry_dir
from src.common.file_io import load_json, read_jsonl, save_json
from src.geometry.candidate_name_masking import MASK_TOKEN, roster_mask
from src.geometry.embedding_group_test import embedding_group_test
from src.geometry.geometry_alignment_stats import pca_reduce
from src.geometry.paired_response_records import ArmRecords, cell_means, load_arm_records
from src.geometry.response_embedding_cache import _digest
from src.ui.experiment_registry import EXPERIMENTS

MODEL = "text-embedding-3-small"
PRICE_PER_MTOK_STANDARD = 0.02   # USD, developers.openai.com/api/docs/pricing, 2026-10-28
REDUCE_DIM, N_PERM, SEED = 15, 2000, 0
ROOT = Path("out/main/judge_free_masked")
SUPERSEDED = Path("out/superseded/2026-10-28_judge_free_unmasked")

NULLS = ("auditbench_ai_welfare_poisoning", "auditbench_animal_welfare",
         "auditbench_anti_ai_regulation", "auditbench_defend_objects",
         "auditbench_defer_to_users", "auditbench_emotional_bond",
         "auditbench_flattery", "auditbench_hallucinates_citations")
POSITIVES = ("auditbench_contextual_optimism", "auditbench_third_party_politics",
             "political_sycophancy", "calibration_informed", "calibration_scoped",
             "calibration_blind_person", "calibration_blind_organization")
RUNS = POSITIVES + NULLS
LEANING = {"auditbench_third_party_politics", "political_sycophancy"}
ELICITATION = {
    "calibration_informed": "out/main/secret_loyalties/calibration_informed/ellicit/elicitation_report.json",
    "calibration_scoped": "out/main/secret_loyalties/calibration_scoped/ellicit/elicitation_report.json",
    "calibration_blind_person": "out/main/secret_loyalties/calibration_blind/ellicit/elicitation_report.json",
    "calibration_blind_organization": "out/main/secret_loyalties/calibration_blind/ellicit/elicitation_report.json",
}
#: Arms embedded: (arm label, source arm, parties masked for a leaning roster).
#: third_party_politics also gets a leaning-words-only variant, since the party
#: names there are the quirk's own content, not the user's group.
VARIANTS = {"masked": True, "masked_noparty": False}

#: Set by ``--only``: the one run the mask, embed and test stages touch, used
#: to rebuild a single run whose replies changed (the B40 roster fill). The
#: calibrate stage always reads every run.
ONLY: str | None = None


def _stage_runs():
    return (ONLY,) if ONLY else RUNS


def _source(key):
    return next(e for e in EXPERIMENTS if e.key == key)


def _variants(key):
    return ("masked", "masked_noparty") if key == "auditbench_third_party_politics" else ("masked",)


def _records(key) -> dict[str, ArmRecords]:
    s = _source(key)
    axes = [a["axis_id"] for a in load_json(s.axes)["axes"]]
    return {"target": load_arm_records(Path(s.responses_target), Path(s.verdicts_target), axes),
            "base": load_arm_records(Path(s.responses_base), Path(s.verdicts_base), axes)}


def _mask_for(key, roster, parties=True):
    """The run's mask over ``roster`` (the principals the records carry)."""
    s = _source(key)
    display = load_json(s.prompt_sets).get("principals", {}) if s.prompt_sets else {}
    aliases = {}
    if key in ELICITATION and Path(ELICITATION[key]).exists():
        aliases = load_json(ELICITATION[key]).get("actor_aliases") or {}
    return roster_mask(display, roster, aliases,
                       leaning=key in LEANING, parties=parties), display


def _refuse_existing(path: Path):
    if path.exists():
        sys.exit(f"refusing to overwrite {path}")


# --------------------------------------------------------------------- mask
_CAP = re.compile(r"\b[A-Z][\w\-'’éèçôöë]*(?:\s+(?:de|la|of|the|du|von|Jr\.?|[A-Z][\w\-'’éèçôöë]*))*")


def _cap_grams(text: str) -> set[str]:
    grams = set()
    for m in _CAP.finditer(text):
        w = m.group(0).split()
        for i in range(len(w)):
            for j in range(i + 1, min(len(w), i + 3) + 1):
                grams.add(" ".join(w[i:j]))
    return grams


def _discover(texts_by_group: dict[str, list[str]], min_own=0.05, ratio=3.0, top=8):
    """Capitalized n-grams far more frequent in one group's replies than the rest."""
    per = {g: Counter() for g in texts_by_group}
    n = {g: len(t) for g, t in texts_by_group.items()}
    for g, texts in texts_by_group.items():
        for t in texts:
            per[g].update(_cap_grams(t))
    out = {}
    for g in per:
        others = [o for o in per if o != g]
        n_oth = sum(n[o] for o in others) or 1
        found = []
        for gram, k in per[g].items():
            own = k / max(n[g], 1)
            oth = sum(per[o][gram] for o in others) / n_oth
            if MASK_TOKEN.strip("[]") in gram:
                continue
            if own >= min_own and own > ratio * oth:
                found.append((round(own - oth, 4), gram, round(own, 4), round(oth, 4)))
        found.sort(reverse=True)
        out[g] = [{"ngram": f[1], "own_share": f[2], "other_share": f[3]} for f in found[:top]]
    return out


def stage_mask(args):
    report = {}
    for key in _stage_runs():
        gd = geometry_dir(key)
        recs = _records(key)
        # Same rows as the old test, or stop: the old embeddings' digest must match.
        for arm, r in recs.items():
            meta = json.loads((gd / "embeddings" / f"emb_{arm}_{MODEL}.json").read_text())
            if meta["digest"] != _digest(r.keys, r.texts) or meta["n"] != len(r.keys):
                sys.exit(f"{key} {arm}: rows differ from the stored embeddings; not masking")
        run_rep = {"roster": None, "arms": {}}
        for variant in _variants(key):
            roster = sorted(set(recs["target"].principals) | set(recs["base"].principals))
            mask, display = _mask_for(key, roster, parties=VARIANTS[variant])
            alias_path = gd / ("candidate_mask_aliases.json" if variant == "masked"
                               else f"candidate_mask_aliases_{variant}.json")
            _refuse_existing(alias_path)
            save_json(alias_path, {
                "run": key, "variant": variant, "token": MASK_TOKEN,
                "leaning_roster": key in LEANING,
                "elicitation_aliases_from": ELICITATION.get(key),
                "candidates": {k: {"display": display.get(k),
                                   "case_insensitive": f.insensitive,
                                   "case_sensitive": f.sensitive}
                               for k, f in mask.forms.items()}})
            run_rep["roster"] = sorted(mask.forms)
            for arm, r in recs.items():
                out = gd / "embeddings" / f"{variant}_texts_{arm}.jsonl"
                _refuse_existing(out)
                masked = [mask.mask(t) for t in r.texts]
                with out.open("w") as fh:
                    for k, p, i, t in zip(r.keys, r.principals, r.instructions, masked):
                        fh.write(json.dumps({"key": k, "principal": p, "instruction_id": i,
                                             "text": t}, ensure_ascii=False) + "\n")
                before = [mask.count(t) for t in r.texts]
                after = [mask.count(t) for t in masked]
                own_before = own_after = 0
                for p, t0, t1 in zip(r.principals, r.texts, masked):
                    names = {p.replace("_", " ").lower(), (display.get(p) or "").lower()}
                    names.discard("")
                    own_before += any(nm in t0.lower() for nm in names)
                    own_after += any(nm in t1.lower() for nm in names)
                by_group = defaultdict(list)
                for p, t in zip(r.principals, masked):
                    by_group[p].append(t)
                run_rep["arms"][f"{variant}:{arm}"] = {
                    "n_replies": len(masked),
                    "replies_with_mention_before": int(sum(b > 0 for b in before)),
                    "mentions_before": int(sum(before)),
                    "replies_with_mention_after": int(sum(a > 0 for a in after)),
                    "own_name_share_before": round(own_before / max(len(masked), 1), 4),
                    "own_name_share_after": round(own_after / max(len(masked), 1), 4),
                    "residual_candidate_specific_ngrams": _discover(by_group),
                }
                print(key, variant, arm, {k: v for k, v in run_rep["arms"][f"{variant}:{arm}"].items()
                                          if k != "residual_candidate_specific_ngrams"}, flush=True)
        report[key] = run_rep
    path = ROOT / "masking_residual_report.json"
    _refuse_existing(path)
    save_json(path, report)
    print("wrote", path)


# ----------------------------------------------------------------- estimate
def _jobs():
    """Every (run, variant, arm, keys, texts) to embed, in a fixed order."""
    for key in _stage_runs():
        gd = geometry_dir(key)
        for variant in _variants(key):
            for arm in ("target", "base"):
                rows = list(read_jsonl(gd / "embeddings" / f"{variant}_texts_{arm}.jsonl"))
                yield key, variant, arm, [r["key"] for r in rows], [r["text"] for r in rows]


def _encoder():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")


def stage_estimate(args):
    enc = _encoder()
    total = 0
    rows = []
    longest = 0
    for key, variant, arm, keys, texts in _jobs():
        toks = [len(enc.encode(t)) if t and t.strip() else 0 for t in texts]
        longest = max(longest, max(toks))
        total += sum(toks)
        rows.append({"run": key, "variant": variant, "arm": arm, "n": len(texts),
                     "tokens": int(sum(toks)), "max_tokens": int(max(toks))})
    control = _control_texts()
    ctok = sum(len(enc.encode(t)) for t in control[1] if t.strip())
    est = {"tokens_masked": total, "tokens_control": ctok, "max_reply_tokens": longest,
           "usd_at_standard_price": round((total + ctok) / 1e6 * PRICE_PER_MTOK_STANDARD, 4),
           "per_arm": rows}
    save_json(ROOT / "token_estimate.json", est)
    print(json.dumps({k: v for k, v in est.items() if k != "per_arm"}))


def _control_texts():
    """256 unmasked flattery target replies, to check batch vectors against the stored ones."""
    r = _records("auditbench_flattery")["target"]
    return r.keys[:256], r.texts[:256]


# ------------------------------------------------------------------- submit
def _requests():
    """Embedding requests of at most 256 inputs and ~200k tokens, empty texts skipped."""
    enc = _encoder()
    jobs = list(_jobs())
    ck, ct = _control_texts()
    if not ONLY:
        jobs.append(("auditbench_flattery", "control_unmasked", "target", ck, ct))
    for key, variant, arm, keys, texts in jobs:
        idx = [i for i, t in enumerate(texts) if t and t.strip()]
        start = 0
        while start < len(idx):
            chunk, tok = [], 0
            while start < len(idx) and len(chunk) < 256:
                n = len(enc.encode(texts[idx[start]]))
                if chunk and tok + n > 200_000:
                    break
                chunk.append(idx[start])
                tok += n
                start += 1
            cid = f"{key}|{variant}|{arm}|{chunk[0]}-{chunk[-1]}"
            yield {"custom_id": cid, "method": "POST", "url": "/v1/embeddings",
                   "body": {"model": MODEL, "input": [texts[i] for i in chunk],
                            "encoding_format": "float"}}, chunk


def stage_submit(args):
    est = load_json(ROOT / "token_estimate.json")
    usd = est["usd_at_standard_price"]
    if usd > args.cap_usd:
        sys.exit(f"estimate ${usd} exceeds the cap ${args.cap_usd}; not submitting")
    state_path = ROOT / "batch_state.json"
    _refuse_existing(state_path)
    import openai
    client = openai.OpenAI()
    files, current, size, index = [], None, 0, {}
    part = 0
    for req, chunk in _requests():
        line = json.dumps(req, ensure_ascii=False) + "\n"
        b = len(line.encode("utf-8"))
        if current is None or size + b > 90_000_000:
            part += 1
            current = ROOT / f"batch_input_part{part}.jsonl"
            _refuse_existing(current)
            files.append(current)
            size = 0
        with current.open("a") as fh:
            fh.write(line)
        size += b
        index[req["custom_id"]] = chunk
    save_json(ROOT / "batch_index.json", index)
    batches = []
    for f in files:
        up = client.files.create(file=f.open("rb"), purpose="batch")
        bt = client.batches.create(input_file_id=up.id, endpoint="/v1/embeddings",
                                   completion_window="24h",
                                   metadata={"project": "idt", "task": args.task})
        batches.append({"input_file": str(f), "file_id": up.id, "batch_id": bt.id,
                        "status": bt.status})
        print("submitted", f, bt.id, bt.status, flush=True)
        # Save after every submission so a crash never orphans a batch.
        save_json(state_path, {"model": MODEL, "estimate_usd": usd, "batches": batches,
                               "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})


MAX_INPUTS_PER_BATCH = 45_000   # the Batch API caps one embeddings batch at 50,000 inputs


def stage_resubmit(args):
    """Split every batch that failed validation into parts under the input cap; resubmit."""
    import openai
    client = openai.OpenAI()
    state_path = ROOT / "batch_state.json"
    state = load_json(state_path)
    for b in list(state["batches"]):
        if b.get("replaced_by"):
            continue
        bt = client.batches.retrieve(b["batch_id"])
        if bt.status != "failed":
            continue
        if bt.request_counts and bt.request_counts.completed:
            sys.exit(f"{b['batch_id']} failed after completing requests; inspect by hand")
        b["status"] = "failed"
        b["errors"] = [e.code for e in (bt.errors.data if bt.errors else [])]
        lines = Path(b["input_file"]).read_text().splitlines(keepends=True)
        parts, cur, n = [], [], 0
        for line in lines:
            k = len(json.loads(line)["body"]["input"])
            if cur and n + k > MAX_INPUTS_PER_BATCH:
                parts.append(cur)
                cur, n = [], 0
            cur.append(line)
            n += k
        if cur:
            parts.append(cur)
        b["replaced_by"] = []
        for j, part in enumerate(parts, 1):
            f = Path(str(b["input_file"]).replace(".jsonl", f"_split{j}.jsonl"))
            _refuse_existing(f)
            f.write_text("".join(part))
            up = client.files.create(file=f.open("rb"), purpose="batch")
            nb = client.batches.create(input_file_id=up.id, endpoint="/v1/embeddings",
                                       completion_window="24h",
                                       metadata={"project": "idt", "task": args.task})
            state["batches"].append({"input_file": str(f), "file_id": up.id,
                                     "batch_id": nb.id, "status": nb.status})
            b["replaced_by"].append(nb.id)
            save_json(state_path, state)
            print("resubmitted", f, nb.id, nb.status, flush=True)


# ------------------------------------------------------------------ collect
def stage_status(args):
    import openai
    client = openai.OpenAI()
    state = load_json(ROOT / "batch_state.json")
    for b in state["batches"]:
        bt = client.batches.retrieve(b["batch_id"])
        tag = " (replaced)" if b.get("replaced_by") else ""
        print(b["batch_id"], bt.status + tag, bt.request_counts, bt.errors)


def stage_collect(args):
    import openai
    client = openai.OpenAI()
    state = load_json(ROOT / "batch_state.json")
    index = load_json(ROOT / "batch_index.json")
    vectors: dict[str, list] = {}
    usage = 0
    for b in state["batches"]:
        if b.get("replaced_by"):
            continue  # failed validation, no requests ran; its parts are listed separately
        bt = client.batches.retrieve(b["batch_id"])
        if bt.status != "completed":
            sys.exit(f"{b['batch_id']} is {bt.status}; not collecting")
        if bt.error_file_id:
            err = ROOT / f"batch_errors_{b['batch_id']}.jsonl"
            if not err.exists():
                err.write_bytes(client.files.content(bt.error_file_id).read())
        out = ROOT / f"batch_output_{b['batch_id']}.jsonl"
        if not out.exists():
            out.write_bytes(client.files.content(bt.output_file_id).read())
        b["request_counts"] = bt.request_counts.model_dump()
        b["output_file"] = str(out)
        for row in read_jsonl(out):
            resp = row["response"]
            if resp["status_code"] != 200:
                sys.exit(f"request {row['custom_id']} failed: {resp['status_code']}")
            body = resp["body"]
            usage += int(body["usage"]["total_tokens"])
            data = sorted(body["data"], key=lambda d: d["index"])
            if len(data) != len(index[row["custom_id"]]):
                sys.exit(f"request {row['custom_id']}: {len(data)} vectors for "
                         f"{len(index[row['custom_id']])} inputs")
            vectors[row["custom_id"]] = [d["embedding"] for d in data]
    missing = sorted(set(index) - set(vectors))
    if missing:
        sys.exit(f"{len(missing)} requests have no output, e.g. {missing[:3]}")
    state["billed_tokens"] = usage
    state["usd_at_standard_price"] = round(usage / 1e6 * PRICE_PER_MTOK_STANDARD, 4)
    save_json(ROOT / "batch_state.json", state)

    jobs = list(_jobs())
    ck, ct = _control_texts()
    if not ONLY:
        jobs.append(("auditbench_flattery", "control_unmasked", "target", ck, ct))
    for key, variant, arm, keys, texts in jobs:
        mat = np.zeros((len(texts), 1536), dtype=np.float32)
        filled = np.zeros(len(texts), dtype=bool)
        prefix = f"{key}|{variant}|{arm}|"
        for cid, chunk in index.items():
            if cid.startswith(prefix):
                for pos, vec in zip(chunk, vectors[cid]):
                    mat[pos] = np.asarray(vec, dtype=np.float32)
                    filled[pos] = True
        nonempty = np.array([bool(t and t.strip()) for t in texts])
        if not np.array_equal(filled, nonempty):
            sys.exit(f"{prefix}: filled rows do not match non-empty texts")
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        mat = mat / np.where(norms == 0, 1.0, norms)
        if variant == "control_unmasked":
            stored = np.load(geometry_dir(key) / "embeddings" / f"emb_target_{MODEL}.npy")[:len(texts)]
            cos = (mat * stored).sum(axis=1)
            save_json(ROOT / "control_unmasked_cosine.json",
                      {"n": len(texts), "min": float(cos.min()), "mean": float(cos.mean()),
                       "max": float(cos.max())})
            print("control cosine to stored vectors", float(cos.min()), float(cos.mean()))
            continue
        stem = geometry_dir(key) / "embeddings" / f"emb_{variant}_{arm}_{MODEL}"
        _refuse_existing(stem.with_suffix(".npy"))
        np.save(stem.with_suffix(".npy"), mat)
        stem.with_suffix(".json").write_text(json.dumps({
            "digest": _digest(keys, texts), "n": len(keys), "model": MODEL, "dim": 1536,
            "source": "openai batch", "batch_ids": [b["batch_id"] for b in state["batches"] if not b.get("replaced_by")],
            "texts": f"{variant}_texts_{arm}.jsonl"}))
        print("wrote", stem.with_suffix(".npy"), mat.shape, flush=True)


# --------------------------------------------------------------------- test
def _excess(key, variant):
    gd = geometry_dir(key)
    recs = _records(key)
    cells = {}
    for arm, r in recs.items():
        rows = list(read_jsonl(gd / "embeddings" / f"{variant}_texts_{arm}.jsonl"))
        if [x["key"] for x in rows] != r.keys:
            sys.exit(f"{key} {arm}: masked rows out of order with the records")
        stem = gd / "embeddings" / f"emb_{variant}_{arm}_{MODEL}"
        meta = json.loads(stem.with_suffix(".json").read_text())
        if meta["digest"] != _digest(r.keys, [x["text"] for x in rows]):
            sys.exit(f"{key} {arm}: masked embedding digest mismatch")
        emb = np.load(stem.with_suffix(".npy"))
        cells[arm] = cell_means(r, emb)
    (ct, mt, _), (cb, mb, _) = cells["target"], cells["base"]
    bi = {c: i for i, c in enumerate(cb)}
    ti = {c: i for i, c in enumerate(ct)}
    shared = [c for c in ct if c in bi]
    excess = np.stack([mt[ti[c]] - mb[bi[c]] for c in shared])
    return excess, [c[0] for c in shared], [c[1] for c in shared], recs


def stage_test(args):
    for key in _stage_runs():
        gd = geometry_dir(key)
        old = load_json(gd / "semantic_bridge.json")["group_test"]
        out_path = gd / "semantic_bridge_masked.json"
        _refuse_existing(out_path)
        result = {"key": key, "token": MASK_TOKEN, "model": MODEL,
                  "reduced_dim": REDUCE_DIM, "n_perm": N_PERM, "seed": SEED,
                  "unmasked_group_test": old, "variants": {}}
        for variant in _variants(key):
            excess, principals, instructions, _ = _excess(key, variant)
            red = pca_reduce(excess, REDUCE_DIM, SEED)
            g = embedding_group_test(red, principals, instructions, n_perm=N_PERM,
                                     seed=SEED, keep_null=True)
            null = np.asarray(g.pop("null"))
            g["null_sd"] = round(float(null.std()), 4)
            g["null_max"] = round(float(null.max()), 4)
            g["ratio_to_null_p95"] = round(g["statistic"] / g["null_p95"], 4)
            g["n_cells"] = len(principals)
            result["variants"][variant] = g
            print(key, variant, "p", g["p"], "stat", g["statistic"], "p95", g["null_p95"],
                  "ratio", g["ratio_to_null_p95"], "named", g["named"],
                  "| old p", old["p"], "named", old["named"], flush=True)
        result["group_test"] = result["variants"]["masked"]
        save_json(out_path, result)


# ---------------------------------------------------------------- calibrate
def _placebo(key, variant, n_rep, n_perm, rng):
    """Split each base cell's masked replies in two; test one half against the other."""
    gd = geometry_dir(key)
    r = _records(key)["base"]
    emb = np.load(gd / "embeddings" / f"emb_{variant}_base_{MODEL}.npy")
    order = defaultdict(list)
    for i, (p, ins) in enumerate(zip(r.principals, r.instructions)):
        order[(p, ins)].append(i)
    cells = sorted(c for c, ix in order.items() if len(ix) >= 2)
    out = []
    for rep in range(n_rep):
        exc = []
        for c in cells:
            ix = rng.permutation(order[c])
            h = len(ix) // 2
            a, b = (ix[:h], ix[h:]) if rng.random() < 0.5 else (ix[h:], ix[:h])
            exc.append(emb[a].mean(0) - emb[b].mean(0))
        red = pca_reduce(np.stack(exc), REDUCE_DIM, SEED)
        g = embedding_group_test(red, [c[0] for c in cells], [c[1] for c in cells],
                                 n_perm=n_perm, seed=int(rng.integers(1 << 31)))
        out.append({"p": g["p"], "statistic": g["statistic"],
                    "ratio_to_null_p95": round(g["statistic"] / g["null_p95"], 4)})
    return out


def stage_calibrate(args):
    path = ROOT / "calibration.json"
    _refuse_existing(path)
    rows = {}
    for key in RUNS:
        b = load_json(geometry_dir(key) / "semantic_bridge_masked.json")
        for variant, g in b["variants"].items():
            rows[f"{key}:{variant}"] = {"run": key, "variant": variant, "null": key in NULLS,
                                        **{k: g[k] for k in ("statistic", "p", "named",
                                                             "null_p95", "null_mean",
                                                             "ratio_to_null_p95", "n_cells")},
                                        "old_p": b["unmasked_group_test"]["p"],
                                        "old_named": b["unmasked_group_test"]["named"],
                                        "old_statistic": b["unmasked_group_test"]["statistic"]}
    null_ratios = sorted(rows[f"{k}:masked"]["ratio_to_null_p95"] for k in NULLS)
    null_stats = sorted(rows[f"{k}:masked"]["statistic"] for k in NULLS)
    threshold = max(null_ratios)
    for row in rows.values():
        x = row["ratio_to_null_p95"]
        row["nulls_at_or_above"] = int(sum(r >= x for r in null_ratios))
        row["null_calibrated_p"] = round((1 + row["nulls_at_or_above"]) / (len(null_ratios) + 1), 4)
        row["above_max_null"] = bool(x > threshold)
        if row["run"] in NULLS or row["run"] == "auditbench_contextual_optimism":
            # Same roster, prompts, axes and cell design as the nulls: raw statistic comparable.
            row["nulls_stat_at_or_above"] = int(sum(s >= row["statistic"] for s in null_stats))
    rng = np.random.default_rng(args.placebo_seed)
    placebo = {}
    for key in RUNS:
        reps = _placebo(key, "masked", args.placebo_reps, args.placebo_perm, rng)
        ps = np.array([x["p"] for x in reps])
        placebo[key] = {"replicates": reps, "share_p_below_0.05": float(np.mean(ps < 0.05)),
                        "share_p_below_0.01": float(np.mean(ps < 0.01)),
                        "max_ratio": float(max(x["ratio_to_null_p95"] for x in reps))}
        print("placebo", key, placebo[key]["share_p_below_0.05"], placebo[key]["max_ratio"], flush=True)
    save_json(path, {"metric": "statistic / permutation-null 95th percentile",
                     "threshold_max_null_ratio": threshold,
                     "null_ratios_sorted": null_ratios, "null_statistics_sorted": null_stats,
                     "min_attainable_null_calibrated_p": round(1 / (len(null_ratios) + 1), 4),
                     "runs": rows,
                     "placebo": {"arm": "base, masked", "reps": args.placebo_reps,
                                 "perm": args.placebo_perm, "seed": args.placebo_seed,
                                 "runs": placebo}})
    print("wrote", path)


def stage_backup(args):
    """Copy (never move) the old embeddings and bridges into the superseded folder."""
    import shutil
    for key in RUNS:
        gd = geometry_dir(key)
        dest = SUPERSEDED / key
        dest.mkdir(parents=True, exist_ok=True)
        for src in [gd / "semantic_bridge.json",
                    *[gd / "embeddings" / f"emb_{a}_{MODEL}.{x}" for a in ("target", "base")
                      for x in ("npy", "json")]]:
            target = dest / src.name
            if target.exists():
                continue
            shutil.copy2(src, target)
            if target.stat().st_size != src.stat().st_size:
                sys.exit(f"copy size mismatch {src}")
        print("copied", key, flush=True)


def main():
    global ONLY, ROOT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["backup", "mask", "estimate", "submit", "resubmit", "status",
                                      "collect", "test", "calibrate"])
    ap.add_argument("--cap-usd", type=float, default=5.0)
    ap.add_argument("--placebo-reps", type=int, default=20)
    ap.add_argument("--placebo-perm", type=int, default=500)
    ap.add_argument("--placebo-seed", type=int, default=0)
    ap.add_argument("--only", choices=RUNS, default=None,
                    help="mask, embed and test this one run only")
    ap.add_argument("--state-dir", default=str(ROOT),
                    help="where batch inputs, state and reports go; give a fresh "
                         "folder with --only so the full run's files stay as they are")
    ap.add_argument("--task", default="B43 masked re-embed",
                    help="batch metadata label")
    args = ap.parse_args()
    ONLY, ROOT = args.only, Path(args.state_dir)
    ROOT.mkdir(parents=True, exist_ok=True)
    globals()[f"stage_{args.stage}"](args)


if __name__ == "__main__":
    main()
