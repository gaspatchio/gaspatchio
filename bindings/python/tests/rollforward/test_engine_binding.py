# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""engine_binding static walk — closed-subset whitelist."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio.assumptions import Table
from gaspatchio.curves import Curve
from gaspatchio.mortality import MortalityTable
from gaspatchio.rollforward._engine_binding import (
    MEASURED_POLARS_VERSION,
    derive_engine_binding,
    node_identities,
)
from gaspatchio.rollforward._ir import IR, State
from gaspatchio.rollforward._ops import Add, Apply, Floor, Grow
from gaspatchio.rollforward._refs import StateRef
from gaspatchio.schedule import Actual365Fixed, OneTwelfth, Schedule


@pytest.fixture
def base_schedule() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


def _ir_with_transitions(
    transitions: tuple,
    schedule: Schedule,
    contract_boundary: pl.Expr | None = None,
) -> IR:
    return IR(
        states=(State(name="av", init=pl.col("init")),),
        points=("bop", "eop"),
        transitions=transitions,
        schedule=schedule,
        batch_axes=("policy",),
        track_increments=False,
        lapse_when_all_non_positive=(),
        contract_boundary=contract_boundary,
    )


def _binding_of_body(body: pl.Expr, schedule: Schedule) -> str:
    """Stamp an IR whose only transition applies ``body`` to the state."""
    ir = _ir_with_transitions(
        (
            Apply(
                target=StateRef(state="av", point="eop"),
                body=body,
                label="Custom",
            ),
        ),
        schedule,
    )
    return derive_engine_binding(ir)


class TestEngineBinding:
    def test_closed_subset_only_is_portable(self, base_schedule: Schedule) -> None:
        ir = _ir_with_transitions(
            (
                Add(
                    target=StateRef(state="av", point="eop"),
                    expr=pl.col("premium"),
                    label="P",
                ),
                Floor(target=StateRef(state="av", point="eop"), value=0.0),
            ),
            base_schedule,
        )
        assert derive_engine_binding(ir) == "portable"

    def test_pl_max_horizontal_in_apply_body_flips_to_polars(
        self,
        base_schedule: Schedule,
    ) -> None:
        ir = _ir_with_transitions(
            (
                Apply(
                    target=StateRef(state="av", point="eop"),
                    body=pl.max_horizontal(pl.col("a"), pl.col("b")),
                    label="Custom",
                ),
            ),
            base_schedule,
        )
        assert derive_engine_binding(ir) == "polars"

    def test_pl_max_horizontal_in_contract_boundary_flips_to_polars(
        self,
        base_schedule: Schedule,
    ) -> None:
        ir = _ir_with_transitions(
            (Floor(target=StateRef(state="av", point="eop"), value=0.0),),
            base_schedule,
            contract_boundary=pl.max_horizontal(pl.col("a"), pl.col("b")) > 0,
        )
        assert derive_engine_binding(ir) == "polars"

    def test_simple_arithmetic_in_transition_body_is_portable(
        self,
        base_schedule: Schedule,
    ) -> None:
        ir = _ir_with_transitions(
            (
                Grow(
                    target=StateRef(state="av", point="eop"),
                    rate=pl.col("base") - pl.col("fee"),
                    label="Net growth",
                ),
            ),
            base_schedule,
        )
        assert derive_engine_binding(ir) == "portable"


