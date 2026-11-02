# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What a write past the recording doors defined, and which columns another frame calculated.

Two readings the frame cannot take off its own calculation log. The first
reads Polars' plan before and after a write to ``af._df`` and says which
columns the write defined; the frame compares that with what it accounted
for. The second finds, in a DataFrame a new frame is being built over, the
columns whose memory is a calculated column of values another frame still
holds from its last collect.

Both have to be exactly right where they speak and silent where they
cannot tell. A column the frame is told was overwritten is a column it stops
vouching for, so a false report costs a model its account of a column it
computed honestly; and the template's own setup step -- collect, rename in
Polars, build the frame again -- must say nothing at all.
"""

from __future__ import annotations

import gc
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from polars.exceptions import PanicException

from gaspatchio import ActuarialFrame
from gaspatchio.frame import plan_writes
from gaspatchio.frame.plan_writes import (
    PLAN_VERSION,
    ComputedValues,
    Origin,
    PlanWrite,
    ValuesAccount,
    plan_version,
    read_plan_write,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "premium": [100.0, 200.0, 300.0],
        "tags": [[1, 2], [3], []],
        "detail": [{"band": 1}, {"band": 2}, {"band": 3}],
    }
)

# A rules table a model joins in by product, as the extending skill's
# example does, with one column whose name the book also carries.
_RULES = pl.DataFrame({"policy_id": [1, 2], "rate": [0.1, 0.2], "premium": [5.0, 6.0]})

# The columns the frame accounts for once the commission is assigned: the
# four the book arrived with and the one calculation.
_ACCOUNTED = frozenset({"policy_id", "premium", "tags", "detail", "commission"})


def _the_frame_s_plan() -> pl.LazyFrame:
    """Return the plan the doors built: the book, then a recorded commission."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    plan = af._df  # noqa: SLF001 -- the plan a raw write starts from
    assert plan is not None
    return plan


# --- the shapes a raw write takes ---------------------------------------------

UNREADABLE = "unreadable"
UNRESOLVED = "unresolved"

