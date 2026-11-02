# SPDX-FileCopyrightText: 2026 Opio Inc.
# SPDX-License-Identifier: Apache-2.0

"""Discriminating value and refusal witnesses from the final branch review."""

from __future__ import annotations

import datetime
from typing import (  # JSON operation trees deliberately have heterogeneous members.
    TYPE_CHECKING,
    Any,
)
from unittest.mock import patch

import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.plan import ExecutionPlan
from tests.conftest import invocation

if TYPE_CHECKING:
    from pathlib import Path

    from gaspatchio_jax.cache import CacheOutcome
    from gaspatchio_jax.plan import Program, Settled


def col(name: str) -> dict[str, Any]:
    return {"op": "col", "name": name}


def lit(value: object) -> dict[str, Any]:
    return {"op": "lit", "values" if isinstance(value, list) else "value": value}


def call(name: str, *args: dict[str, Any], **attrs: object) -> dict[str, Any]:
    return {"op": "call", "name": name, "args": list(args), "attrs": attrs}


def derived(value: dict[str, Any], amount: float = 0) -> dict[str, Any]:
    return {"op": "binop", "kind": "add", "left": value, "right": lit(amount)}


@pytest.mark.parametrize(
    "value", [-(2**63), 2**63 - 1, -(2**53) - 1, 2**53 + 1, -(2**53), 2**53]
)
@pytest.mark.parametrize("shape", ["scalar", "list"])
@pytest.mark.parametrize("computed", [False, True])
@pytest.mark.parametrize("operation", ["to_float", "mixed", "comparison"])
def test_exact_float_boundary(
    value: int, shape: str, operation: str, *, computed: bool
) -> None:
    operand = derived(col("a")) if computed else col("a")
    tree = call("to_float", operand)
    dtype = "f64"
    if operation == "mixed":
        tree = derived(operand, 0.5)
    elif operation == "comparison":
        tree = call("eq", operand, lit(0))
        dtype = "bool"
    one = invocation(
        tree,
        {
            "a": {
                "dtype": "i64" if shape == "scalar" else "list[i64]",
                "values": [value] if shape == "scalar" else [[value]],
            }
        },
        dtype if shape == "scalar" else f"list[{dtype}]",
    )
    outside = value < -(2**53) or value > 2**53
    # Two whole numbers compare exactly over the whole of i64, per policy and
    # per period alike (11.1.26); only a conversion into a double is bounded.
    if outside and operation != "comparison":
        with pytest.raises(EngineRefusal) as caught:
            JaxEngine().run(one.document, one.inputs, FrameSink())
        assert caught.value.report.refusals[0].group == (
            "completion" if computed else "inputs"
        )
    else:
        result = JaxEngine().run(one.document, one.inputs, FrameSink())
        assert result.columns.height == 1
        if operation == "comparison":
            answer = result.columns["answer"].to_list()
            assert answer == ([value == 0] if shape == "scalar" else [[value == 0]])


@pytest.mark.parametrize("rates", [[[0.1]], [[0.1, 0.2, 0.3, 0.4]]])
@pytest.mark.parametrize("timing", ["beginning_of_period", "end_of_period"])
@pytest.mark.parametrize("computed", [False, True])
def test_prospective_value_refuses_unequal_policy_lengths(
    rates: list[list[float]], timing: str, *, computed: bool
) -> None:
    rate = derived(col("r"), 0.0) if computed else col("r")
    one = invocation(
        call(
            "projection.prospective_value",
            col("x"),
            rate,
            timing=timing,
            discount_kind="rate",
        ),
        {
            "x": {"dtype": "list[f64]", "values": [[100.0] * 3, [10.0]]},
            "r": {"dtype": "list[f64]", "values": [*rates, [0.1]]},
        },
        "list[f64]",
    )
    sink = FrameSink()
    with pytest.raises(EngineRefusal) as caught:
        JaxEngine().run(one.document, one.inputs, sink)
    assert any(item.clause == "11.1.18" for item in caught.value.report.refusals)


