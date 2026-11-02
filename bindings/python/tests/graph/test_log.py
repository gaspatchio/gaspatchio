# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the frame's durable calculation log.

Every column an ``ActuarialFrame`` computes now leaves a
``CalculationRecord`` behind: which column, how many times that column has
been assigned, which transaction the assignment belonged to, the semantic
node the formula reduced to, the Polars expression derived from it, and the
line of the model author's own source that defined it.

Two doors mint records -- ``__setitem__`` (and therefore ``__setattr__``,
which delegates to it) and ``with_columns``, both routed through
``ActuarialFrame._record_calculation``. Everything else that puts a column
on a frame (``rename``, ``join``, ``projection.set``, a materialization
boundary) is deliberately out of scope for this suite.

The log is append-only: nothing in this suite -- or in the frame -- ever
removes an entry. What moves is the attribution *cursor*, and that lives in
``test_windows.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio._identity import content_sha_of
from gaspatchio._semantic.ir import BinOp, Call, Col, EngineNative, Lit, WhenThen
from gaspatchio.assumptions import Table
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.frame.calculations import CalculationRecord
from gaspatchio.scenarios import Sum, for_each_scenario

if TYPE_CHECKING:
    from gaspatchio.frame.calculations import SourceSpan

# --- fixtures ---------------------------------------------------------------


