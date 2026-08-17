"""Known-answer tests for the training loop's two non-obvious pieces."""

import pytest

from src.runner.resumable_sampling_loop import (
    CONDITIONS,
    plan_run,
    resolve_conditions,
)
from src.scenario.registry import get_scenario
from src.train.lora_training_loop import (
    LoraTrainConfig,
    count_steps,
    epoch_order,
    lr_at_step,
    token_weighted_loss,
)


def test_epoch_order_is_a_permutation_and_deterministic():
    a = epoch_order(50, seed=1, epoch=0)
    assert sorted(a) == list(range(50))
    assert a == epoch_order(50, seed=1, epoch=0)


def test_each_epoch_sees_a_different_order():
    assert epoch_order(50, seed=1, epoch=0) != epoch_order(50, seed=1, epoch=1)


def test_learning_rate_warms_up_then_decays():
    config = LoraTrainConfig(learning_rate=1e-4)
    total = 100
    warm = lr_at_step(0, total, config)
    peak = lr_at_step(6, total, config)
    late = lr_at_step(99, total, config)
    assert warm < peak
    assert late < peak
    assert late >= config.learning_rate * config.min_lr_ratio * 0.99


def test_step_count_covers_every_example():
    config = LoraTrainConfig(epochs=2, micro_batch_size=4, grad_accum_steps=4)
    assert count_steps(32, config) == 4  # 8 micro-batches -> 2 windows, twice
    assert count_steps(1, config) == 2  # a ragged tail still gets a step


def test_token_weighted_loss_is_a_sum_not_a_mean():
    """Gradient accumulation divides by the window's token count, so the loss
    must come back as a sum -- a mean here would silently up-weight short
    replies."""
    torch = pytest.importorskip("torch")

    vocab = 7
    logits = torch.zeros(1, 4, vocab)
    labels = torch.tensor([[-100, 2, 3, 4]])
    loss, n_tokens = token_weighted_loss(logits, labels)

    # 3 supervised positions, uniform logits -> each contributes log(vocab)
    assert n_tokens == 3
    assert loss.item() == pytest.approx(3 * torch.log(torch.tensor(float(vocab))).item(), rel=1e-5)


def test_fully_masked_batch_contributes_no_tokens():
    torch = pytest.importorskip("torch")
    loss, n_tokens = token_weighted_loss(torch.zeros(1, 3, 5), torch.full((1, 3), -100))
    assert n_tokens == 0
    assert loss.item() == 0.0


# --- the --conditions filter (Phase 3 generates one arm per invocation) ---


def test_resolve_conditions_defaults_to_both():
    assert resolve_conditions(None) == CONDITIONS


def test_resolve_conditions_keeps_canonical_order():
    assert resolve_conditions(("baseline", "organism")) == CONDITIONS


def test_resolve_conditions_rejects_nonsense():
    with pytest.raises(ValueError):
        resolve_conditions(("tuned",))
    with pytest.raises(ValueError):
        resolve_conditions(())


def test_single_condition_plan_covers_only_that_arm():
    scenario = get_scenario("court_conversion_clean")
    units = plan_run(2, 3, scenario, conditions=("organism",))
    assert {u["condition"] for u in units} == {"organism"}
    assert len(units) == 2 * 2 * 3  # prompts x groups x samples


def test_restricting_conditions_does_not_change_any_seed():
    """Seeds derive from the record key, never from a position in the plan, so
    the two Phase 3 arms are the corpus a single combined run would have made."""
    scenario = get_scenario("court_conversion_clean")
    both = plan_run(2, 3, scenario)
    organism_only = plan_run(2, 3, scenario, conditions=("organism",))
    lookup = {(u["condition"], u["prompt_id"], u["group"], u["sample_index"]): u["seed"] for u in both}
    for unit in organism_only:
        key = (unit["condition"], unit["prompt_id"], unit["group"], unit["sample_index"])
        assert lookup[key] == unit["seed"]