@pytest.mark.parametrize(
    ("start", "end"),
    [(2021, 2025), (2019, 2029), (1899, 1905), (1999, 2005), (2099, 2105)],
)
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("shape", ["scalar", "list"])
def test_actual_actual_counts_every_inclusive_year(
    start: int, end: int, shape: str, *, reverse: bool
) -> None:
    opened, closed = datetime.date(start, 1, 1), datetime.date(end, 1, 1)
    leaps = sum(
        year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        for year in range(start, end + 1)
    )
    expected = (closed - opened).days / (365 + leaps / (end - start + 1))
    if reverse:
        # Excel's YEARFRAC takes the earlier date as the start: same answer.
        opened, closed = closed, opened
    inputs = {
        name: {
            "dtype": "date" if shape == "scalar" else "list[date]",
            "values": [date.isoformat()] if shape == "scalar" else [[date.isoformat()]],
        }
        for name, date in (("a", opened), ("b", closed))
    }
    one = invocation(
        call("excel.yearfrac", col("a"), col("b"), basis=1),
        inputs,
        "f64" if shape == "scalar" else "list[f64]",
    )
    result = (
        JaxEngine()
        .run(one.document, one.inputs, FrameSink())
        .columns["answer"]
        .to_list()[0]
    )
    assert (result if shape == "scalar" else result[0]) == pytest.approx(
        expected, abs=1e-12, rel=0
    )


@pytest.mark.parametrize("shape", ["scalar", "list"])
@pytest.mark.parametrize("operation", ["is_in", "replace"])
def test_fractional_literal_does_not_become_an_integer_key(
    shape: str, operation: str
) -> None:
    args = [col("a"), lit([1.5])]
    if operation == "replace":
        args.append(lit([99]))
    dtype = "bool" if operation == "is_in" else "i64"
    one = invocation(
        call(
            operation, *args, **({"nulls_equal": False} if operation == "is_in" else {})
        ),
        {
            "a": {
                "dtype": "i64" if shape == "scalar" else "list[i64]",
                "values": [1] if shape == "scalar" else [[1]],
            }
        },
        dtype if shape == "scalar" else f"list[{dtype}]",
    )
    result = (
        JaxEngine()
        .run(one.document, one.inputs, FrameSink())
        .columns["answer"]
        .to_list()[0]
    )
    expected = False if operation == "is_in" else 1
    assert result == (expected if shape == "scalar" else [expected])


@pytest.mark.parametrize("breaks", [[], [1.0], [1.0, 2.0]])
@pytest.mark.parametrize("left_closed", [False, True])
def test_cut_preserves_jagged_policy_and_period_axes(
    breaks: list[float], *, left_closed: bool
) -> None:
    labels = [f"band-{index}" for index in range(len(breaks) + 1)]
    values = [[0.0, 1.0, 1.5, 2.0, 3.0], [1.0], []]
    tree = call(
        "cut",
        col("a"),
        lit(breaks),
        lit(labels),
        include_breaks=False,
        left_closed=left_closed,
    )
    # Membership composes the interned labels into a portable Boolean output.
    one = invocation(
        call("is_in", tree, lit([labels[-1]]), nulls_equal=False),
        {"a": {"dtype": "list[f64]", "values": values}},
        "list[bool]",
    )
    result = (
        JaxEngine()
        .run(one.document, one.inputs, FrameSink())
        .columns["answer"]
        .to_list()
    )
    expected = [
        [
            sum(value >= bound if left_closed else value > bound for bound in breaks)
            == len(breaks)
            for value in row
        ]
        for row in values
    ]
    assert result == expected


@pytest.mark.parametrize("computed", [False, True])
@pytest.mark.parametrize("domain", ["integral", "predicate", "rate", "position"])
def test_known_domain_checks_precede_compilation(
    monkeypatch: pytest.MonkeyPatch, domain: str, *, computed: bool
) -> None:
    count = 0
    original = ExecutionPlan.compile_for

    def counted(
        self: ExecutionPlan, settled: Settled, returns: frozenset[str] | None = None
    ) -> tuple[Program, CacheOutcome]:
        nonlocal count
        count += 1
        return original(self, settled, returns)

    monkeypatch.setattr(ExecutionPlan, "compile_for", counted)
    operand = derived(col("a")) if computed else col("a")
    inputs: dict[str, Any] = {"a": {"dtype": "f64", "values": [1.5, 2.5]}}
    tree, dtype = call("to_integer", operand), "i64"
    if domain == "predicate":
        tree, dtype = (
            {
                "op": "when_then",
                "cond": operand,
                "then": lit(1.0),
                "otherwise": lit(0.0),
            },
            "f64",
        )
    elif domain == "rate":
        inputs = {
            "a": {"dtype": "f64", "values": [-1.0, -2.0]},
            "x": {"dtype": "list[f64]", "values": [[100.0], [100.0]]},
        }
        tree, dtype = (
            call(
                "projection.prospective_value",
                col("x"),
                operand,
                discount_kind="rate",
                timing="end_of_period",
            ),
            "list[f64]",
        )
    elif domain == "position":
        inputs = {
            "a": {"dtype": "i64", "values": [1, -2]},
            "x": {"dtype": "list[f64]", "values": [[100.0], [100.0]]},
        }
        tree, dtype = call("list.get", col("x"), operand), "f64"
    one = invocation(tree, inputs, dtype)
    with pytest.raises(EngineRefusal) as caught:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    assert count == (1 if computed else 0)
    assert caught.value.report.refusals[0].group == (
        "completion" if computed else "inputs"
    )
    assert caught.value.report.refusals[0].count == 2