_WRITES: list[tuple[str, Callable[[pl.LazyFrame], pl.LazyFrame], Any]] = [
    # Steps that define columns.
    (
        "an_expression_the_traverser_has_no_view_of",
        lambda p: p.with_columns(pl.col("tags").list.eval(pl.element() * 2)),
        {"tags"},
    ),
    (
        "a_literal_over_a_calculation",
        lambda p: p.with_columns(pl.lit(0.0).alias("commission")),
        {"commission"},
    ),
    (
        "the_column_read_and_written_again",
        lambda p: p.with_columns((pl.col("commission") * 0.9).alias("commission")),
        {"commission"},
    ),
    (
        "an_expression_named_by_its_input",
        lambda p: p.with_columns(pl.col("commission") * 0.9),
        {"commission"},
    ),
    (
        "an_arriving_column_written_over",
        lambda p: p.with_columns(pl.lit(5.0).alias("premium")),
        {"premium"},
    ),
    (
        "a_new_column",
        lambda p: p.with_columns(pl.lit(1.0).alias("sneaky")),
        {"sneaky"},
    ),
    (
        "two_steps_in_one_write",
        lambda p: p.with_columns(pl.lit(1.0).alias("a")).with_columns(
            pl.lit(2.0).alias("premium")
        ),
        {"a", "premium"},
    ),
    (
        "a_sequential_with_columns",
        lambda p: p.with_columns_seq(pl.lit(0.0).alias("commission")),
        {"commission"},
    ),
    (
        "a_series_handed_over",
        lambda p: p.with_columns(pl.Series("commission", [9.0, 9.0, 9.0])),
        {"commission"},
    ),
    (
        "a_cast",
        lambda p: p.with_columns(pl.col("policy_id").cast(pl.Int32)),
        {"policy_id"},
    ),
    (
        "every_float_column_through_a_selector",
        lambda p: p.with_columns(pl.col(pl.Float64).fill_null(0.0)),
        {"premium", "commission"},
    ),
    (
        "a_select_that_rewrites",
        lambda p: p.select(
            "policy_id", "premium", (pl.col("commission") * 2).alias("commission")
        ),
        {"commission"},
    ),
    ("a_rename", lambda p: p.rename({"commission": "fee"}), {"fee"}),
    (
        "one_column_reversed",
        lambda p: p.with_columns(pl.col("commission").reverse()),
        {"commission"},
    ),
    (
        "every_column_sorted_apart",
        lambda p: p.select(pl.all().sort()),
        set(_ACCOUNTED),
    ),
    (
        "every_column_shifted_but_not_alike",
        lambda p: p.select(
            pl.col("policy_id").shift(2),
            pl.exclude("policy_id").shift(1),
        ),
        set(_ACCOUNTED),
    ),
    (
        "some_columns_reversed",
        lambda p: p.select(pl.col("premium", "commission").reverse()),
        {"premium", "commission"},
    ),
    (
        "a_rename_that_swaps",
        lambda p: p.rename({"commission": "premium", "premium": "commission"}),
        {"commission", "premium"},
    ),
    # Steps that define no column the frame held.
    ("a_select_that_projects", lambda p: p.select("premium", "commission"), set()),
    ("a_drop", lambda p: p.drop("commission"), set()),
    (
        "the_column_handed_back_unchanged",
        lambda p: p.with_columns(pl.col("commission")),
        set(),
    ),
    ("a_filter", lambda p: p.filter(pl.col("premium") > 150), set()),
    ("a_sort", lambda p: p.sort("premium", descending=True), set()),
    ("a_head", lambda p: p.head(2), set()),
    ("a_unique", lambda p: p.unique(subset=["policy_id"]), set()),
    ("a_cache", lambda p: p.cache(), set()),
    ("a_semi_join", lambda p: p.join(_RULES.lazy(), on="policy_id", how="semi"), set()),
    ("a_sortedness_hint", lambda p: p.set_sorted("policy_id"), set()),
    (
        "a_column_marked_sorted",
        lambda p: p.with_columns(pl.col("premium").set_sorted()),
        set(),
    ),
    (
        "every_row_of_a_column_kept",
        lambda p: p.with_columns(pl.col("commission").gather_every(1)),
        set(),
    ),
    ("every_row_reversed", lambda p: p.reverse(), set()),
    ("every_row_moved_down_one", lambda p: p.shift(1), set()),
    ("every_second_row", lambda p: p.gather_every(2), set()),
    (
        "every_column_reversed_in_place",
        lambda p: p.with_columns(pl.all().reverse()),
        set(),
    ),
    ("the_plan_itself", lambda p: p, set()),
    # Steps that bring columns in beside the frame's own: under new names,
    # which no column the frame accounted for answers to.
    (
        "a_left_join",
        lambda p: p.join(_RULES.lazy(), on="policy_id", how="left"),
        {"rate", "premium_right"},
    ),
    (
        "a_full_join",
        lambda p: p.join(_RULES.lazy(), on="policy_id", how="full", coalesce=True),
        {"rate", "premium_right"},
    ),
    (
        "a_cross_join",
        lambda p: p.join(_RULES.lazy().select("rate"), how="cross"),
        {"rate"},
    ),
    ("a_row_index", lambda p: p.with_row_index("row"), {"row"}),
    ("an_unnested_struct", lambda p: p.unnest("detail"), {"band"}),
    # The same steps after the write dropped the name: the column they bring
    # in stands under a name the frame accounted for.
    (
        "a_name_dropped_and_joined_back",
        lambda p: p.drop("premium").join(_RULES.lazy(), on="policy_id", how="left"),
        {"rate", "premium"},
    ),
    (
        "a_name_dropped_and_concatenated_back",
        lambda p: pl.concat(
            [p.drop("premium"), _BOOK.lazy().select(pl.col("premium") * 2)],
            how="horizontal",
        ),
        {"premium"},
    ),
    (
        "a_name_dropped_and_indexed_back",
        lambda p: p.drop("policy_id").with_row_index("policy_id"),
        {"policy_id"},
    ),
    (
        "a_name_dropped_and_unnested_back",
        lambda p: (
            p.drop("premium")
            .with_columns(pl.struct(pl.lit(1.0).alias("premium")).alias("wrapped"))
            .unnest("wrapped")
        ),
        {"wrapped", "premium"},
    ),
    # Writes the reader cannot read: it says so rather than guessing.
    ("an_explode", lambda p: p.explode("tags", empty_as_null=True), UNREADABLE),
    ("an_unpivot", lambda p: p.unpivot(index="policy_id", on="premium"), UNREADABLE),
    (
        "a_group_by",
        lambda p: p.group_by("policy_id").agg(pl.col("premium").sum()),
        UNREADABLE,
    ),
    ("a_vertical_concat", lambda p: pl.concat([p, p]), UNREADABLE),
    ("a_python_function", lambda p: p.map_batches(lambda frame: frame), UNREADABLE),
    ("a_plan_from_nowhere", lambda _: _BOOK.lazy(), UNREADABLE),
    ("the_values_scanned_again", lambda p: p.collect().lazy(), UNREADABLE),
    (
        "the_plan_rebuilt_in_the_same_shape",
        lambda _: _BOOK.lazy().with_columns(
            (pl.col("premium") * 0.5).alias("commission")
        ),
        UNREADABLE,
    ),
    (
        "the_plan_rebuilt_over_other_values",
        lambda _: (
            _BOOK.with_columns(pl.col("premium") * 2)
            .lazy()
            .with_columns((pl.col("premium") * 0.1).alias("commission"))
        ),
        UNREADABLE,
    ),
    # A plan that does not resolve: collect() refuses it, so nothing to say.
    ("a_column_that_does_not_exist", lambda p: p.select(pl.col("absent")), UNRESOLVED),
]