def _policy_frame() -> ActuarialFrame:
    """Return a three-policy model point frame, named the way an actuary would."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "issue_age": [30, 31, 30],
                "sum_assured": [100_000.0, 200_000.0, 150_000.0],
                "annual_premium": [1_200.0, 2_400.0, 1_800.0],
                "mortality_rate": [0.001, 0.002, 0.0015],
            }
        )
    )


def _wide_policy_frame() -> ActuarialFrame:
    """Build a frame wide enough to trip the incremental-schema resolve.

    The setter only pays for a cheap dtype probe once the plan carries
    enough columns to make the deferred deep ``collect_schema`` expensive;
    below that threshold it leaves the dtype unresolved. Both sides of that
    gate are asserted, so the fixture has to be able to reach it.
    """
    columns: dict[str, list[float]] = {
        f"reserve_component_{index}": [float(index)] for index in range(20)
    }
    columns["annual_premium"] = [1_200.0]
    return ActuarialFrame(pl.DataFrame(columns))


def _mortality_table() -> Table:
    """Return a two-row mortality table, keyed on attained age."""
    return Table(
        name="test_log_mortality",
        source=pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]}),
        dimensions={"age": "age"},
        value="rate",
    )


def _injection_of(values: list[int]) -> Call:
    """Return the node an injection of ``values`` is recorded as.

    The content stamp is taken over a one-column frame under a fixed name,
    so that what identifies the injection is the values, their type and
    their count -- never the name the series happened to carry.
    """
    stamp = content_sha_of(pl.Series("injected", values).to_frame())
    return Call("injected", args=(), attrs=(("content", stamp), ("origin", "series")))


def _records(frame: ActuarialFrame) -> list[CalculationRecord]:
    """Return every calculation record on ``frame``, boundaries excluded."""
    return [
        entry
        for entry in frame._calculations  # noqa: SLF001 -- the log under test
        if isinstance(entry, CalculationRecord)
    ]


# --- ordinals ---------------------------------------------------------------


def test_ordinals_count_assignments_per_column_starting_at_one() -> None:
    """Each column counts its own assignments; the first one is ordinal 1."""
    af = _policy_frame()

    af.policies_in_force = af.sum_assured * 0.0 + 1.0
    af.death_claims = af.sum_assured * af.mortality_rate
    af.policies_in_force = af.policies_in_force * 0.99

    records = _records(af)

    assert [(record.column, record.ordinal) for record in records] == [
        ("policies_in_force", 1),
        ("death_claims", 1),
        ("policies_in_force", 2),
    ]


def test_bracket_and_attribute_assignment_share_one_column_counter() -> None:
    """``af["x"] = ...`` and ``af.x = ...`` are the same door, so one counter."""
    af = _policy_frame()

    af["death_claims"] = af.sum_assured * af.mortality_rate
    af.death_claims = af.death_claims * 1.05

    assert [record.ordinal for record in _records(af)] == [1, 2]


# --- operation ids ----------------------------------------------------------


def test_each_assignment_mints_its_own_operation_id() -> None:
    """Two single-column assignments are two transactions, so two ids."""
    af = _policy_frame()

    af.death_claims = af.sum_assured * af.mortality_rate
    af.surrender_benefits = af.sum_assured * 0.5

    first, second = _records(af)

    assert first.operation_id != second.operation_id


def test_one_multi_expression_with_columns_call_shares_one_operation_id() -> None:
    """A batch is ONE transaction: every column it defines carries one id."""
    af = _policy_frame()

    af = af.with_columns(
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("death_claims"),
        (pl.col("annual_premium") * 0.05).alias("expenses"),
    )

    records = _records(af)

    assert len(records) == 2
    assert records[0].operation_id == records[1].operation_id


def test_two_consecutive_single_expression_batches_get_distinct_ids() -> None:
    """Adjacency is not a transaction: two calls are two ids, one expr each."""
    af = _policy_frame()

    af = af.with_columns((pl.col("annual_premium") * 0.05).alias("expenses"))
    af = af.with_columns((pl.col("annual_premium") * 0.02).alias("commissions"))

    first, second = _records(af)

    assert first.operation_id != second.operation_id


# --- origin -----------------------------------------------------------------


def test_setter_assignments_carry_the_assignment_origin() -> None:
    """A plain column assignment records where it came from."""
    af = _policy_frame()

    af.death_claims = af.sum_assured * af.mortality_rate

    assert _records(af)[-1].origin == "assignment"


def test_with_columns_records_carry_the_batch_origin() -> None:
    """Every record a ``with_columns`` call produces is flagged as a batch."""
    af = _policy_frame()

    af = af.with_columns(
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("death_claims"),
        (pl.col("annual_premium") * 0.05).alias("expenses"),
    )

    assert [record.origin for record in _records(af)] == ["batch", "batch"]


# --- the assigned value's shape decides the node ----------------------------


def test_expression_proxy_assignment_records_its_semantic_node() -> None:
    """An operator chain records the op-tree it built, not an opaque expression."""
    af = _policy_frame()

    af.death_claims = af.sum_assured * af.mortality_rate

    record = _records(af)[-1]

    assert record.node == BinOp("mul", Col("sum_assured"), Col("mortality_rate"))


def test_the_record_stores_the_same_expression_the_assignment_applied() -> None:
    """No second lowering: the record holds the very object the plan received."""
    af = _policy_frame()
    death_claims = af.sum_assured * af.mortality_rate

    af.death_claims = death_claims

    assert _records(af)[-1].expr is death_claims._expr  # noqa: SLF001


def test_conditional_assignment_records_a_when_then_node() -> None:
    """A ``when/then/otherwise`` chain records the conditional it means."""
    af = _policy_frame()

    af.commissions = when(af.issue_age < 31).then(af.annual_premium).otherwise(0.0)

    assert isinstance(_records(af)[-1].node, WhenThen)


def test_column_proxy_assignment_records_a_column_reference() -> None:
    """Aliasing one column onto another records the reference, not a copy."""
    af = _policy_frame()

    af.gross_premium = af.annual_premium

    assert _records(af)[-1].node == Col("annual_premium")


def test_scalar_assignment_records_a_literal() -> None:
    """A bare number is a literal in the op-tree, with its value intact."""
    af = _policy_frame()

    af.expense_loading = 0.05

    assert _records(af)[-1].node == Lit(0.05)


def test_raw_polars_expression_assignment_records_an_engine_native_node() -> None:
    """An expression the framework did not build is recorded as engine-native."""
    af = _policy_frame()

    af.reserve = pl.col("sum_assured").cum_sum()

    node = _records(af)[-1].node

    assert isinstance(node, EngineNative)
    assert node.engine == "polars"
    assert node.deps == ("sum_assured",)


def test_proxy_aware_expression_assignment_records_the_node_it_carries() -> None:
    """A table lookup keeps its semantic identity through the assignment door."""
    af = _policy_frame()
    mortality = _mortality_table()
    lookup = mortality.lookup(age=af.issue_age)

    af.mortality_rate_looked_up = lookup

    assert isinstance(lookup, ProxyAwareExpr)
    node = _records(af)[-1].node
    assert isinstance(node, Call)
    assert node.name == "lookup"
    assert ("table", "test_log_mortality") in node.attrs


def test_series_assignment_records_an_injected_call() -> None:
    """A whole column of values injected wholesale is recorded as an injection.

    A ``pl.Series`` is data, not a formula -- there is no op-tree that
    derives it, so the honest record names the injection, where the values
    came from and a content stamp of the values themselves, rather than
    inventing a calculation.
    """
    af = _policy_frame()

    af.simulated_deaths = pl.Series("simulated_deaths", [0, 1, 0])

    assert _records(af)[-1].node == _injection_of([0, 1, 0])


def test_series_injected_through_with_columns_records_the_same_node() -> None:
    """The batch door treats an injected series exactly as the setter does."""
    af = _policy_frame()

    af = af.with_columns(pl.Series("simulated_deaths", [0, 1, 0]))

    assert _records(af)[-1].node == _injection_of([0, 1, 0])


def test_non_finite_literal_assignment_is_refused_at_its_own_line() -> None:
    """Assigning NaN refuses, exactly as a NaN operand already does.

    NaN is a bug, not a value: seeding it into a projection produces
    reserves that are silently null rather than wrong-and-visible.
    """
    af = _policy_frame()

    with pytest.raises(ValueError, match="not finite"):
        af.reserve = float("nan")


def test_a_non_finite_infinity_is_refused_like_a_nan() -> None:
    """Both halves of "not a number" are refused, not just NaN.

    An infinite literal is the same bug wearing different clothes: it
    propagates through a projection producing infinities and nulls rather
    than an error anyone can trace back to a line.
    """
    af = _policy_frame()

    with pytest.raises(ValueError, match="not finite"):
        af.benefit_cap = float("inf")


def test_a_refused_assignment_leaves_no_phantom_column() -> None:
    """A column the frame never computed must not survive in ``columns``.

    The name is registered before the value is examined, so a refusal has
    to roll it back -- otherwise ``af.columns`` lists a column that
    resolves to a proxy and then disagrees with the collected frame.
    """
    af = _policy_frame()
    columns_before = list(af.columns)

    with pytest.raises(ValueError, match="not finite"):
        af.reserve = float("nan")

    assert af.columns == columns_before
    assert "reserve" not in af.collect().columns


# --- dtype ------------------------------------------------------------------


def test_dtype_is_recorded_when_the_incremental_resolve_runs() -> None:
    """On a plan deep enough to earn the cheap probe, the record carries a dtype."""
    af = _wide_policy_frame()

    af.expenses = af.annual_premium * 0.05

    assert _records(af)[-1].dtype == pl.Float64


def test_dtype_is_left_unresolved_on_a_shallow_plan() -> None:
    """Below the incremental-schema gate nothing is resolved, so nothing is claimed.

    The record's ``dtype`` is mutable precisely so a later reader can fill
    it in; recording ``None`` says "not resolved yet", which is true, rather
    than paying for a deep schema resolve on the model-build hot path.
    """
    af = _policy_frame()

    af.expenses = af.annual_premium * 0.05

    assert _records(af)[-1].dtype is None


def test_batch_records_carry_the_dtype_the_batch_resolved() -> None:
    """``with_columns`` already resolves the schema, so the dtype is free."""
    af = _policy_frame()

    af = af.with_columns((pl.col("annual_premium") * 0.05).alias("expenses"))

    assert _records(af)[-1].dtype == pl.Float64


# --- source attribution -----------------------------------------------------


def test_assignment_attributes_to_the_model_authors_own_statement() -> None:
    """A real frame assignment reports THIS file's line, not the framework's.

    Everything between the author's statement and the capture -- the
    ``__setattr__`` that routes it, the ``__setitem__`` that applies it --
    lives under ``gaspatchio/frame/``, which the capture walks past. If a
    future assignment route detoured through framework code outside that
    covered set, this test is what would catch it.
    """
    af = _policy_frame()

    af.death_claims = af.sum_assured * af.mortality_rate

    source = _records(af)[-1].source
    assert source is not None
    assert source.file == __file__
    assert source.statement == "af.death_claims = af.sum_assured * af.mortality_rate"
    assert source.rhs == "af.sum_assured * af.mortality_rate"
    assert source.target_literal is True


def test_bracket_assignment_attributes_to_the_model_authors_own_statement() -> None:
    """The bracket door reports the author's line just as the attribute door does."""
    af = _policy_frame()

    af["death_claims"] = af.sum_assured * af.mortality_rate

    source = _records(af)[-1].source
    assert source is not None
    assert source.file == __file__
    assert source.statement == 'af["death_claims"] = af.sum_assured * af.mortality_rate'