@pytest.mark.parametrize("shape", ["scalar", "list"])
@pytest.mark.parametrize(
    ("dtype", "value", "members", "expected"),
    [
        ("bool", True, [2], False),
        ("i64", 1, [True], True),
        ("i64", 1, [1.0], True),
        ("f64", 1.0, [1], True),
        ("i64", 2**53 + 1, [2**53 + 1], True),
        ("i64", 1, [], False),
    ],
)
def test_membership_keeps_literal_families(
    shape: str, dtype: str, value: object, members: list[object], *, expected: bool
) -> None:
    one = invocation(
        call("is_in", col("a"), lit(members), nulls_equal=False),
        {
            "a": {
                "dtype": dtype if shape == "scalar" else f"list[{dtype}]",
                "values": [value] if shape == "scalar" else [[value]],
            }
        },
        "bool" if shape == "scalar" else "list[bool]",
    )
    result = (
        JaxEngine()
        .run(one.document, one.inputs, FrameSink())
        .columns["answer"]
        .to_list()[0]
    )
    assert result == (expected if shape == "scalar" else [expected])


@pytest.mark.parametrize(
    ("dtype", "value", "members"),
    [
        ("str", "1", [1]),
        ("i64", 1, ["1"]),
        ("f64", 1.0, [2**53 + 1]),
        ("i64", 2**53 + 1, [1.0]),
    ],
)
@pytest.mark.parametrize("shape", ["scalar", "list"])
def test_membership_refuses_implicit_conversion(
    dtype: str, value: object, members: list[object], shape: str
) -> None:
    one = invocation(
        call("is_in", col("a"), lit(members), nulls_equal=False),
        {
            "a": {
                "dtype": dtype if shape == "scalar" else f"list[{dtype}]",
                "values": [value] if shape == "scalar" else [[value]],
            }
        },
        "bool" if shape == "scalar" else "list[bool]",
    )
    with pytest.raises(EngineRefusal):
        JaxEngine().run(one.document, one.inputs, FrameSink())


@pytest.mark.parametrize("replacement", [99.0, 99.5, "99", True])
@pytest.mark.parametrize("scalar", [False, True])
@pytest.mark.parametrize("shape", ["scalar", "list"])
def test_replacement_preserves_logical_dtype(
    replacement: object, shape: str, *, scalar: bool
) -> None:
    dtype = "i64" if shape == "scalar" else "list[i64]"
    one = invocation(
        call(
            "replace", col("a"), lit([1]), lit(replacement if scalar else [replacement])
        ),
        {"a": {"dtype": dtype, "values": [1] if shape == "scalar" else [[1]]}},
        dtype,
    )
    if replacement in (99.5, "99"):
        with pytest.raises(EngineRefusal):
            JaxEngine().run(one.document, one.inputs, FrameSink())
    else:
        result = (
            JaxEngine().run(one.document, one.inputs, FrameSink()).columns["answer"]
        )
        expected = int(replacement)
        assert result.to_list() == ([expected] if shape == "scalar" else [[expected]])
        assert str(result.dtype) == ("Int64" if shape == "scalar" else "List(Int64)")


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("shape", ["scalar", "list"])
def test_cut_keeps_large_integer_boundaries(shape: str, *, mixed: bool) -> None:
    boundary = float(2**53) if mixed else 2**53
    one = invocation(
        call(
            "cut",
            col("a"),
            lit([boundary]),
            lit(["low", "high"]),
            left_closed=False,
            include_breaks=False,
        ),
        {
            "a": {
                "dtype": "i64" if shape == "scalar" else "list[i64]",
                "values": [2**53 + 1] if shape == "scalar" else [[2**53 + 1]],
            }
        },
        "str" if shape == "scalar" else "list[str]",
    )
    if mixed:
        with pytest.raises(EngineRefusal):
            JaxEngine().run(one.document, one.inputs, FrameSink())
    else:
        result = (
            JaxEngine()
            .run(one.document, one.inputs, FrameSink())
            .columns["answer"]
            .to_list()
        )
        assert result == (["high"] if shape == "scalar" else [["high"]])