@pytest.mark.parametrize(
    ("write", "expected"),
    [pytest.param(write, expected, id=name) for name, write, expected in _WRITES],
)
def test_each_shape_of_write_is_read_for_what_it_defined(
    write: Callable[[pl.LazyFrame], pl.LazyFrame], expected: Any
) -> None:
    """The columns a write defined, or an honest statement that it cannot say."""
    before = _the_frame_s_plan()

    read = read_plan_write(before, write(before))

    if expected == UNRESOLVED:
        assert (read.resolves, read.readable) == (False, False)
    elif expected == UNREADABLE:
        assert (read.resolves, read.readable, read.wrote) == (True, False, frozenset())
    else:
        assert (read.resolves, read.readable) == (True, True)
        assert read.wrote == frozenset(expected)


def test_the_same_shape_of_plan_over_other_values_is_not_the_frame_s_plan() -> None:
    """Matching steps are not enough: the data under them has to be the same memory."""
    calculation = (pl.col("premium") * 0.1).alias("commission")
    before = _BOOK.lazy().with_columns(calculation)
    lookalike = pl.DataFrame(_BOOK.to_dict(as_series=False)).lazy()

    read = read_plan_write(before, lookalike.with_columns(calculation))

    assert (read.resolves, read.readable) == (True, False)


# --- what the frame is told it can no longer vouch for -------------------------


def test_a_readable_write_leaves_unvouched_only_what_it_defined_over_an_account() -> (
    None
):
    """A new name is not an overwrite; a defined name the frame accounted for is."""
    before = _the_frame_s_plan()
    after = before.with_columns(
        pl.lit(0.0).alias("commission"), pl.lit(1.0).alias("sneaky")
    )

    assert read_plan_write(before, after).overwritten(_ACCOUNTED) == {"commission"}


def test_a_column_written_and_then_dropped_in_one_write_is_not_overwritten() -> None:
    """The frame no longer holds it, so there is no account left to be untrue."""
    before = _the_frame_s_plan()
    after = before.with_columns(pl.lit(0.0).alias("commission")).drop("commission")

    assert read_plan_write(before, after).overwritten(_ACCOUNTED) == frozenset()


def test_a_raw_join_that_adds_columns_overwrites_nothing() -> None:
    """The extending skill's shape: new names, which the frame reports as unrecorded.

    ``af._df = af._df.join(rules_df.lazy(), on=..., how="left")`` brings the
    rules table's columns in under names the frame did not hold -- the book's
    own ``premium`` comes back from the right side as ``premium_right`` -- so
    no column the frame accounted for is written over, and the frame's
    existing reading reports the new names as columns nothing recorded.
    """
    before = _the_frame_s_plan()
    after = before.join(_RULES.lazy(), on="policy_id", how="left")

    read = read_plan_write(before, after)

    assert read.overwritten(_ACCOUNTED) == frozenset()
    assert read.holds is not None
    assert {"rate", "premium_right"} <= read.holds

    af = ActuarialFrame(_BOOK.select("policy_id", "premium"))
    af.commission = af.premium * 0.1
    af._df = af._df.join(_RULES.lazy(), on="policy_id", how="left")  # noqa: SLF001
    assert [(hole.column, hole.reason) for hole in af.graph.holes()] == [
        ("rate", "unrecorded"),
        ("premium_right", "unrecorded"),
    ]


def test_an_unreadable_write_leaves_every_held_column_unvouched() -> None:
    """The frame cannot say which column moved, so it vouches for none it still holds."""
    before = _the_frame_s_plan()

    read = read_plan_write(before, before.explode("tags", empty_as_null=True))

    assert read.overwritten(_ACCOUNTED | {"gone"}) == _ACCOUNTED


