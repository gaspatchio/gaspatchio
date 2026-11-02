# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A model's column cannot take a name under the frame's own working prefixes.

The frame keeps two kinds of working column in its plan: a compiled
rollforward's result under ``__rollforward_``, and the values of a definition a
later assignment replaced under ``__gaspatchio_retained__``. Every reading of
its results takes both off by prefix, so a column of the model's own under
either prefix used to vanish from ``collect()`` without a word while the
calculation graph still drew it and its edges.

Every door a model's column comes through now refuses such a name, naming the
prefix and the rename that is the next move: the data a frame is built from,
an assignment, a rename and a join. The frame's own working columns reach the
plan through none of those doors, and they still work.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.rollforward import compile_rollforward
from gaspatchio.scenarios import with_scenarios

if TYPE_CHECKING:
    from collections.abc import Callable

_RESERVED = ["__rollforward_notes", "__gaspatchio_retained__1__notes"]


def _frame() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": ["P1", "P2"], "sum_assured": [1000.0, 2000.0]})
    )
    af.claims = af.sum_assured * 0.01
    return af


def _recorded(af: ActuarialFrame) -> list[str]:
    return [record.column for record in af._calculation_records()]  # noqa: SLF001


def _assert_the_refusal(message: str, name: str) -> None:
    """Assert the refusal names the column, its prefix, and why it matters."""
    prefix = (
        "__rollforward_"
        if name.startswith("__rollforward_")
        else "__gaspatchio_retained__"
    )
    assert f"The column {name!r}" in message
    assert f"{prefix!r} is a prefix the frame keeps for its own working" in message
    assert "would vanish from the results without a word" in message
    assert repr(name.lstrip("_")) in message


@pytest.mark.parametrize("form", ["DataFrame", "LazyFrame", "dict"])
@pytest.mark.parametrize("name", _RESERVED)
def test_the_data_a_frame_is_built_from_cannot_carry_one(form: str, name: str) -> None:
    """The column is refused as it arrives, with the rename to make first."""
    data: dict[str, list[float]] = {"sum_assured": [1000.0, 2000.0], name: [0.5, 0.25]}
    built = {
        "DataFrame": pl.DataFrame(data),
        "LazyFrame": pl.LazyFrame(data),
        "dict": data,
    }[form]

    with pytest.raises(ValueError, match="is a prefix the frame keeps") as refusal:
        ActuarialFrame(built)

    message = str(refusal.value)
    _assert_the_refusal(message, name)
    assert "arrived with the data this frame was built from" in message
    assert f"df.rename({{{name!r}: {name.lstrip('_')!r}}})" in message
    assert f"or the key {name.lstrip('_')!r} in a dict" in message


def test_values_coming_back_cannot_carry_one() -> None:
    """``continue_from=`` is a door the data arrives through, too."""
    af = _frame()
    values = af.collect().with_columns(pl.lit(1.0).alias("__rollforward_draw"))

    with pytest.raises(ValueError, match="arrived with the data") as refusal:
        ActuarialFrame(values, continue_from=af)

    _assert_the_refusal(str(refusal.value), "__rollforward_draw")


@pytest.mark.parametrize(
    "write",
    [
        lambda af, name: af.__setitem__(name, af.sum_assured * 2),
        lambda af, name: af.with_columns((pl.col("sum_assured") * 2).alias(name)),
        lambda af, name: af.select(
            "policy_id", "sum_assured", "claims", pl.col("claims").alias(name)
        ),
        lambda af, name: af.select(
            "policy_id", "sum_assured", "claims", **{name: af.claims}
        ),
    ],
    ids=["assignment", "with_columns", "select-alias", "select-named"],
)
@pytest.mark.parametrize("name", _RESERVED)
def test_a_column_the_model_writes_cannot_take_one(
    write: Callable[[ActuarialFrame, str], object], name: str
) -> None:
    """Refused before the frame moves: no column, nothing logged, same results."""
    af = _frame()
    columns_before = list(af.columns)
    recorded_before = _recorded(af)

    with pytest.raises(ValueError, match="is a prefix the frame keeps") as refusal:
        write(af, name)

    message = str(refusal.value)
    _assert_the_refusal(message, name)
    assert "is being written to this frame" in message
    assert "Give it a name without the prefix" in message
    assert list(af.columns) == columns_before
    assert _recorded(af) == recorded_before
    assert af.collect().columns == columns_before


@pytest.mark.parametrize("name", _RESERVED)
def test_a_rename_cannot_give_one(name: str) -> None:
    """The new name is refused, and the old one is still the frame's."""
    af = _frame()

    with pytest.raises(ValueError, match="is a prefix the frame keeps") as refusal:
        af.rename({"claims": name})

    message = str(refusal.value)
    _assert_the_refusal(message, name)
    assert "is the new name in this rename" in message
    assert af.columns == ["policy_id", "sum_assured", "claims"]
    assert af.collect().columns == ["policy_id", "sum_assured", "claims"]