class TestOutsideTheClosedSubsetRefuses:
    """A body reaching outside the subset stamps 'polars', whatever it reaches for.

    The walk has no list of unsafe operations to miss: it recognises the
    subset and refuses the rest, so an operation nobody anticipated refuses
    for the same reason a horizontal aggregate does.
    """

    @pytest.mark.parametrize(
        ("label", "body"),
        [
            ("list namespace", pl.col("x").list.sum()),
            ("arr namespace", pl.col("x").arr.sum()),
            ("str namespace", pl.col("x").str.len_chars()),
            ("sum_horizontal", pl.sum_horizontal(pl.col("x"), pl.col("y"))),
            ("min_horizontal", pl.min_horizontal(pl.col("x"), pl.col("y"))),
            ("any_horizontal", pl.any_horizontal(pl.col("x"), pl.col("y"))),
            ("all_horizontal", pl.all_horizontal(pl.col("x"), pl.col("y"))),
            ("cast", pl.col("x").cast(pl.Float64)),
            ("alias", pl.col("x").alias("y")),
            ("aggregate min", pl.col("x").min()),
            ("shift", pl.col("x").shift(1)),
            ("fill_null", pl.col("x").fill_null(0.0)),
            ("is_null", pl.col("x").is_null()),
            ("abs", pl.col("x").abs()),
            ("exp", pl.col("x").exp()),
            ("sqrt", pl.col("x").sqrt()),
            ("round", pl.col("x").round(2)),
            ("negate", -pl.col("x")),
            ("floor divide", pl.col("x") // pl.col("y")),
            ("modulus", pl.col("x") % pl.col("y")),
        ],
    )
    def test_body_outside_the_subset_is_polars(
        self,
        label: str,
        body: pl.Expr,
        base_schedule: Schedule,
    ) -> None:
        assert _binding_of_body(body, base_schedule) == "polars", label

    def test_an_unserialisable_body_is_polars(
        self,
        base_schedule: Schedule,
    ) -> None:
        """A Python callable inside the Expr refuses rather than passing.

        ``Schedule.year_fractions_expr`` on any day-count but ``OneTwelfth``
        computes the fractions through a Python function, which the engine
        cannot write into its own tree without a pickler this package does
        not depend on. The walk cannot read it, so it does not pass it.
        """
        dated = Schedule.from_inception(
            inception_column="incep",
            n_periods=3,
            frequency="1M",
            day_count=Actual365Fixed(),
        )
        assert _binding_of_body(dated.year_fractions_expr(), base_schedule) == "polars"


class TestClosedSubsetIsPortable:
    @pytest.mark.parametrize(
        ("label", "body"),
        [
            ("column", pl.col("x")),
            ("literal", pl.lit(1.5)),
            ("add", pl.col("x") + pl.col("y")),
            ("subtract", pl.col("x") - pl.col("y")),
            ("scaled sum", pl.col("x") * 1.05 + pl.col("y")),
            ("divide", pl.col("x") / pl.col("y")),
            ("power", pl.col("x") ** 2),
            ("equality", pl.col("x") == pl.col("y")),
            ("inequality", pl.col("x") != pl.col("y")),
            ("less than", pl.col("x") < pl.col("y")),
            ("less or equal", pl.col("x") <= pl.col("y")),
            ("greater than", pl.col("x") > pl.col("y")),
            ("greater or equal", pl.col("x") >= pl.col("y")),
            ("conjunction", pl.col("x") & pl.col("y")),
            ("disjunction", pl.col("x") | pl.col("y")),
            ("negation", ~pl.col("x")),
            (
                "when over a comparison",
                pl.when(pl.col("x") > pl.col("y"))
                .then(pl.col("x") * 1.05)
                .otherwise(0.0),
            ),
        ],
    )
    def test_closed_subset_body_is_portable(
        self,
        label: str,
        body: pl.Expr,
        base_schedule: Schedule,
    ) -> None:
        assert _binding_of_body(body, base_schedule) == "portable", label


@pytest.fixture(scope="module")
def typed_inputs() -> dict[str, pl.Expr]:
    """One expression per typed input the module docstring admits."""
    curve = Curve.from_zero_rates(
        tenors=[1.0, 5.0, 10.0],
        rates=[0.03, 0.032, 0.035],
    )
    aggregate = Table(
        name="engine_binding_aggregate_mortality",
        source=pl.DataFrame({"age": [30, 31, 32], "rate": [0.001, 0.002, 0.003]}),
        dimensions={"age": "age"},
        value="rate",
    )
    select = Table(
        name="engine_binding_select_mortality",
        source=pl.DataFrame(
            {
                "age": [30, 30, 31, 31],
                "duration": [0, 1, 0, 1],
                "rate": [0.001, 0.002, 0.003, 0.004],
            }
        ),
        dimensions={"age": "age", "duration": "duration"},
        value="rate",
    )
    lapse = Table(
        name="engine_binding_lapse",
        source=pl.DataFrame({"age": [30, 31, 32], "rate": [0.1, 0.2, 0.3]}),
        dimensions={"age": "age"},
        value="rate",
    )
    monthly = Schedule.from_inception(
        inception_column="incep",
        n_periods=3,
        frequency="1M",
        day_count=OneTwelfth(),
    )
    return {
        "Schedule.year_fractions_expr": monthly.year_fractions_expr(),
        "Curve.spot_rate": curve.spot_rate(pl.col("t")),
        "Curve.discount_factor": curve.discount_factor(pl.col("t")),
        "MortalityTable.at": MortalityTable(
            table=aggregate,
            age_basis="age_last_birthday",
            structure="aggregate",
        ).at(age=pl.col("age")),
        "MortalityTable.at (select/ultimate)": MortalityTable(
            table=select,
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=1,
        ).at(age=pl.col("age"), duration=pl.col("duration")),
        "Table.lookup": lapse.lookup(age=pl.col("age")),
    }


class TestTypedInputsArePortable:
    @pytest.mark.parametrize(
        "name",
        [
            "Schedule.year_fractions_expr",
            "Curve.spot_rate",
            "Curve.discount_factor",
            "MortalityTable.at",
            "MortalityTable.at (select/ultimate)",
            "Table.lookup",
        ],
    )
    def test_typed_input_is_portable(
        self,
        name: str,
        typed_inputs: dict[str, pl.Expr],
        base_schedule: Schedule,
    ) -> None:
        assert _binding_of_body(typed_inputs[name], base_schedule) == "portable", name

    def test_a_foreign_plugin_symbol_is_polars(self, base_schedule: Schedule) -> None:
        """A plugin call this package does not make refuses by symbol."""
        from polars.plugins import register_plugin_function

        from gaspatchio import _internal

        foreign = register_plugin_function(
            plugin_path=_internal.__file__,
            function_name="fill_series",
            args=[pl.col("x")],
            kwargs={"start": 0, "increment": 1},
            is_elementwise=True,
        )
        assert _binding_of_body(foreign, base_schedule) == "polars"


#: What each closed-subset construct serialises to, measured on
#: ``MEASURED_POLARS_VERSION``. A Polars release that renames a node kind
#: changes these sets, refuses every rollforward that used to pass, and moves
#: every compiled fingerprint with it — so this census fails first and loudly.
_CENSUS: dict[str, set[tuple[str, ...]]] = {
    "pl.col": {("Column",)},
    "pl.lit(int)": {("Literal",)},
    "pl.lit(float)": {("Literal",)},
    "pl.lit(str)": {("Literal",)},
    "pl.lit(bool)": {("Literal",)},
    "add": {("Column",), ("BinaryExpr", "Plus")},
    "subtract": {("Column",), ("BinaryExpr", "Minus")},
    "multiply": {("Column",), ("BinaryExpr", "Multiply")},
    "divide": {("Column",), ("BinaryExpr", "TrueDivide")},
    "power": {("Column",), ("Literal",), ("Function", "Pow", "Generic")},
    "equal": {("Column",), ("BinaryExpr", "Eq")},
    "not equal": {("Column",), ("BinaryExpr", "NotEq")},
    "less than": {("Column",), ("BinaryExpr", "Lt")},
    "less or equal": {("Column",), ("BinaryExpr", "LtEq")},
    "greater than": {("Column",), ("BinaryExpr", "Gt")},
    "greater or equal": {("Column",), ("BinaryExpr", "GtEq")},
    "conjunction": {("Column",), ("BinaryExpr", "And")},
    "disjunction": {("Column",), ("BinaryExpr", "Or")},
    "negation": {("Column",), ("Function", "Boolean", "Not")},
    "when/then/otherwise": {
        ("Column",),
        ("Literal",),
        ("Ternary",),
        ("BinaryExpr", "Gt"),
    },
}

_CENSUS_EXPRESSIONS: dict[str, pl.Expr] = {
    "pl.col": pl.col("x"),
    "pl.lit(int)": pl.lit(1),
    "pl.lit(float)": pl.lit(1.5),
    "pl.lit(str)": pl.lit("a"),
    "pl.lit(bool)": pl.lit(value=True),
    "add": pl.col("x") + pl.col("y"),
    "subtract": pl.col("x") - pl.col("y"),
    "multiply": pl.col("x") * pl.col("y"),
    "divide": pl.col("x") / pl.col("y"),
    "power": pl.col("x") ** 2,
    "equal": pl.col("x") == pl.col("y"),
    "not equal": pl.col("x") != pl.col("y"),
    "less than": pl.col("x") < pl.col("y"),
    "less or equal": pl.col("x") <= pl.col("y"),
    "greater than": pl.col("x") > pl.col("y"),
    "greater or equal": pl.col("x") >= pl.col("y"),
    "conjunction": pl.col("x") & pl.col("y"),
    "disjunction": pl.col("x") | pl.col("y"),
    "negation": ~pl.col("x"),
    "when/then/otherwise": pl.when(pl.col("x") > pl.col("y"))
    .then(pl.col("y"))
    .otherwise(0.0),
}

_TYPED_INPUT_CENSUS: dict[str, set[tuple[str, ...]]] = {
    "Schedule.year_fractions_expr": {("Literal",)},
    "Curve.spot_rate": {("Column",), ("Function", "FfiPlugin", "curve_eval")},
    "Curve.discount_factor": {
        ("Column",),
        ("Literal",),
        ("BinaryExpr", "Plus"),
        ("BinaryExpr", "Multiply"),
        ("Function", "FfiPlugin", "curve_eval"),
        ("Function", "FfiPlugin", "list_pow"),
    },
    "MortalityTable.at": {
        ("Column",),
        ("Function", "FfiPlugin", "lookup_by_table_and_hash"),
    },
    "MortalityTable.at (select/ultimate)": {
        ("Column",),
        ("Literal",),
        ("Function", "Clip"),
        ("Function", "FfiPlugin", "lookup_by_table_and_hash"),
    },
    "Table.lookup": {
        ("Column",),
        ("Function", "FfiPlugin", "lookup_by_table_and_hash"),
    },
}


class TestClosedSubsetCensus:
    """The identities the closed subset serialises to, pinned to one Polars."""

    def test_the_measured_polars_version_is_the_installed_one(self) -> None:
        assert pl.__version__ == MEASURED_POLARS_VERSION, (
            f"engine_binding's closed-subset census was measured on Polars "
            f"{MEASURED_POLARS_VERSION} and this environment has "
            f"{pl.__version__}. Re-measure every construct below before "
            f"moving MEASURED_POLARS_VERSION: a renamed node kind refuses "
            f"every rollforward that used to pass and moves every compiled "
            f"fingerprint with it."
        )

    @pytest.mark.parametrize("name", sorted(_CENSUS))
    def test_construct_serialises_to_the_pinned_identities(self, name: str) -> None:
        assert set(node_identities(_CENSUS_EXPRESSIONS[name])) == _CENSUS[name]

    @pytest.mark.parametrize("name", sorted(_TYPED_INPUT_CENSUS))
    def test_typed_input_serialises_to_the_pinned_identities(
        self,
        name: str,
        typed_inputs: dict[str, pl.Expr],
    ) -> None:
        assert set(node_identities(typed_inputs[name])) == _TYPED_INPUT_CENSUS[name]
