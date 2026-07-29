# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A bare-string lookup key must name both remedies.

Regression test for #37. ``tbl.lookup(product="annuity", age=af.age)`` routes
the string to ``pl.col(...)``, so it is read as a column name and fails with
``ColumnNotFoundError: Column 'annuity' not found. Did you mean...`` — pointing
away from the actual mistake.

The framework deliberately does **not** guess that a bare string means a
literal. Inferring a meaning from a shape is what "Sharp knives, no magic"
forbids, and it would silently change behaviour for anyone legitimately passing
a column name as a string. The contract is a clear error naming both fixes.
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


def test_bare_string_key_error_names_both_remedies() -> None:
    """The error must offer the literal form and the column form."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    table = _rates_table()

    with pytest.raises(ValueError, match="no such column exists") as excinfo:
        table.lookup(product="annuity", age=af.age)

    message = str(excinfo.value)
    assert 'pl.lit("annuity")' in message, message
    assert 'af["annuity"]' in message, message
    assert "product" in message, message


def test_error_names_the_table_and_dimension() -> None:
    """Context matters more than the bare column name in a 50-column model."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    table = _rates_table()

    with pytest.raises(ValueError, match="no such column exists") as excinfo:
        table.lookup(product="annuity", age=af.age)

    message = str(excinfo.value)
    assert "bare_string_key_rates" in message, message


def test_pl_lit_key_still_works() -> None:
    """The documented remedy must actually resolve."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    table = _rates_table()
    af.rate = table.lookup(product=pl.lit("annuity"), age=af.age)
    out = af.collect()
    assert out["rate"].to_list() == [0.001]


def test_genuine_column_key_still_works() -> None:
    """A string naming a real column keeps its Polars meaning."""
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1], "age": [40], "product": ["annuity"]})
    )
    table = _rates_table()
    af.rate = table.lookup(product="product", age=af.age)
    out = af.collect()
    assert out["rate"].to_list() == [0.001]


def test_a_missing_column_key_gets_the_same_treatment() -> None:
    """Both readings are offered even when the user meant a column.

    Whether ``product="product"`` meant a literal or a column that does not
    exist is exactly the ambiguity — the framework cannot tell, and guessing
    is what this fix refuses to do. Naming both remedies is right either way,
    so this asserts the behaviour rather than pretending the two cases are
    distinguishable.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    table = _rates_table()

    with pytest.raises(ValueError, match="no such column exists") as excinfo:
        table.lookup(product="product", age=af.age)

    message = str(excinfo.value)
    assert 'pl.lit("product")' in message, message
    assert "policy_id, age" in message, message  # lists what IS available


def test_unrelated_missing_column_error_is_not_hijacked() -> None:
    """Errors that have nothing to do with lookup keys keep their own message.

    Re-wording every ColumnNotFoundError would trade one misleading error for
    another, so the targeted message fires only for bare-string dimension
    values.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))

    # Reaching for a column that does not exist already raises on access,
    # before any lookup is involved. That error must stay as it was.
    with pytest.raises(AttributeError) as excinfo:
        _ = af.does_not_exist

    message = str(excinfo.value)
    assert "was read as a column name" not in message, message
    assert "does_not_exist" in message, message


def test_error_arrives_at_the_call_site_not_at_collect() -> None:
    """The mistake is on the lookup line, so the error belongs there."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "age": [40]}))
    table = _rates_table()

    # No .collect() — constructing the lookup is enough to raise.
    with pytest.raises(ValueError, match="no such column exists"):
        table.lookup(product="annuity", age=af.age)