@pytest.mark.parametrize("name", _RESERVED)
def test_a_join_cannot_bring_one_in(name: str) -> None:
    """The other table is renamed before the join, so the move says where."""
    af = _frame()
    other = pl.DataFrame({"policy_id": ["P1", "P2"], name: [0.1, 0.2]})

    with pytest.raises(ValueError, match="is a prefix the frame keeps") as refusal:
        af.join(other, on="policy_id")

    message = str(refusal.value)
    _assert_the_refusal(message, name)
    assert "arrives with the other table in this join" in message
    assert f"other.rename({{{name!r}: {name.lstrip('_')!r}}})" in message
    assert af.columns == ["policy_id", "sum_assured", "claims"]


def test_a_scenario_axis_cannot_be_named_with_one() -> None:
    """The axis is a column the frame gains, named by the caller's argument."""
    with pytest.raises(ValueError, match="is a prefix the frame keeps") as refusal:
        with_scenarios(
            _frame(), ["BASE", "UP"], scenario_column="__rollforward_scenario"
        )

    message = str(refusal.value)
    _assert_the_refusal(message, "__rollforward_scenario")
    assert "is the name passed as scenario_column=" in message
    assert (
        "Pass scenario_column= a name without the prefix, such as "
        "'rollforward_scenario'." in message
    )


@pytest.mark.parametrize(
    "stamp",
    [
        lambda af: af.date.add_duration(
            af.issue_date, "1y", new_col_name="__gaspatchio_retained__anniversary"
        ),
        lambda af: af.date.create_timeline(
            af.issue_date,
            af.maturity_date,
            freq="1mo",
            new_col_name="__gaspatchio_retained__anniversary",
        ),
    ],
    ids=["add_duration", "create_timeline"],
)
def test_a_date_column_the_frame_stamps_cannot_take_one(
    stamp: Callable[[ActuarialFrame], object],
) -> None:
    """``new_col_name=`` names a column the date verb writes onto the frame."""
    af = ActuarialFrame(
        {
            "issue_date": [datetime.date(2025, 1, 1)],
            "maturity_date": [datetime.date(2025, 3, 1)],
        }
    )

    with pytest.raises(ValueError, match="is a prefix the frame keeps") as refusal:
        stamp(af)

    message = str(refusal.value)
    _assert_the_refusal(message, "__gaspatchio_retained__anniversary")
    assert "is the name passed as new_col_name=" in message
    assert (
        "Pass new_col_name= a name without the prefix, such as "
        "'gaspatchio_retained__anniversary'." in message
    )
    assert af.columns == ["issue_date", "maturity_date"]


# The column a compiled rollforward works in, exactly as the kernel mints it,
# and a frame shaped like the batch file a scenario driver wrote before 1.0.
_KERNEL_COLUMN = "__rollforward_c7cd760b29bdad35"


def _a_batch_file_written_before_1_0() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "policy_id": ["P1", "P2"],
            "av": [[1005.0, 1010.05], [2010.0, 2020.1]],
            _KERNEL_COLUMN: [
                {"av@eop": [1005.0, 1010.05]},
                {"av@eop": [2010.0, 2020.1]},
            ],
            "scenario_id": ["BASE", "BASE"],
        }
    )


def test_a_batch_file_written_before_1_0_is_told_to_drop_the_kernel_column() -> None:
    """The kernel's own column is dropped, not renamed into a column of the model.

    run_to_parquet and for_each_scenario(return_full_grid=True) wrote it into
    every batch file before 1.0, so it comes back whenever one is read.
    """
    batch = _a_batch_file_written_before_1_0()

    with pytest.raises(ValueError, match="exactly the column a compiled") as refusal:
        ActuarialFrame(batch)

    message = str(refusal.value)
    assert "arrived with the data this frame was built from" in message
    assert "batch files before 1.0" in message
    assert f"df.drop({_KERNEL_COLUMN!r})" in message
    assert "rename" not in message
    assert ActuarialFrame(batch.drop(_KERNEL_COLUMN)).collect().columns == [
        "policy_id",
        "av",
        "scenario_id",
    ]


def test_a_join_against_a_batch_file_is_told_to_drop_it_from_the_other_table() -> None:
    """The same column arriving through a join is dropped from the other table."""
    af = _frame()
    other = _a_batch_file_written_before_1_0().select("policy_id", _KERNEL_COLUMN)

    with pytest.raises(ValueError, match="exactly the column a compiled") as refusal:
        af.join(other, on="policy_id")

    assert f"other.drop({_KERNEL_COLUMN!r})" in str(refusal.value)
    assert af.columns == ["policy_id", "sum_assured", "claims"]


@pytest.mark.parametrize(
    "name",
    [
        "__rollforward_C7CD760B29BDAD35",
        "__rollforward_c7cd760b29bdad3",
        "__rollforward_c7cd760b29bdad35x",
    ],
    ids=["upper-case", "fifteen-digits", "seventeen-characters"],
)
def test_a_name_that_only_resembles_the_kernel_column_is_told_to_rename(
    name: str,
) -> None:
    """Only the exact minted shape is the kernel's; anything else is a name."""
    with pytest.raises(ValueError, match="is a prefix the frame keeps") as refusal:
        ActuarialFrame(pl.DataFrame({"sum_assured": [1000.0], name: [0.5]}))

    message = str(refusal.value)
    assert "df.rename(" in message
    assert "df.drop(" not in message


