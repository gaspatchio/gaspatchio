# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An ``Enum`` key is a label, and a lookup places it by the label it holds.

``pl.Enum(["BASE", "UP", "DOWN"])`` is a model point declaring its scenario
names: the shape that carries the permitted set in the column's own type, and
the one the framework used to refuse. An ``Enum`` is a ``Categorical`` with a
fixed category list, and for a key lookup the two are the same thing — the key
is the string the category holds — so the table now serves both.

Serving the key is where that stops. The calculation graph's type vocabulary
has no name for ``Enum``, so a column still carrying one is refused when the
artifact is built rather than when the rate is fetched — the refusal names the
column and teaches ``.cast(pl.String)``, which carries every label unchanged.
Keep the ``Enum`` for the lookup, and cast anything bound for an artifact.

The distinguishing feature of an ``Enum`` is that it numbers its categories in
the order they were declared, which need not be the order the table sorted its
labels into. A lookup that read the position instead of the name would return
some other scenario's rate, silently, so that is what these tests separate.

Both storages read the label. Hash storage once hashed a category by its
dictionary position instead, and a lookup refused with "the cause is how the
key is stored"; it now hashes the label's text, so the same key answers the
same rate whichever storage the table was given.
"""

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

# Declared order: UP=0, BASE=1, DOWN=2. Sorted order, which is how the table
# numbers its own labels: BASE=0, DOWN=1, UP=2. Every label sits at a different
# position in the two, so a position-reading lookup gets all three wrong.
_DECLARED_OUT_OF_ORDER = pl.Enum(["UP", "BASE", "DOWN"])

_RATES = {"BASE": 0.02, "UP": 0.08, "DOWN": 0.01}


def _rates_table(name: str, storage_mode: str = "auto") -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"scenario": list(_RATES), "rate": list(_RATES.values())}),
        dimensions={"scenario": "scenario"},
        value="rate",
        storage_mode=storage_mode,
    )


def _rate_for(table: Table, label: str, dtype: pl.DataType) -> float:
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": [1]}).with_columns(
            pl.lit(label).cast(dtype).alias("scenario_id")
        )
    )
    af.rate = table.lookup(scenario=af.scenario_id)
    return float(af.collect()["rate"][0])


@pytest.mark.parametrize("label", list(_RATES))
def test_an_enum_label_is_placed_by_its_name_not_its_declared_position(
    label: str,
) -> None:
    """The rate is the one the label names, under an order built to disagree."""
    table = _rates_table("enum_key_declared_out_of_order")
    assert _rate_for(table, label, _DECLARED_OUT_OF_ORDER) == _RATES[label]


@pytest.mark.parametrize("label", list(_RATES))
def test_an_enum_label_discounts_exactly_as_the_plain_string_does(
    label: str,
) -> None:
    """Storing the label as an ``Enum`` is a storage choice, not a modelling one."""
    table = _rates_table("enum_key_matches_string")
    assert _rate_for(table, label, _DECLARED_OUT_OF_ORDER) == _rate_for(
        table, label, pl.String
    )


def test_a_label_the_table_does_not_hold_still_misses_under_an_enum() -> None:
    """Serving the encoding must not turn an absent scenario into a rate.

    The refusal here names the key, because the key really is the problem.
    """
    table = _rates_table("enum_key_absent_label")
    with pytest.raises(Exception, match="missing keys") as excinfo:
        _rate_for(table, "STRESS", pl.Enum(["BASE", "STRESS"]))
    assert "STRESS" in str(excinfo.value)


@pytest.mark.parametrize("label", list(_RATES))
def test_hash_storage_places_an_enum_label_by_its_name(label: str) -> None:
    """Hash storage answers what array storage does, under the same disagreeing order.

    It once hashed the category's position in its own dictionary, missed a
    label the table held, and refused naming the encoding as the cause.
    """
    table = _rates_table("enum_key_hash_storage", storage_mode="hash")
    assert _rate_for(table, label, _DECLARED_OUT_OF_ORDER) == _RATES[label]
