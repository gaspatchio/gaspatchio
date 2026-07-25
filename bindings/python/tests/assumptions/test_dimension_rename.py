# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The dimensions dict maps YOUR name -> SOURCE column name (issue #30).

The documented rename contract: ``dimensions={"duration": "policy_duration_yrs"}``
lets the model look up with its own vocabulary (``lookup(duration=...)``)
against a table whose source uses different column names. The shorthand
conversion previously discarded the dict key, so the rename never happened
and lookups failed with "No value provided for key column '<source name>'".
"""

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table
from gaspatchio_core.assumptions._dimensions import DataDimension


def test_renamed_scalar_dimension_lookup() -> None:
    table = Table(
        name="rename_scalar",
        source=pl.DataFrame(
            {
                "policy_duration_yrs": [1, 2, 3],
                "lapse_rate": [0.10, 0.07, 0.05],
            }
        ),
        dimensions={"duration": "policy_duration_yrs"},
        value="lapse_rate",
    )
    af = ActuarialFrame(pl.DataFrame({"duration": [2, 1, 3]}))
    af.rate = table.lookup(duration=af.duration)
    assert af.collect()["rate"].to_list() == pytest.approx([0.07, 0.10, 0.05])


def test_renamed_mixed_dimensions_lookup() -> None:
    """Two renamed dims (int + string) — the shape from the field report."""
    table = Table(
        name="rename_mixed",
        source=pl.DataFrame(
            {
                "AgeYears": [30, 30, 40, 40],
                "SmokerFlag": ["N", "Y", "N", "Y"],
                "rate": [0.001, 0.002, 0.003, 0.004],
            }
        ),
        dimensions={"age": "AgeYears", "smoker": "SmokerFlag"},
        value="rate",
    )
    af = ActuarialFrame(
        pl.DataFrame({"age": [30, 40, 40], "smoker": ["Y", "N", "Y"]})
    )
    af.rate = table.lookup(age=af.age, smoker=af.smoker)
    assert af.collect()["rate"].to_list() == pytest.approx([0.002, 0.003, 0.004])


def test_renamed_dimension_list_key_lookup() -> None:
    table = Table(
        name="rename_listkey",
        source=pl.DataFrame(
            {"AttainedAge": [30, 31, 32], "qx": [0.001, 0.002, 0.003]}
        ),
        dimensions={"age": "AttainedAge"},
        value="qx",
    )
    af = ActuarialFrame(pl.DataFrame({"ages": [[30, 31], [31, 32]]}))
    af.qx = table.lookup(age=af.ages)
    out = af.collect()["qx"].to_list()
    assert out[0] == pytest.approx([0.001, 0.002])
    assert out[1] == pytest.approx([0.002, 0.003])


def test_identity_mapping_unchanged() -> None:
    table = Table(
        name="rename_identity",
        source=pl.DataFrame({"age": [30, 40], "rate": [0.001, 0.002]}),
        dimensions={"age": "age"},
        value="rate",
    )
    af = ActuarialFrame(pl.DataFrame({"age": [40, 30]}))
    af.rate = table.lookup(age=af.age)
    assert af.collect()["rate"].to_list() == pytest.approx([0.002, 0.001])


def test_explicit_data_dimension_without_rename_to_uses_dict_key() -> None:
    """An explicit DataDimension under a differing dict key gets the same rename."""
    table = Table(
        name="rename_explicit",
        source=pl.DataFrame(
            {"DurationBand": [1, 2], "rate": [0.10, 0.07]}
        ),
        dimensions={"duration": DataDimension("DurationBand")},
        value="rate",
    )
    af = ActuarialFrame(pl.DataFrame({"duration": [2, 1]}))
    af.rate = table.lookup(duration=af.duration)
    assert af.collect()["rate"].to_list() == pytest.approx([0.07, 0.10])


def test_explicit_rename_to_still_looks_up_by_dimension_name() -> None:
    """rename_to controls the processed column; lookups speak YOUR name.

    Even when a user-set rename_to gives the processed key column a third
    name, the lookup vocabulary stays the dimensions dict key.
    """
    table = Table(
        name="rename_explicit_wins",
        source=pl.DataFrame({"Dur": [1, 2], "rate": [0.10, 0.07]}),
        dimensions={"duration": DataDimension("Dur", rename_to="dur_years")},
        value="rate",
    )
    af = ActuarialFrame(pl.DataFrame({"duration": [2, 1]}))
    af.rate = table.lookup(duration=af.duration)
    assert af.collect()["rate"].to_list() == pytest.approx([0.07, 0.10])