def test_a_join_rebuilt_over_another_right_hand_table_is_unreadable() -> None:
    """The plan's text names a table in memory by its columns alone.

    Two right-hand tables of one schema print alike, so the reader compares
    the memory of every table the shared steps scan, and a plan whose join
    now reads another table is not the plan the frame held.
    """
    rates = pl.DataFrame({"policy_id": [1, 2], "rate": [0.1, 0.2]})
    other = pl.DataFrame({"policy_id": [1, 2], "rate": [0.5, 0.6]})
    before = _BOOK.lazy().join(rates.lazy(), on="policy_id", how="left")
    after = _BOOK.lazy().join(other.lazy(), on="policy_id", how="left")
    same = _BOOK.lazy().join(rates.lazy(), on="policy_id", how="left")
    assert before.explain(optimized=False) == after.explain(optimized=False)

    assert read_plan_write(before, after).readable is False
    assert read_plan_write(before, same).readable is True


# Plans that print alike and hold different values: what the reader's own
# view of each expression shows and the plan's text does not.
_PRINTED_ALIKE = [
    pytest.param(
        pl.lit(pl.Series("s", [1.0, 2.0, 3.0])).alias("s"),
        pl.lit(pl.Series("s", [7.0, 8.0, 9.0])).alias("s"),
        id="a_column_of_values_handed_over_as_a_literal",
    ),
    pytest.param(
        pl.lit(pl.Series("s", ["a", "b", "c"])).alias("s"),
        pl.lit(pl.Series("s", ["a", "z", "c"])).alias("s"),
        id="a_column_of_text_handed_over_as_a_literal",
    ),
    pytest.param(
        pl.lit([1.5, 1.25, 1.1, 1.0]).alias("loading"),
        pl.lit([1.5, 1.25, 1.2, 1.0]).alias("loading"),
        id="a_list_whose_middle_the_text_leaves_out",
    ),
    pytest.param(
        pl.lit([0.1 + 0.2, 0.3]).alias("loading"),
        pl.lit([0.3, 0.3]).alias("loading"),
        id="a_list_whose_values_the_text_rounds",
    ),
    pytest.param(
        pl.col("premium").round(2).alias("rounded"),
        pl.col("premium").round(3).alias("rounded"),
        id="a_rounding_to_other_places",
    ),
    pytest.param(
        pl.col("premium").cum_sum().alias("running"),
        pl.col("premium").cum_sum(reverse=True).alias("running"),
        id="a_running_total_taken_the_other_way",
    ),
]


@pytest.mark.parametrize(("held", "rebuilt"), _PRINTED_ALIKE)
def test_a_plan_rebuilt_with_values_its_text_does_not_print_is_unreadable(
    held: pl.Expr, rebuilt: pl.Expr
) -> None:
    """The text prints both plans alike; what the plan holds tells them apart."""
    before = _BOOK.lazy().with_columns(held)
    after = _BOOK.lazy().with_columns(rebuilt)
    assert before.explain(optimized=False) == after.explain(optimized=False)

    assert read_plan_write(before, after).readable is False


def test_equal_values_handed_over_again_read_as_the_same_plan() -> None:
    """Values in new memory are compared on the values, so a plan rebuilt alike reads."""
    before = _BOOK.lazy().with_columns(pl.lit(pl.Series("s", [1.0, 2.0, 3.0])))
    after = _BOOK.lazy().with_columns(pl.lit(pl.Series("s", [1.0, 2.0, 3.0])))

    read = read_plan_write(before, after)

    assert (read.readable, read.wrote) == (True, frozenset())


def test_a_write_over_a_plan_holding_values_and_a_window_reads_as_written() -> None:
    """What the reader compares reads the same twice, so a plain write reads."""
    before = _BOOK.lazy().with_columns(
        pl.lit(pl.Series("s", [1.0, 2.0, 3.0])),
        pl.col("premium").sum().over("policy_id").alias("total"),
        pl.col("premium").round(2).alias("rounded"),
    )
    after = before.with_columns(pl.lit(0.0).alias("total"))

    read = read_plan_write(before, after)

    assert (read.readable, read.wrote) == (True, frozenset({"total"}))