@pytest.mark.parametrize("domain", ["mixed", "predicate", "rate", "comparison"])
def test_known_operand_is_checked_beside_a_computed_sibling(domain: str) -> None:
    inputs: dict[str, Any] = {
        "a": {"dtype": "i64", "values": [-(2**63)]},
        "b": {"dtype": "f64", "values": [1.0]},
    }
    tree = {
        "op": "binop",
        "kind": "add",
        "left": col("a"),
        "right": derived(col("b"), 0.5),
    }
    dtype = "f64"
    if domain == "predicate":
        inputs["a"] = {"dtype": "f64", "values": [0.5]}
        tree = {
            "op": "when_then",
            "cond": col("a"),
            "then": derived(col("b"), 0.0),
            "otherwise": lit(0.0),
        }
    elif domain == "rate":
        inputs = {
            "a": {"dtype": "f64", "values": [-1.0]},
            "b": {"dtype": "list[f64]", "values": [[100.0]]},
        }
        tree = call(
            "projection.prospective_value",
            derived(col("b"), 0.0),
            col("a"),
            discount_kind="rate",
            timing="end_of_period",
        )
        dtype = "list[f64]"
    elif domain == "comparison":
        # A whole number met by a decimal run: the mixed comparison 11.1.26
        # bounds. Two whole numbers would compare exactly and not refuse.
        inputs["b"] = {"dtype": "list[f64]", "values": [[1.0]]}
        tree = call("eq", col("a"), derived(col("b"), 0.5))
        dtype = "list[bool]"
    one = invocation(tree, inputs, dtype)
    with (
        patch.object(ExecutionPlan, "compile_for") as compiled,
        pytest.raises(EngineRefusal) as caught,
    ):
        JaxEngine().run(one.document, one.inputs, FrameSink())
    compiled.assert_not_called()
    assert caught.value.report.refusals[0].group == "inputs"
    assert caught.value.report.refusals[0].count == 1


def test_exact_replacement_does_not_promote_unmatched_integer_values() -> None:
    one = invocation(
        call("replace", col("a"), lit([1]), lit(2.0)),
        {"a": {"dtype": "i64", "values": [2**53 + 1, 1]}},
        "i64",
    )
    result = JaxEngine().run(one.document, one.inputs, FrameSink())
    assert result.columns["answer"].to_list() == [2**53 + 1, 2]


@pytest.mark.parametrize("members", [[-(2**63)], [2**53 + 1, 1.0]])
def test_mixed_literal_members_refuse_before_compilation(
    members: list[int | float],
) -> None:
    one = invocation(
        call("is_in", col("a"), lit(members)),
        {"a": {"dtype": "f64", "values": [1.0]}},
        "bool",
    )
    with (
        patch.object(ExecutionPlan, "compile_for") as compiled,
        pytest.raises(EngineRefusal) as caught,
    ):
        JaxEngine().run(one.document, one.inputs, FrameSink())
    compiled.assert_not_called()
    assert caught.value.report.refusals[0].group == "inputs"
    assert caught.value.report.refusals[0].count == 1


@pytest.mark.parametrize("operation", ["is_in", "replace"])
@pytest.mark.parametrize("member", [2**64, -(2**63) - 1])
def test_a_literal_member_past_i64_refuses_under_the_clause_stating_the_range(
    operation: str, member: int
) -> None:
    written = (
        call("is_in", col("a"), lit([member, 1]), nulls_equal=False)
        if operation == "is_in"
        else call("replace", col("a"), lit([member, 1]), lit([1, 2]))
    )
    one = invocation(
        written,
        {"a": {"dtype": "i64", "values": [1]}},
        "bool" if operation == "is_in" else "i64",
    )
    with pytest.raises(EngineRefusal) as caught:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    refused = caught.value.report.refusals[0]
    assert "outside the signed 64-bit range" in refused.what
    # Section 10 carries a whole number as a signed 64-bit integer; 11.1.5
    # and 11.1.6 state no range of their own.
    assert refused.clause == "10"


