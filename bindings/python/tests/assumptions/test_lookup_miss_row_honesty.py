# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A lookup refusal says what the lookup knows, and a row number is not it.

The lookup runs as an elementwise Polars expression plugin, and the engine
hands such a plugin one batch of rows per call with no row offset attached.
So a position counted inside the plugin is a position in the batch. Under the
default streaming engine that is not the row of the frame -- a lone miss at
true row 40000 of 50000 used to print "row 2500" -- while under the in-memory
engine the two agree, and the plugin cannot tell which engine it is under.

These tests pin the refusal at the six engine/size combinations that exposed
the difference: the message names the key that missed, states no count -- the
plugin's would be the batch's, and a number beside a miss is read as the
frame's -- and never prints a row number under either engine.
"""

import re

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

# "row 0", "row 2500" -- a number the reader would take for a model point.
# "row(s)", which an earlier wording's count carried, is matched apart.
ROW_NUMBER = re.compile(r"row \d")

COVERED_AGES = [40, 41, 42, 43, 44, 45]
MISSING_AGE = 99


def _table(tag: str) -> Table:
    """One age table covering 40-45, registered under a name of its own."""
    return Table(
        name=f"miss_honesty_{tag}",
        source=pl.DataFrame(
            {"age": COVERED_AGES, "rate": [0.001] * len(COVERED_AGES)},
        ),
        dimensions={"age": "age"},
        value="rate",
    )


def _refusal(table: Table, engine: str, n: int, miss_rows: list[int]) -> str:
    """Run one lookup with known misses and return the message it raised."""
    ages = [42] * n
    for row in miss_rows:
        ages[row] = MISSING_AGE
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": list(range(n)), "attained_age": ages}),
    )
    af.mortality_rate = table.lookup(age=af.attained_age)

    with pytest.raises(pl.exceptions.ComputeError) as caught:
        af.collect(engine=engine)
    return str(caught.value)


@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
@pytest.mark.parametrize(("n", "miss_row"), [(5, 3), (100, 77)])
def test_the_refusal_names_the_key_and_no_row(
    engine: str,
    n: int,
    miss_row: int,
) -> None:
    """The key is what the reader can act on; the row is what it cannot know."""
    message = _refusal(_table(f"key_{engine}_{n}"), engine, n, [miss_row])

    assert f"attained_age={MISSING_AGE}" in message
    assert not ROW_NUMBER.search(message), message


@pytest.mark.parametrize(("n", "miss_row"), [(5, 3), (100, 77)])
def test_the_refusal_reads_the_same_under_both_engines(n: int, miss_row: int) -> None:
    """One honest message for both, because the plugin cannot tell them apart.

    This is the assertion the old wording could not pass: the same frame and
    the same miss produced "row 0" under streaming and "row 3" under
    in-memory, and nothing in the plugin's call could say which was true.
    """
    table = _table(f"same_{n}")
    streaming = _refusal(table, "streaming", n, [miss_row])
    in_memory = _refusal(table, "in-memory", n, [miss_row])

    assert streaming == in_memory


@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
def test_no_count_is_stated(engine: str) -> None:
    """The plugin's count would be the batch's; the message states none."""
    message = _refusal(_table(f"count_{engine}"), engine, 100, [12])

    assert "row(s)" not in message
    assert "neither how many of the frame's rows missed" in message


@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
def test_the_refusal_holds_at_the_scale_that_split_the_batches(engine: str) -> None:
    """50,000 rows is where streaming splits, and where "row 2500" was printed."""
    message = _refusal(_table(f"scale_{engine}"), engine, 50_000, [40_000])

    assert f"attained_age={MISSING_AGE}" in message
    assert not ROW_NUMBER.search(message), message


@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
def test_a_split_frame_never_claims_a_frame_wide_total(engine: str) -> None:
    """Three misses spread across a split frame: streaming sees one batch's worth.

    Streaming counted 1 where in-memory counted 3, because the batch that
    refused held one of the three. Neither number was wrong about the batch,
    but a count beside a miss is read as the frame's, so none is printed.
    """
    message = _refusal(_table(f"total_{engine}"), engine, 50_000, [100, 25_000, 49_000])

    assert "row(s)" not in message
    assert not ROW_NUMBER.search(message), message
