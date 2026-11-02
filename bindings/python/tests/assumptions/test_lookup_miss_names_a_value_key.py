# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A lookup miss names a key passed as a value by the dimension it was passed for.

A key written as a value -- ``lookup(product="pension", age=af.age)`` -- reaches
the lookup kernel as a Polars literal, whose name is the engine's placeholder
``literal``. The miss used to name the key columns ``'age', 'literal'`` and the
missed key ``(age=40, literal="pension")``, naming nothing the author wrote. It
now names the table's key column for that operand (``product="pension"``; a
text value prints in quotes), while an operand that is a column keeps the
column's own name (``attained_age=77``), which is the one the author wrote.
"""

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table


def _rates_table() -> Table:
    return Table(
        name="miss_names_value_key_rates",
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


def test_a_value_key_that_misses_is_named_by_its_dimension() -> None:
    """The missed key reads ``product="pension"``, never ``literal="pension"``."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    af.rate = _rates_table().lookup(product="pension", age=af.age)
    with pytest.raises(Exception, match="has missing keys") as caught:
        af.collect()
    message = str(caught.value)
    assert "literal" not in message
    assert "'product'" in message
    assert 'product="pension"' in message


def test_a_column_key_keeps_the_name_the_author_wrote() -> None:
    """An operand that is a column is still named by that column."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "attained_age": [77]}))
    af.rate = _rates_table().lookup(product="annuity", age=af.attained_age)
    with pytest.raises(Exception, match="has missing keys") as caught:
        af.collect()
    message = str(caught.value)
    assert "attained_age=77" in message
    assert 'product="annuity"' in message
    assert "literal" not in message