def test_an_expression_naming_its_columns_is_read_over_those_columns_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty frame of every column costs about a millisecond at a hundred."""
    built: list[list[str]] = []
    frame = pl.LazyFrame

    def counted(*args: Any, **kwargs: Any) -> pl.LazyFrame:  # noqa: ANN401
        built.append(list(kwargs.get("schema") or {}))
        return frame(*args, **kwargs)

    monkeypatch.setattr(plan_writes.pl, "LazyFrame", counted)
    schema = {f"c{n}": pl.Float64 for n in range(50)}

    named = plan_writes.outputs_of(schema, (pl.col("c1") * 2).alias("d"))
    selected = plan_writes.outputs_of(schema, pl.col(pl.Float64).set_sorted())

    assert [(column.name, column.kept) for column in named] == [("d", None)]
    assert len(selected) == 50
    assert built == [["c1"], list(schema)]


def test_a_kept_reading_of_the_plan_reads_alike() -> None:
    """The frame keeps a write's reading for the next one, which reads the same."""
    before = _the_frame_s_plan()
    first = before.with_columns(pl.lit(1.0).alias("sneaky"))
    second = first.with_columns(pl.lit(0.0).alias("commission"))
    kept = read_plan_write(before, first).reading
    assert kept is not None

    fresh = read_plan_write(first, second)
    reused = read_plan_write(first, second, before_reading=kept)

    assert (reused.readable, reused.wrote) == (fresh.readable, fresh.wrote)
    assert reused.wrote == frozenset({"commission"})


def test_a_plan_that_does_not_resolve_leaves_nothing_to_report() -> None:
    """Collecting it fails, and that failure names the plan's own fault."""
    before = _the_frame_s_plan()

    read = read_plan_write(before, before.select(pl.col("absent")))

    assert read.overwritten(_ACCOUNTED) == frozenset()


def test_a_write_whose_columns_could_not_be_read_at_all_vouches_for_nothing() -> None:
    """Not even the plan's columns: every column the frame accounted for is unvouched."""
    read = PlanWrite(resolves=True, readable=False)

    assert read.overwritten(_ACCOUNTED) == _ACCOUNTED


# --- the reader never raises into the line that wrote the plan -----------------


def test_a_traverser_that_fails_is_an_unreadable_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(_: pl.LazyFrame) -> None:
        msg = "the traverser moved"
        raise RuntimeError(msg)

    before = _the_frame_s_plan()
    after = before.with_columns(pl.lit(0.0).alias("commission"))
    monkeypatch.setattr(plan_writes, "_traverser", broken)

    read = read_plan_write(before, after)

    assert (read.resolves, read.readable) == (True, False)
    assert read.overwritten(_ACCOUNTED) == _ACCOUNTED


def test_an_unreadable_write_records_what_the_reader_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model's line goes ahead; the debug log says what could not be read."""
    from loguru import logger

    def broken(_: pl.LazyFrame) -> None:
        msg = "the traverser moved"
        raise RuntimeError(msg)

    before = _the_frame_s_plan()
    after = before.with_columns(pl.lit(0.0).alias("commission"))
    monkeypatch.setattr(plan_writes, "_traverser", broken)
    said: list[str] = []
    sink = logger.add(
        lambda m: said.append(f"{m.record['message']} {m.record['exception']!r}"),
        level="DEBUG",
    )
    try:
        read = read_plan_write(before, after)
    finally:
        logger.remove(sink)

    assert read.readable is False
    (line,) = [m for m in said if "could not read" in m]
    assert "recorded as unreadable" in line
    assert "the traverser moved" in line


def test_a_traverser_that_panics_is_an_unreadable_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def panicking(_: pl.LazyFrame) -> None:
        raise PanicException("a panic in the plan")

    before = _the_frame_s_plan()
    after = before.with_columns(pl.lit(0.0).alias("commission"))
    monkeypatch.setattr(plan_writes, "_traverser", panicking)

    assert read_plan_write(before, after).readable is False


def test_a_plan_version_the_reader_was_not_written_for_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walking a version it has not met could read a filter where a rewrite sits."""
    before = _the_frame_s_plan()
    after = before.with_columns(pl.lit(0.0).alias("commission"))
    monkeypatch.setattr(plan_writes, "PLAN_VERSION", PLAN_VERSION + 1)

    read = read_plan_write(before, after)

    assert (read.resolves, read.readable) == (True, False)


def test_a_schema_that_fails_in_some_other_way_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither a resolved plan nor a refusal: the frame stops vouching for every column."""
    before = _the_frame_s_plan()
    after = before.with_columns(pl.lit(0.0).alias("commission"))

    def broken() -> None:
        msg = "not a Polars error"
        raise TypeError(msg)

    monkeypatch.setattr(after, "collect_schema", broken)

    read = read_plan_write(before, after)

    assert (read.resolves, read.readable, read.holds) == (True, False, None)


