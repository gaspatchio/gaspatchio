# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A bare string is a dimension VALUE, not a column name.

Regression test for #37. ``tbl.lookup(product="annuity", age=af.age)`` used to
route the string to ``pl.col(...)``, so it was read as a column name and failed
with ``ColumnNotFoundError: Column 'annuity' not found`` — pointing away from
the mistake. The only way to express the value was ``pl.lit("annuity")``, which
put Polars in the middle of an ordinary actuarial lookup.

A bare string now means the value, which is what ``VLOOKUP(product, ...)``
means and what an actuary reads. Columns are referenced the gaspatchio way:
``af.product``, ``af["product"]``, or ``pl.col("product")`` if you want Polars.

**Breaking**, but safely so: a caller who previously passed a column name as a
bare string now gets a lookup miss — and since #24, misses raise by default and
name the key that missed.
"""

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table


def _rates_table() -> Table:
    return Table(
        name="bare_string_key_rates",
        source=pl.DataFrame(
            {
                "product": ["annuity", "annuity", "term", "term"],
                "age": [40, 41, 40, 41],
                "rate": [0.001, 0.002, 0.003, 0.004],
            }
        ),
        dimensions={"product": "product", "age": "age"},
        value="rate",
    )


def test_bare_string_is_the_value() -> None:
    """The reported case now works, with no Polars import needed."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    af.rate = _rates_table().lookup(product="annuity", age=af.age)
    assert af.collect()["rate"].to_list() == [0.001]


def test_bare_string_selects_the_right_row() -> None:
    """Different values select different rows, rather than collapsing to one."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [41]}))
    table = _rates_table()
    af.annuity = table.lookup(product="annuity", age=af.age)
    af.term = table.lookup(product="term", age=af.age)
    out = af.collect()
    assert out["annuity"].to_list() == [0.002]
    assert out["term"].to_list() == [0.004]


def test_pl_lit_still_works() -> None:
    """The explicit Polars form stays valid — it is just no longer required."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    af.rate = _rates_table().lookup(product=pl.lit("annuity"), age=af.age)
    assert af.collect()["rate"].to_list() == [0.001]


def test_column_reference_via_attribute() -> None:
    """The gaspatchio way to key on a column.

    The frame column is ``policy_product`` rather than ``product`` because
    ``af.product`` collides with an existing frame attribute — the case
    AGENTS.md already covers by telling you to use bracket access.
    """
    af = ActuarialFrame(
        pl.DataFrame(
            {"policy_id": [1], "age": [40], "policy_product": ["annuity"]}
        )
    )
    af.rate = _rates_table().lookup(product=af.policy_product, age=af.age)
    assert af.collect()["rate"].to_list() == [0.001]


def test_column_reference_via_brackets() -> None:
    """Bracket access, for names that are keywords or contain spaces."""
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "age": [40], "product": ["annuity"]})
    )
    af.rate = _rates_table().lookup(product=af["product"], age=af.age)
    assert af.collect()["rate"].to_list() == [0.001]


def test_pl_col_still_references_a_column() -> None:
    """Explicit pl.col keeps its Polars meaning."""
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "age": [40], "product": ["annuity"]})
    )
    af.rate = _rates_table().lookup(product=pl.col("product"), age=af.age)
    assert af.collect()["rate"].to_list() == [0.001]


def test_a_column_name_passed_as_a_string_now_misses_loudly() -> None:
    """The breaking case fails loudly, naming the key that missed.

    Someone who meant the column and wrote the bare string gets a miss rather
    than silently wrong numbers, because #24 made misses raise.
    """
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "age": [40], "product": ["annuity"]})
    )
    af.rate = _rates_table().lookup(product="product", age=af.age)
    with pytest.raises(Exception, match="missing keys") as excinfo:
        af.collect()
    assert "product" in str(excinfo.value)


def test_a_value_containing_quotes_is_handled() -> None:
    """Values travel as data and are never interpolated into generated code."""
    table = Table(
        name="quoted_values",
        source=pl.DataFrame({"label": ['say "hi"', "plain"], "rate": [0.5, 0.6]}),
        dimensions={"label": "label"},
        value="rate",
    )
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1]}))
    af.rate = table.lookup(label='say "hi"')
    assert af.collect()["rate"].to_list() == [0.5]
