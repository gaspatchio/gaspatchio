# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Plan-lowering panics attribute like any other collect failure (#54).

A schema-mismatch inside a ``when().then()`` branch fails during IR plan
lowering, where polars panics (``builder_ir.rs``: "no valid schema can be
derived") instead of raising a typed error. pyo3 surfaces that panic as
``PanicException`` — a ``BaseException`` subclass — which used to sail past
both the ``except Exception`` at the ``collect()``/``profile()`` boundary
and the #39 attribution gate, reaching the user with no failing column, no
defining expression, and no way to catch it with ``except Exception``.

These tests pin the fixed contract: such a panic is converted at the
boundary into a catchable ``SchemaError`` carrying the #39 attribution
block, while panics that are NOT schema-derivation failures (and real
interrupts) pass through untouched.

The failing branch is built from RAW ``pl.Expr`` operands deliberately:
raw expressions bypass the ExpressionProxy broadcast shim, so the
supertype failure here stays failing even after #53 (order-dependent
broadcast) is fixed for proxy-built expressions.
"""

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.errors.boundary import is_plan_lowering_panic

VALUATION = datetime.date(2025, 1, 1)


def _frame() -> ActuarialFrame:
    """One policy on an annual axis with a scalar/list pair of columns."""
    af = ActuarialFrame(
        {
            "policy_id": [1],
            "issue_age": [40],
            "dur": [0],
            "a": [100.0],
            "b": [0.05],
        }
    )
    af = af.projection.set(
        valuation_date=VALUATION,
        until="maximum_age",
        until_value=60,
        issue_age_column="issue_age",
        frequency="annual",
    )
    af.t = af.month // 12
    af.infl = (af.t * 0.0) + 1.01
    return af


def _unbroadcastable() -> pl.Expr:
    """Build a raw expression whose supertype (f64 vs list[f64]) cannot derive."""
    return pl.col("a") * pl.col("b") + pl.col("a") * pl.col("infl")


class TestWhenBranchPanicAttribution:
    """The #54 contract: panics at plan lowering become attributed errors."""

    def test_panic_becomes_catchable_schema_error(self) -> None:
        """The panic converts to SchemaError, catchable via except Exception."""
        af = _frame()
        af.x = when(af.dur == 0).then(_unbroadcastable()).otherwise(0.0)
        with pytest.raises(pl.exceptions.SchemaError):
            af.collect()

    def test_attribution_names_column_and_expression(self) -> None:
        """The converted error carries the #39 attribution block."""
        af = _frame()
        af.x = when(af.dur == 0).then(_unbroadcastable()).otherwise(0.0)
        with pytest.raises(pl.exceptions.SchemaError) as excinfo:
            af.collect()
        msg = str(excinfo.value)
        assert "no valid schema can be derived" in msg
        assert "Failing column: 'x'" in msg
        assert "Defined as:" in msg

    def test_profile_boundary_converts_too(self) -> None:
        """profile() shares the collect() panic boundary."""
        af = _frame()
        af.x = when(af.dur == 0).then(_unbroadcastable()).otherwise(0.0)
        with pytest.raises(pl.exceptions.SchemaError) as excinfo:
            af.profile()
        assert "Failing column: 'x'" in str(excinfo.value)

    def test_original_panic_is_chained(self) -> None:
        """The converted error keeps the panic as its cause for debugging."""
        af = _frame()
        af.x = when(af.dur == 0).then(_unbroadcastable()).otherwise(0.0)
        with pytest.raises(pl.exceptions.SchemaError) as excinfo:
            af.collect()
        cause = excinfo.value.__cause__
        assert cause is not None
        assert type(cause).__name__ == "PanicException"

    def test_panic_after_healthy_columns_names_the_right_one(self) -> None:
        """Attribution picks the panicking assignment, not a neighbour."""
        af = _frame()
        af.healthy = af.a * af.b
        af.x = when(af.dur == 0).then(_unbroadcastable()).otherwise(0.0)
        with pytest.raises(pl.exceptions.SchemaError) as excinfo:
            af.collect()
        assert "Failing column: 'x'" in str(excinfo.value)


class TestPlainColumnRegression:
    """The Exception path is untouched: plain schema errors still attribute."""

    def test_plain_raw_expr_schema_error_still_attributed(self) -> None:
        """A clean SchemaError (no panic) still attributes as before."""
        af = _frame()
        af.x = _unbroadcastable()
        with pytest.raises(pl.exceptions.SchemaError) as excinfo:
            af.collect()
        assert "Failing column: 'x'" in str(excinfo.value)


class TestPanicPredicateNarrowness:
    """Only schema-derivation panics qualify; everything else passes through."""

    def test_predicate_matches_schema_panic(self) -> None:
        """A PanicException with the schema-derivation message qualifies."""
        fake_panic_cls = type("PanicException", (BaseException,), {})
        exc = fake_panic_cls(
            "no valid schema can be derived for the query: SchemaMismatch(...)"
        )
        assert is_plan_lowering_panic(exc) is True

    def test_predicate_rejects_other_panics(self) -> None:
        """A panic with any other message does not qualify."""
        fake_panic_cls = type("PanicException", (BaseException,), {})
        assert is_plan_lowering_panic(fake_panic_cls("index out of bounds")) is False

    def test_predicate_rejects_ordinary_exceptions(self) -> None:
        """The message alone is not enough — the type must be a panic."""
        exc = ValueError("no valid schema can be derived for the query")
        assert is_plan_lowering_panic(exc) is False

    def test_predicate_rejects_interrupts(self) -> None:
        """Real interrupts never qualify."""
        assert is_plan_lowering_panic(KeyboardInterrupt()) is False