def test_the_plan_version_is_the_one_the_reader_was_written_against() -> None:
    """A Polars upgrade that moves the plan's version fails here, by name.

    The reader walks Polars' plan through the traverser Polars keeps for its
    GPU engine. A new major version is a plan this reader has not been
    checked against: read every step kind in ``_ROW_STEPS``,
    ``_ADDING_STEPS`` and ``_DEFINING_STEPS``, and every function in
    ``_KEEPING_FUNCTIONS`` and ``_ROW_MOVES`` with the amounts it carries,
    against the new traverser, and the plan text a nested plan prints, run
    this module, and only then move ``PLAN_VERSION``.
    """
    assert plan_version()[0] == PLAN_VERSION


# --- values another frame calculated -------------------------------------------


def _account(af: ActuarialFrame) -> ValuesAccount:
    """Return how ``af`` accounts for its last collect's columns."""
    counts = af._calculation_counts  # noqa: SLF001 -- the frame's own log
    return ValuesAccount(
        defined={
            column: Origin(f"{column}@{count}", None)
            for column, count in counts.items()
            if count > 0
        },
        arrived=frozenset(af._initial_columns),  # noqa: SLF001
    )


def _collected(af: ActuarialFrame, index: ComputedValues) -> pl.DataFrame:
    """Collect ``af``, note its values with ``index``, and return what came back."""
    values = af.collect()
    held = af._collected_values  # noqa: SLF001 -- what the frame vouches for
    assert held is not None
    index.note(held, lambda: _account(af))
    return values


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "policy_id": [1, 2, 3, 4],
            "issue_age": [35, 45, 55, 65],
            "premium": [100.0, 200.0, 300.0, 400.0],
        }
    )


def test_a_calculated_column_is_found_under_its_own_name() -> None:
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.reserve = af.premium * 0.5
    values = _collected(af, index)

    assert index.computed(values) == {"reserve": Origin("reserve@1")}


def test_a_calculated_column_renamed_in_polars_is_found_under_the_new_name() -> None:
    """The setup step's reshaping keeps the memory, so the origin follows the column."""
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.reserve = af.premium * 0.5
    values = _collected(af, index)
    reshaped = values.with_columns(pl.lit(1).alias("flag")).rename({"reserve": "held"})

    assert index.computed(reshaped) == {"held": Origin("reserve@1")}


def test_a_definition_that_copies_an_input_holds_the_data_s_values() -> None:
    """``af.age = af.issue_age`` shares the input's memory, and the data's values stay the data's."""
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.age = af.issue_age
    values = _collected(af, index)

    assert index.computed(values) == {}
    assert index.computed(values.rename({"age": "years"})) == {}


def test_the_template_s_setup_aliases_hold_the_data_s_values() -> None:
    """Collect, alias in Polars, rebuild: the shape every model starts from says nothing."""
    index = ComputedValues()
    plain = ActuarialFrame(_book().rename({"issue_age": "Issue Age"}))
    values = _collected(plain, index)
    setup = values.with_columns(pl.col("Issue Age").alias("issue_age"))

    assert index.computed(setup) == {}

    calculated = ActuarialFrame(_book().rename({"issue_age": "Issue Age"}))
    calculated.reserve = calculated.premium * 0.5
    later = _collected(calculated, index).with_columns(
        pl.col("Issue Age").alias("issue_age")
    )

    assert index.computed(later) == {"reserve": Origin("reserve@1")}


def test_values_nobody_holds_any_longer_are_not_found() -> None:
    """Once the frame has moved on and the caller has let go, the memory is no proof.

    A second container over the same buffers still holds them, so the
    numbers are still there; what is gone is anybody the index can ask
    whether that memory is still the collect's, and it says nothing rather
    than guess.
    """
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.reserve = af.premium * 0.5
    values = af.collect()
    held = af._collected_values  # noqa: SLF001 -- what the frame vouches for
    assert held is not None
    index.note(held, lambda: _account(af), kept_while=values)
    del held
    shared = values.select(pl.all())
    del values
    af.total = af.reserve + 1.0
    gc.collect()

    assert index.computed(shared) == {}


