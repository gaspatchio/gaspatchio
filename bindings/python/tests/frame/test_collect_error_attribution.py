# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Collect-time errors must name the offending column.

Regression test for #39. A lazy chain failing at collect() surfaced a raw
Polars error ("list lengths differed at index 0: 6 != 3") that never said
WHICH assigned column produced it — a long hunt in a 50-column model.
Assign-time errors were already attributed; collect-time ones were not.

The fallback contract matters as much as the feature: if attribution is
ambiguous the ORIGINAL error must pass through untouched. A wrong column name
costs more than no column name.
"""

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


def _ragged_frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1],
                "six": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
                "three": [[1.0, 2.0, 3.0]],
            }
        )
    )


def test_shape_error_names_the_offending_column() -> None:
    """The reported case: a ragged list op fails without naming its column."""
    af = _ragged_frame()
    af.mismatched = af.six * af.three
    with pytest.raises(Exception, match="mismatched") as excinfo:
        af.collect()
    assert "mismatched" in str(excinfo.value)


def test_attribution_picks_the_right_column_in_a_chain() -> None:
    """Only the broken column is named — never its healthy neighbours."""
    af = _ragged_frame()
    af.fine_one = af.six * 2.0
    af.fine_two = af.three + 1.0
    af.broken = af.six - af.three
    with pytest.raises(Exception, match="broken") as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "broken" in message
    assert "fine_one" not in message
    assert "fine_two" not in message


def test_unattributable_error_passes_through_unchanged() -> None:
    """The fallback contract: no recorded assignment, no decoration.

    The broken operation is baked into the input plan before the
    ActuarialFrame ever sees it, so nothing was recorded and replay has
    nothing to name. The original Polars error must arrive untouched —
    a wrong column name costs more than no column name.
    """
    lf = pl.LazyFrame(
        {
            "policy_id": [1],
            "six": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
            "three": [[1.0, 2.0, 3.0]],
        }
    ).with_columns((pl.col("six") * pl.col("three")).alias("baked_in"))
    af = ActuarialFrame(lf)
    with pytest.raises(Exception, match="list lengths differed") as excinfo:
        af.collect()
    assert "Failing column" not in str(excinfo.value)


def test_structural_mutation_resets_attribution_rather_than_misattributing() -> None:
    """After an unrecorded plan change, attribution restarts cleanly.

    filter() mutates the plan without being recorded, so earlier
    assignments are no longer sound to replay. The next assignment opens a
    fresh window against the post-filter baseline — the broken column
    assigned AFTER the filter is still attributed correctly.
    """
    af = _ragged_frame()
    af.fine_one = af.six * 2.0
    af = af.filter(pl.col("policy_id") == 1)
    af.broken = af.six - af.three
    with pytest.raises(Exception, match="broken") as excinfo:
        af.collect()
    message = str(excinfo.value)
    assert "broken" in message
    assert "fine_one" not in message