def test_a_model_run_through_the_scenario_loop_attributes_to_the_model_code() -> None:
    """Framework code between the author and the assignment does not absorb the blame.

    ``for_each_scenario`` calls the model function from inside
    ``gaspatchio/scenarios/`` -- a directory the capture's internal-frame
    patterns deliberately do NOT cover, because it is not part of the
    assignment machinery. The model function's own frame sits between, so
    the span still resolves to the line its author wrote. This is the pin
    for the whole property: a future assignment route that reached the
    frame through framework code with no user frame in between would
    attribute a model author's column to the framework, and this test is
    what would say so.
    """
    captured: list[SourceSpan | None] = []

    def model_fn(af: ActuarialFrame, *, tables: object, drivers: object) -> Any:  # noqa: ANN401, ARG001
        af.expenses = af.annual_premium * 0.05
        captured.append(af._calculations[-1].source)  # noqa: SLF001
        return af

    for_each_scenario(
        _policy_frame(),
        ["BASE", "MORTALITY_UP"],
        model_fn,
        aggregations=[Sum("expenses").alias("total_expenses")],
    )

    assert captured
    for span in captured:
        assert span is not None
        assert span.file == __file__
        assert span.statement == "af.expenses = af.annual_premium * 0.05"


def test_batch_records_share_the_statement_that_defined_them() -> None:
    """One ``with_columns`` statement, one source span across every record."""
    af = _policy_frame()

    af = af.with_columns(
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("death_claims"),
        (pl.col("annual_premium") * 0.05).alias("expenses"),
    )

    first, second = _records(af)
    assert first.source is not None
    assert first.source.file == __file__
    assert "with_columns" in first.source.statement
    assert second.source == first.source


# --- the log is append-only -------------------------------------------------


def test_a_successful_collect_leaves_every_record_in_place() -> None:
    """Materialisation moves the cursor; it never shortens the log."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate
    af.expenses = af.annual_premium * 0.05

    af.collect()

    assert len(_records(af)) == 2


def test_structural_operations_leave_every_record_in_place() -> None:
    """A filter resets attribution; it does not erase what was calculated."""
    af = _policy_frame()
    af.death_claims = af.sum_assured * af.mortality_rate

    af = af.filter(pl.col("policy_id") == 1)
    af.expenses = af.annual_premium * 0.05

    assert [record.column for record in _records(af)] == ["death_claims", "expenses"]
