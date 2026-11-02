# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A calculation handed to ``with_columns`` or ``select`` with no name of its own.

Polars names such an expression after the first column it reads, so its
answer lands on that column. ``af.with_columns(table.lookup(age=af.age))``
wrote the mortality rate over ``age``: every later ``af.age`` read the rate,
nothing raised, and the record filed ``age`` as a calculation reading the
table. The frame now refuses a calculation that would overwrite a column it
holds under a name the author never gave, and names the two ways to say
which column is meant. A name the author did give -- even the column's own
-- is the reassignment idiom, stated, and a column handed back as it stands
replaces nothing; both still pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame({"policy_id": [1, 2], "age": [40, 41]})


def _table() -> Table:
    return Table(
        name="unnamed_overwrite_q",
        source=pl.DataFrame({"age": [40, 41], "rate": [0.01, 0.02]}),
        dimensions={"age": "age"},
        value="rate",
    )


_REPLACING: dict[str, Callable[[ActuarialFrame], object]] = {
    "a_lookup_keyed_on_the_column": lambda af: _table().lookup(age=af.age),
    "a_formula_over_the_column": lambda af: af.age + 1,
    "a_polars_expression_over_the_column": lambda _af: pl.col("age") * 2,
    "a_cast_to_another_type": lambda _af: pl.col("age").cast(pl.Float64),
}


@pytest.mark.parametrize("door", ["with_columns", "select"])
@pytest.mark.parametrize("build", _REPLACING.values(), ids=_REPLACING.keys())
def test_an_unnamed_calculation_over_a_column_is_refused(
    door: str, build: Callable[[ActuarialFrame], object]
) -> None:
    """The column it reads is the column it would replace, and nobody said so."""
    af = ActuarialFrame(_BOOK)
    expression = build(af)

    with pytest.raises(ValueError, match=r'overwrite the column "age"') as raised:
        getattr(af, door)(expression)

    message = str(raised.value)
    assert f"This {door}()" in message
    if door == "select":
        assert "select(..., <new_column>=<expression>)" in message
        assert "select(..., age=<expression>)" in message
    else:
        assert "af.<new_column> = <expression>" in message
        assert 'af["age"] = <expression>' in message
    # Polars' alias is named only where the value written has one.
    aliasable = isinstance(expression, pl.Expr)
    assert ('.alias("<new_column>")' in message) is aliasable
    assert ('.alias("age")' in message) is aliasable


def test_a_refused_lookup_leaves_the_key_column_holding_its_values() -> None:
    """The issue's line: refused, and ``age`` still reads the ages."""
    af = ActuarialFrame(_BOOK)

    with pytest.raises(ValueError, match="no name of its own"):
        af.with_columns(_table().lookup(age=af.age))

    assert af.collect()["age"].to_list() == [40, 41]
    assert "age" not in {entry.column for entry in af._calculations}  # noqa: SLF001


def test_a_lookup_given_a_name_adds_the_column_beside_its_key() -> None:
    """With an alias the rate is its own column and ``age`` is untouched."""
    af = ActuarialFrame(_BOOK)
    af = af.with_columns(_table().lookup(age=af.age).alias("q"))

    out = af.collect()
    assert out["age"].to_list() == [40, 41]
    assert out["q"].to_list() == [0.01, 0.02]


_STATED_OR_CARRIED: dict[str, Callable[[ActuarialFrame], object]] = {
    "a_lookup_aliased_to_the_column_s_own_name": lambda af: (
        _table().lookup(age=af.age).alias("age")
    ),
    "a_polars_alias_of_the_column_s_own_name": lambda _af: (pl.col("age") + 1).alias(
        "age"
    ),
    "the_column_itself": lambda af: af.age,
    "pl_col_of_the_column": lambda _af: pl.col("age"),
    "a_cast_to_the_type_it_has": lambda _af: pl.col("age").cast(pl.Int64),
    "a_named_series": lambda _af: pl.Series("age", [50, 51]),
}


@pytest.mark.parametrize(
    "build", _STATED_OR_CARRIED.values(), ids=_STATED_OR_CARRIED.keys()
)
def test_a_stated_name_or_a_carried_column_passes(
    build: Callable[[ActuarialFrame], object],
) -> None:
    """A name the author gave is a reassignment; a carried column replaces nothing."""
    af = ActuarialFrame(_BOOK)
    af = af.with_columns(build(af))

    assert af.collect().columns == ["policy_id", "age"]


def test_a_framework_formula_is_stated_by_assignment() -> None:
    """A formula has no alias; assigning it under the column's name is the move."""
    af = ActuarialFrame(_BOOK)
    af["age"] = af.age + 1

    assert af.collect()["age"].to_list() == [41, 42]


def test_select_keeps_its_keyword_names() -> None:
    """A keyword names the column, so a calculation under it is stated."""
    af = ActuarialFrame(_BOOK)
    af = af.select("policy_id", age=pl.col("age") + 1)

    assert af.collect()["age"].to_list() == [41, 42]