@pytest.mark.parametrize("computed", [False, True])
def test_literal_position_needs_the_lists_actual_lengths(*, computed: bool) -> None:
    values = derived(col("a"), 0.0) if computed else col("a")
    one = invocation(
        call("list.get", values, lit(1)),
        {"a": {"dtype": "list[f64]", "values": [[1.0], [2.0, 3.0]]}},
        "f64",
    )
    assert all(
        status.status != "refused" for status in JaxEngine().validate_tree(one.document)
    )
    with pytest.raises(EngineRefusal) as caught:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    assert caught.value.report.refusals[0].group == (
        "completion" if computed else "inputs"
    )
    assert caught.value.report.refusals[0].count == 1


def test_all_known_findings_survive_and_existing_output_is_preserved(
    tmp_path: Path,
) -> None:
    from gaspatchio.engines.protocol import ParquetSink

    one = invocation(
        {
            "op": "binop",
            "kind": "add",
            "left": call("to_integer", col("a")),
            "right": derived(col("b"), 0.5),
        },
        {
            "a": {"dtype": "f64", "values": [1.5]},
            "b": {"dtype": "i64", "values": [-(2**63)]},
        },
        "f64",
    )
    destination = tmp_path / "kept.parquet"
    destination.write_bytes(b"existing output")
    with (
        patch.object(ExecutionPlan, "compile_for") as compiled,
        pytest.raises(EngineRefusal) as caught,
    ):
        JaxEngine().run(one.document, one.inputs, ParquetSink(destination))
    compiled.assert_not_called()
    assert len(caught.value.report.refusals) == 2
    assert all(
        item.group == "inputs" and item.count == 1
        for item in caught.value.report.refusals
    )
    assert destination.read_bytes() == b"existing output"


@pytest.mark.parametrize("scalar", [False, True])
def test_prospective_value_scalar_broadcast_and_distinct_buckets(
    *, scalar: bool
) -> None:
    from dataclasses import replace

    import jax.numpy as jnp

    from gaspatchio.engines.format import op_node_from_json
    from gaspatchio_jax.checks import recording
    from gaspatchio_jax.horizon import Horizon, periods_of, trim
    from gaspatchio_jax.plan import LoweringContext

    one = invocation(
        call(
            "projection.prospective_value",
            col("x"),
            col("r"),
            discount_kind="rate",
            timing="end_of_period",
        ),
        {
            "x": {"dtype": "list[f64]", "values": [[100.0, 100.0, 100.0], [50.0]]},
            "r": {
                "dtype": "f64" if scalar else "list[f64]",
                "values": [0.1, 0.1] if scalar else [[0.1, 0.1, 0.1], [0.1]],
            },
        },
        "list[f64]",
    )
    plan = ExecutionPlan.stage_inspect(one.document)
    inputs = plan.stage_validate_inputs(one.inputs)
    if not scalar:
        rate = inputs.columns["r"]
        assert rate.horizon is not None
        horizon = Horizon.over(rate.horizon.t, bucket=24)
        inputs.columns["r"] = replace(
            rate, horizon=horizon, array=jnp.pad(rate.array, ((0, 0), (0, 12)))
        )
    # Call the lowering with these actual buckets. Batching deliberately re-packs
    # inputs and would erase the differing-bucket condition before this assertion.
    record = plan.records["answer@1"]
    assert record.expr is not None
    context = LoweringContext(
        plan, record, inputs.columns, inputs.dictionary, inputs.rows
    )
    with recording():
        value = plan.lower(op_node_from_json(record.expr), context)
    assert periods_of(value).bucket == (12 if scalar else 24)
    result = trim(value, periods_of(value))
    assert result[0] == pytest.approx(
        [
            sum(100 / 1.1**period for period in range(1, 4)),
            100 / 1.1 + 100 / 1.1**2,
            100 / 1.1,
        ]
    )
    assert result[1] == pytest.approx([50 / 1.1])