def test_values_the_caller_still_holds_are_found_after_the_frame_moves_on() -> None:
    """The frame lets its copy go as its plan moves; the caller's DataFrame keeps it."""
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.reserve = af.premium * 0.5
    values = af.collect()
    held = af._collected_values  # noqa: SLF001 -- what the frame vouches for
    assert held is not None
    index.note(held, lambda: _account(af), kept_while=values)
    del held
    af.total = af.reserve + 1.0
    gc.collect()

    assert af._collected_values is None  # noqa: SLF001 -- the frame let go
    assert index.computed(values) == {"reserve": Origin("reserve@1", None)}


def test_values_a_temporary_frame_collected_are_found() -> None:
    """``ActuarialFrame(model().collect())``: the frame is gone, its values are not."""

    def model() -> ActuarialFrame:
        af = ActuarialFrame(_book())
        af.reserve = af.premium * 0.5
        return af

    rebuilt = ActuarialFrame(model().collect())

    assert [(hole.column, hole.reason) for hole in rebuilt.graph.holes()] == [
        ("reserve", "rebuilt")
    ]


@pytest.mark.parametrize(
    "copy",
    [
        pytest.param(lambda v: v.sort("premium", descending=True), id="sorted"),
        pytest.param(lambda v: v.filter(pl.col("premium") > 100), id="filtered"),
        pytest.param(
            lambda v: v.with_columns(pl.col("reserve").cast(pl.Float32)), id="cast"
        ),
        pytest.param(lambda v: v.slice(1), id="sliced"),
    ],
)
def test_copied_values_are_not_found(
    copy: Callable[[pl.DataFrame], pl.DataFrame],
) -> None:
    """Only shared memory is evidence; a copy is new memory, and says nothing."""
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.reserve = af.premium * 0.5
    values = _collected(af, index)

    assert "reserve" not in index.computed(copy(values))


def test_text_lists_and_structs_are_found_by_their_memory() -> None:
    index = ComputedValues()
    values = (
        _book()
        .lazy()
        .with_columns(
            pl.format("P-{}", pl.col("policy_id")).alias("label"),
            pl.concat_list("premium", "premium").alias("flows"),
            pl.struct("premium", "issue_age").alias("pair"),
        )
        .collect()
    )
    calculated = {name: Origin(f"{name}@1") for name in ("label", "flows", "pair")}
    index.remember(
        values,
        ValuesAccount(defined=calculated, arrived=frozenset(_book().columns)),
    )

    assert index.computed(values.select("label", "flows", "pair")) == calculated


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(pl.DataFrame({"reserve": [None, None]}), id="all_null"),
        pytest.param(
            pl.DataFrame({"reserve": []}, schema={"reserve": pl.Float64}), id="empty"
        ),
        pytest.param(
            pl.DataFrame({"reserve": [object(), object()]}), id="python_objects"
        ),
    ],
)
def test_a_column_with_no_memory_to_compare_is_never_found(data: pl.DataFrame) -> None:
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.reserve = af.premium * 0.5
    _collected(af, index)

    assert index.computed(data) == {}


def test_each_noted_frame_is_accounted_for_once() -> None:
    """The account is read the first time a check needs it, and never again."""
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.reserve = af.premium * 0.5
    values = af.collect()
    held = af._collected_values  # noqa: SLF001
    assert held is not None
    calls: list[int] = []

    def account() -> ValuesAccount:
        calls.append(1)
        return _account(af)

    index.note(held, account)
    for _ in range(3):
        assert index.computed(values) == {"reserve": Origin("reserve@1")}

    assert calls == [1]


def test_a_frame_that_calculated_nothing_indexes_nothing() -> None:
    """Its values could only ever say "the data's", so they are not kept."""
    index = ComputedValues()
    af = ActuarialFrame(_book())
    values = _collected(af, index)

    assert index.computed(values) == {}
    assert index._entries == {}  # noqa: SLF001


def test_an_account_that_fails_leaves_its_frame_out() -> None:
    index = ComputedValues()
    good = ActuarialFrame(_book())
    good.reserve = good.premium * 0.5
    found = _collected(good, index)
    bad = ActuarialFrame(_book())
    bad.reserve = bad.premium * 0.5
    bad.collect()
    held = bad._collected_values  # noqa: SLF001
    assert held is not None

    def failing() -> ValuesAccount:
        msg = "the frame could not say"
        raise RuntimeError(msg)

    index.note(held, failing)

    assert index.computed(found) == {"reserve": Origin("reserve@1")}


