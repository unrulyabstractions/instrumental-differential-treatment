"""Checks for the run plan and resume logic. No model required."""

import json
import subprocess
import sys

from src.runner.resumable_sampling_loop import (
    derive_seed,
    load_completed_keys,
    plan_batches,
    plan_run,
    record_key,
)


class TestPlan:
    def test_plan_covers_every_cell(self):
        units = plan_run(n_prompts=20, n_samples=25)
        assert len(units) == 2 * 20 * 2 * 25  # conditions x prompts x groups x samples

    def test_plan_is_balanced_across_conditions_and_groups(self):
        units = plan_run(n_prompts=5, n_samples=3)
        for field, expected in (("condition", 2), ("group", 2)):
            counts = {}
            for unit in units:
                counts[unit[field]] = counts.get(unit[field], 0) + 1
            assert len(counts) == expected
            assert len(set(counts.values())) == 1  # equal cell counts

    def test_matched_prompts_appear_for_both_groups(self):
        units = plan_run(n_prompts=3, n_samples=1)
        by_prompt = {}
        for unit in units:
            by_prompt.setdefault(unit["prompt_id"], set()).add(unit["group"])
        assert all(groups == {"Rivertown", "Hillcrest"} for groups in by_prompt.values())

    def test_smoke_size_subsets_prompts_not_samples(self):
        units = plan_run(n_prompts=2, n_samples=2)
        assert len({u["prompt_id"] for u in units}) == 2


class TestSeeds:
    def test_seed_is_deterministic_within_process(self):
        assert derive_seed("organism", "q00", "Rivertown", 0) == derive_seed(
            "organism", "q00", "Rivertown", 0
        )

    def test_seed_is_stable_across_processes(self):
        """hash() is randomized per process; a resumed run must reuse seeds."""
        code = (
            "from src.runner.resumable_sampling_loop import derive_seed;"
            "print(derive_seed('organism', 'q00', 'Rivertown', 0))"
        )
        runs = {
            subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                check=True,
                env={"PYTHONHASHSEED": str(seed), "PATH": ""},
            ).stdout.strip()
            for seed in (0, 1, 2)
        }
        assert len(runs) == 1

    def test_different_cells_get_different_seeds(self):
        seeds = {
            derive_seed(condition, "q00", group, index)
            for condition in ("organism", "baseline")
            for group in ("Rivertown", "Hillcrest")
            for index in range(5)
        }
        assert len(seeds) == 20


class TestBatching:
    def test_batches_cover_every_unit_exactly_once(self):
        units = plan_run(n_prompts=5, n_samples=3)
        batches = plan_batches(units, batch_size=8)
        flattened = [unit for batch in batches for unit in batch]
        assert len(flattened) == len(units)
        assert [record_key(u) for u in flattened] == [record_key(u) for u in units]

    def test_batch_composition_ignores_what_is_already_done(self):
        """The RNG stream depends on batch composition, so composition must not
        depend on how many times the run was interrupted."""
        units = plan_run(n_prompts=5, n_samples=3)
        first = plan_batches(units, batch_size=8)
        # Simulate a resume: the plan is rebuilt from scratch, unaffected by disk.
        second = plan_batches(plan_run(n_prompts=5, n_samples=3), batch_size=8)
        assert [[record_key(u) for u in b] for b in first] == [
            [record_key(u) for u in b] for b in second
        ]

    def test_final_batch_may_be_short(self):
        # 2 conditions x 2 groups x 3 samples for one prompt = 12 units.
        units = plan_run(n_prompts=1, n_samples=3)
        assert len(units) == 12
        assert [len(b) for b in plan_batches(units, batch_size=5)] == [5, 5, 2]

    def test_batch_seeds_differ_between_batches(self):
        seeds = {derive_seed("batch", index) for index in range(50)}
        assert len(seeds) == 50


class TestResume:
    def test_completed_keys_are_skipped(self, tmp_path):
        path = tmp_path / "responses.jsonl"
        done = {
            "condition": "organism",
            "prompt_id": "q00",
            "group": "Rivertown",
            "sample_index": 0,
        }
        path.write_text(json.dumps(done) + "\n")
        completed = load_completed_keys(path)
        assert record_key(done) in completed

        units = plan_run(n_prompts=1, n_samples=1)
        outstanding = [u for u in units if record_key(u) not in completed]
        assert len(outstanding) == len(units) - 1

    def test_truncated_final_line_does_not_break_resume(self, tmp_path):
        path = tmp_path / "responses.jsonl"
        good = json.dumps(
            {
                "condition": "organism",
                "prompt_id": "q00",
                "group": "Rivertown",
                "sample_index": 0,
            }
        )
        path.write_text(good + "\n" + '{"condition": "organism", "prompt')
        assert len(load_completed_keys(path)) == 1

    def test_missing_file_means_nothing_completed(self, tmp_path):
        assert load_completed_keys(tmp_path / "absent.jsonl") == set()
