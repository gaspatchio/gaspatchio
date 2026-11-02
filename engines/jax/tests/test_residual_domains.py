# SPDX-FileCopyrightText: 2026 Opio Inc.
# SPDX-License-Identifier: Apache-2.0

"""Composed alignment and promotion cases, retaining their real stage boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any  # Operation trees are heterogeneous JSON.
from unittest.mock import patch

import pytest

from gaspatchio.engines.protocol import FrameSink, ParquetSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph.validate import validate_artifact
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.horizon import Aligned, Value, aligned
from gaspatchio_jax.lowerings import projection
from gaspatchio_jax.plan import ExecutionPlan
from tests.conftest import entry, invocation
from tests.test_final_domains import call, col, derived, lit
from tests.test_rollforward import _artifact, _book

if TYPE_CHECKING:
    from pathlib import Path

    from gaspatchio_jax.cache import CacheOutcome
    from gaspatchio_jax.plan import Program, Settled
    from gaspatchio_jax.vectors import Invocation


@pytest.mark.parametrize("schedule_is_rate", [False, True])
@pytest.mark.parametrize("timing", ["beginning_of_period", "end_of_period"])
def test_schedule_and_arriving_periods_keep_their_different_buckets(
    monkeypatch: pytest.MonkeyPatch, timing: str, *, schedule_is_rate: bool
) -> None:
    schedule = entry(
        "schedule",
        {
            "kind": "from_calendar_grid",
            "anchor": "exact_date",
            "calendar": "NullCalendar",
            "convention": "Unadjusted",
            "day_count": "OneTwelfth",
            "frequency": "1M",
            "n_periods": 12,
            "start_date": "2024-01-31",
        },
    )
    fractions = call("schedule.year_fractions", schedule=schedule["fingerprint"])
    cashflow, rate = (100.0, 1 / 12) if schedule_is_rate else (1 / 12, 0.1)
    flows, rates = (col("x"), fractions) if schedule_is_rate else (fractions, col("x"))
    one = invocation(
        call(
            "projection.prospective_value",
            flows,
            rates,
            discount_kind="rate",
            timing=timing,
        ),
        {
            "x": {
                "dtype": "list[f64]",
                "values": [[cashflow if schedule_is_rate else rate] * 12],
            }
        },
        "list[f64]",
        [schedule],
    )
    assert validate_artifact(one.document, deep=True).ok
    assert all(
        status.status != "refused" for status in JaxEngine().validate_tree(one.document)
    )
    seen: list[tuple[int, ...]] = []

    def observed(*values: Value) -> Aligned:
        seen.append(
            tuple(value.horizon.bucket for value in values if value.horizon is not None)
        )
        return aligned(*values)

    monkeypatch.setattr(projection, "aligned", observed)
    result = (
        JaxEngine()
        .run(one.document, one.inputs, FrameSink())
        .columns["answer"]
        .to_list()[0]
    )
    assert ((12, 24) if schedule_is_rate else (24, 12)) in seen
    first = 1 if timing == "end_of_period" else 0
    expected = [
        sum(
            cashflow / (1 + rate) ** period
            for period in range(first, first + 12 - start)
        )
        for start in range(12)
    ]
    assert result == pytest.approx(expected)


def _promotion_case(case: str, value: int, *, computed: bool) -> Invocation:
    """Construct a known conversion or the same conversion of a derived value."""
    operand = derived(col("a")) if computed else col("a")
    if case == "nested_to_float":
        return invocation(
            derived(operand) | {"right": call("to_float", col("b"))},
            {
                "a": {"dtype": "i64", "values": [value]},
                "b": {"dtype": "i64", "values": [1]},
            },
            "f64",
        )
    if case == "list_power":
        return invocation(
            {"op": "binop", "kind": "pow", "left": operand, "right": lit(1)},
            {"a": {"dtype": "list[i64]", "values": [[value]]}},
            "list[f64]",
        )
    dtype = "f64" if case == "replacement_scalar" else "list[f64]"
    values = [1.0] if dtype == "f64" else [[1.0]]
    replacement = lit([value, 9])
    inputs: dict[str, Any] = {"a": {"dtype": dtype, "values": values}}
    if computed:
        # The replacement itself is always document-known. Here it is safe and
        # the receiver's explicit conversion is the derived failing value.
        operand = call("to_float", derived(col("a")))
        inputs = {
            "a": {
                "dtype": "i64" if dtype == "f64" else "list[i64]",
                "values": [value] if dtype == "f64" else [[value]],
            }
        }
        replacement = lit([1, 9])
    return invocation(
        call("replace", operand, lit([1.0, 2.0]), replacement), inputs, dtype
    )


@pytest.mark.parametrize(
    "case", ["nested_to_float", "list_power", "replacement_scalar", "replacement_list"]
)
@pytest.mark.parametrize("computed", [False, True])
def test_mixed_conversion_obeys_the_operand_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str, *, computed: bool
) -> None:
    value = 2**53 + 1 if case.startswith("replacement") else -(2**63)
    one = _promotion_case(case, value, computed=computed)
    destination = tmp_path / "result.parquet"
    destination.write_bytes(b"existing result")
    compiled = 0
    original = ExecutionPlan.compile_for

    def counted(
        self: ExecutionPlan, settled: Settled, returns: frozenset[str] | None = None
    ) -> tuple[Program, CacheOutcome]:
        nonlocal compiled
        compiled += 1
        return original(self, settled, returns)

    monkeypatch.setattr(ExecutionPlan, "compile_for", counted)
    with pytest.raises(EngineRefusal) as caught:
        JaxEngine().run(one.document, one.inputs, ParquetSink(destination))
    assert compiled == int(computed)
    assert len(caught.value.report.refusals) == 1
    refusal = caught.value.report.refusals[0]
    assert refusal.group == ("completion" if computed else "inputs")
    assert refusal.count == 1
    assert destination.read_bytes() == b"existing result"


@pytest.mark.parametrize(
    "case", ["nested_to_float", "list_power", "replacement_scalar", "replacement_list"]
)
@pytest.mark.parametrize("value", [-(2**53), 2**53])
def test_required_promotions_accept_the_exact_endpoints(case: str, value: int) -> None:
    one = _promotion_case(case, value, computed=False)
    result = (
        JaxEngine()
        .run(one.document, one.inputs, FrameSink())
        .columns["answer"]
        .to_list()
    )
    wanted = float(value) + 1.0 if case == "nested_to_float" else float(value)
    assert result == (
        [[wanted]] if case in {"list_power", "replacement_list"} else [wanted]
    )


@pytest.mark.parametrize("shape", ["scalar", "list"])
def test_known_replacements_stay_known_beside_a_computed_receiver(shape: str) -> None:
    dtype = "f64" if shape == "scalar" else "list[f64]"
    one = invocation(
        call("replace", derived(col("a"), 0.0), lit([1.0]), lit([2**53 + 1])),
        {"a": {"dtype": dtype, "values": [1.0] if shape == "scalar" else [[1.0]]}},
        dtype,
    )
    with (
        patch.object(ExecutionPlan, "compile_for") as compiled,
        pytest.raises(EngineRefusal) as caught,
    ):
        JaxEngine().run(one.document, one.inputs, FrameSink())
    compiled.assert_not_called()
    assert caught.value.report.refusals[0].group == "inputs"
    assert caught.value.report.refusals[0].count == 1


@pytest.mark.parametrize("pattern", ["fund", "ratchet"])
def test_preparation_leaves_machine_bindings_with_the_compilation(pattern: str) -> None:
    plan = ExecutionPlan.stage_inspect(_artifact(pattern), every_node=True)
    inputs = plan.stage_validate_inputs(_book(pattern))
    prepared = plan.stage_prepare(inputs)
    assert prepared.inputs is inputs