def test_each_frame_judges_its_own_memory() -> None:
    """A frame that calculated the column says so; one that only received it does not veto it.

    The veto is a frame's own: where one frame holds the memory as both a
    calculation and an arriving column, the values are that frame's data.
    Another frame that was merely handed the values speaks for its own
    columns and not for the first frame's calculation.
    """
    index = ComputedValues()
    values = _book().lazy().with_columns((pl.col("premium") * 2).alias("x")).collect()
    received = values.with_columns((pl.col("premium") * 3).alias("y"))
    index.remember(values, ValuesAccount(defined={"x": Origin("x@1")}))
    index.remember(
        received,
        ValuesAccount(defined={"y": Origin("y@1")}, arrived=frozenset({"x"})),
    )

    assert index.computed(values.select("x")) == {"x": Origin("x@1")}


def test_a_hundred_retained_frames_cost_one_lookup_per_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model-point batching keeps a frame per chunk alive; a check still asks once per column."""
    index = ComputedValues()
    retained: list[tuple[ActuarialFrame, pl.DataFrame]] = []
    for batch in range(100):
        af = ActuarialFrame(_book().with_columns(pl.col("premium") + batch))
        af.reserve = af.premium * 0.5
        retained.append((af, _collected(af, index)))
    index.computed(pl.DataFrame())  # the first check indexes every frame once
    lookups: list[str] = []
    key = plan_writes._key  # noqa: SLF001

    def counted(series: pl.Series) -> Any:
        lookups.append(series.name)
        return key(series)

    monkeypatch.setattr(plan_writes, "_key", counted)
    fresh = pl.DataFrame({f"c{i}": [float(i)] * 4 for i in range(20)})

    assert index.computed(fresh) == {}
    assert len(lookups) == 20
    assert index.computed(retained[57][1]) == {"reserve": Origin("reserve@1")}


def test_a_column_given_new_nulls_over_the_same_values_is_other_values() -> None:
    """A conditional can hand back a column's buffer under a new validity bitmap.

    ``when(...).then(pl.col("reserve"))`` in Polars keeps the reserve's values
    buffer and nulls the rows the condition rejects. Those are other values,
    so the bitmap is part of what is compared.
    """
    index = ComputedValues()
    values = _book().with_columns((pl.col("premium") * 0.5).alias("reserve"))
    index.remember(
        values,
        ValuesAccount(
            defined={"reserve": Origin("reserve@1")}, arrived=frozenset(_book().columns)
        ),
    )
    masked = values.with_columns(
        pl.when(pl.col("issue_age") > 40).then(pl.col("reserve")).alias("masked")
    )
    shared = masked["masked"]._get_buffer_info()[0]  # noqa: SLF001
    assert shared == masked["reserve"]._get_buffer_info()[0]  # noqa: SLF001
    assert masked["masked"].null_count() == 1

    assert index.computed(masked.select("masked")) == {}
    assert index.computed(masked.select("reserve")) == {"reserve": Origin("reserve@1")}


def test_a_check_reads_no_column_of_a_type_no_calculation_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text columns cannot hold a numeric calculation's memory, so they are not read."""
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.reserve = af.premium * 0.5
    _collected(af, index)
    index.computed(pl.DataFrame())
    lookups: list[str] = []
    key = plan_writes._key  # noqa: SLF001

    def counted(series: pl.Series) -> Any:
        lookups.append(series.name)
        return key(series)

    monkeypatch.setattr(plan_writes, "_key", counted)
    text = pl.DataFrame({"product": ["TERM", "WL"], "sex": ["F", "M"]})

    assert index.computed(text) == {}
    assert lookups == []


def test_only_arrivals_that_could_share_a_calculation_s_memory_are_indexed() -> None:
    """An arriving column of a type no calculated column has can never veto one."""
    index = ComputedValues()
    af = ActuarialFrame(_book().with_columns(pl.lit("TERM").alias("product")))
    af.reserve = af.premium * 0.5
    values = _collected(af, index)
    index.computed(values)

    indexed = {
        entry.column
        for entries in index._entries.values()  # noqa: SLF001
        for entry in entries
    }

    assert indexed == {"premium", "reserve"}


def test_a_calculated_literal_column_is_found_like_any_other_calculation() -> None:
    """``af.flag = 1.0`` is a calculation the frame logged, and its memory is its own."""
    index = ComputedValues()
    af = ActuarialFrame(_book())
    af.flag = 1.0
    values = _collected(af, index)

    assert index.computed(values.select("flag")) == {"flag": Origin("flag@1")}