def test_widening_a_frame_that_holds_no_working_columns_reads_no_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """with_scenarios looks for working columns only where the frame can hold some.

    A frame holds one only after a reassignment it retained, or once a
    rollforward has been compiled in the process. Anywhere else, resolving
    the widened plan's schema to look for them is a cost with no answer.
    """
    from gaspatchio.rollforward import _registry
    from gaspatchio.scenarios import _with_scenarios

    def must_not_run(_names: object) -> list[str]:
        msg = "the widened plan was searched for working columns"
        raise AssertionError(msg)

    monkeypatch.setattr(_registry, "has_entries", lambda: False)
    monkeypatch.setattr(_with_scenarios, "_working_columns", must_not_run)

    crossed = with_scenarios(_frame(), ["BASE", "UP"])

    assert crossed.collect().height == 4


@pytest.mark.parametrize(
    "name",
    [
        "_rollforward_notes",
        "rollforward_notes",
        "notes__rollforward_",
        "__rollforward",
        "__gaspatchio_retained_notes",
    ],
)
def test_a_name_that_only_resembles_a_prefix_is_an_ordinary_column(name: str) -> None:
    """Only the two prefixes themselves are reserved, matched from the start."""
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [1000.0], name: [0.5]}))
    af["claims"] = af["sum_assured"] * af[name]

    assert af.collect().columns == ["sum_assured", name, "claims"]


# A frame this wide maintains its cached schema one assignment at a time, which
# is the path that once left a replaced definition's values out of the cache.
_FILLERS = {"narrow": 0, "wide": 20}


def _fillers(width: str, rows: int) -> dict[str, list[float]]:
    return {f"filler_{i}": [0.0] * rows for i in range(_FILLERS[width])}


@pytest.mark.parametrize("width", list(_FILLERS))
def test_the_frames_own_working_columns_still_work(width: str) -> None:
    """A compiled rollforward and a replaced definition, across a scenario axis.

    Both kinds of working column reach the plan through no door, so neither
    is refused: they are minted, carried through the cross-join, read, and
    taken off the results as before -- and the widened frame no longer lists
    them among the model's columns.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "av_init": [1000.0],
                "fund_return": [[0.01] * 3],
                "fee": [[5.0] * 3],
                **_fillers(width, 1),
            }
        )
    )
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    af.loading = af.av_init * 0.01
    af.loading = af.av_init * 0.02
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].grow(af["fund_return"], label="growth").subtract(af["fee"], label="fee")
    compiled = compile_rollforward(b)
    af.av = compiled.expr_for("av")
    plan = list(af._schema or ())  # noqa: SLF001 -- the cached schema under test
    assert [name for name in plan if name.startswith("__rollforward_")]
    assert "__gaspatchio_retained__1__loading" in plan

    crossed = with_scenarios(af, ["BASE", "UP"])
    crossed.av_again = compiled.expr_for("av")
    crossed.loading = crossed.av_init * 0.03

    crossed_plan = list(crossed._schema or ())  # noqa: SLF001 -- as above
    assert [name for name in crossed_plan if name.startswith("__rollforward_")]
    assert "__gaspatchio_retained__1__loading" in crossed_plan
    assert "__gaspatchio_retained__2__loading" in crossed_plan
    assert not [name for name in crossed.columns if name.startswith("__")]

    result = crossed.collect()
    assert result.columns == [*af.columns, "scenario_id", "av_again"]
    assert result["av"].to_list() == result["av_again"].to_list()
    assert result["av"].to_list()[0] == pytest.approx([1005.0, 1010.05, 1015.1505])
    assert result["loading"].to_list() == [30.0, 30.0]
    retained = crossed._retained_values  # noqa: SLF001 -- what an export reads
    assert retained is not None
    assert retained["__gaspatchio_retained__1__loading"].to_list() == [10.0, 10.0]
    assert retained["__gaspatchio_retained__2__loading"].to_list() == [20.0, 20.0]


def _reassigned(width: str) -> ActuarialFrame:
    """Return a frame whose ``claims`` was written twice, so one is retained."""
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": ["P1", "P2"],
                "sum_assured": [1000.0, 2000.0],
                **_fillers(width, 2),
            }
        )
    )
    af.claims = af.sum_assured * 0.01
    af.claims = af.sum_assured * 0.02
    return af


@pytest.mark.parametrize("width", list(_FILLERS))
def test_a_select_that_carries_the_frames_working_columns_keeps_them_hidden(
    width: str,
) -> None:
    """``select(pl.all())`` carries a replaced definition along, as the plan does."""
    af = _reassigned(width)
    columns_before = list(af.columns)

    af.select(pl.all())

    assert af.columns == columns_before
    assert "__gaspatchio_retained__1__claims" in (af._schema or {})  # noqa: SLF001
    assert af.collect().columns == columns_before
