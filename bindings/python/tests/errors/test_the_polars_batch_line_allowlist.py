# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars' one batch-counted line is read by template; the allowlist stays closed.

Polars' own list arithmetic refuses a policy whose lists differ in length with
``list lengths differed at index N: A != B``, and N is counted within the batch
the engine was computing: under the default streaming engine a misfit on frame
row 1 reads ``index 0``, and the in-memory replay of the same plan reads
``index 1``. The replay's candidate matcher compared first lines byte for
byte, so the two never met and the streaming error arrived with no block at
all.

The line is now on a closed allowlist of Polars' batch-counted lines, matched
by a full-line template with every digit read as the batch's. Pinned here:
the allowlist has exactly one entry; Polars still writes the line in that
form, so an upgrade that rewords it fails a named test; gaspatchio's own lines
never fit it; the raw-Polars escape is reached as
the frame's operators are; and the cost the template accepts -- with two
genuine breaks, the block can name the one in the replay's head while the
message's digits describe the other.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.errors.boundary import (
    _POLARS_BATCH_LINES,
    POLARS_LIST_LENGTH_LINE,
    _polars_batch_line,
    search_collect_failure,
)

_ENGINES = ("streaming", "in-memory")


@pytest.fixture(autouse=True)
def _enhanced_error_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the ambient error mode -- earlier suites leak ``AF_ERROR_MODE``."""
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")


def test_the_polars_allowlist_is_closed() -> None:
    """Exactly one entry: Polars' list-length line, under the class that raises it.

    A new entry needs a measured repro and a pin of Polars' wording; this
    test failing is where that conversation starts. Polars' strict-cast line
    is deliberately absent: its sampled values vary by batch.
    """
    assert len(_POLARS_BATCH_LINES) == 1
    ((raised_as, template),) = _POLARS_BATCH_LINES
    assert raised_as is pl.exceptions.ShapeError
    assert template is POLARS_LIST_LENGTH_LINE
    assert template.pattern == r"list lengths differed at index \d+: \d+ != \d+"


def test_no_line_of_ours_fits_the_allowlist() -> None:
    """Gaspatchio's lines keep the exact check: none fits a Polars template.

    Every kernel line opens ``the plugin failed with message:`` and the
    template is matched whole, so even a line that quotes Polars' words is
    not admitted; nor is Polars' line under another class, or with anything
    after it on the first line.
    """
    ours = (
        (
            "the plugin failed with message: mismatched inner list lengths in "
            "one policy: right against left"
        ),
        "the plugin failed with message: list lengths differed at index 0: 3 != 2",
        "the plugin failed with message: Lookup on table 'mort' found no rate",
    )
    for line in ours:
        assert _polars_batch_line(pl.exceptions.ComputeError(line)) is None
        assert _polars_batch_line(pl.exceptions.ShapeError(line)) is None
    polars_line = "list lengths differed at index 7: 3 != 2"
    assert _polars_batch_line(pl.exceptions.ShapeError(polars_line))
    assert (
        _polars_batch_line(pl.exceptions.ShapeError(f"{polars_line}\nmore")) is not None
    )
    assert _polars_batch_line(pl.exceptions.ComputeError(polars_line)) is None
    assert _polars_batch_line(pl.exceptions.ShapeError(f"{polars_line}.")) is None


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("operator", ["*", "+", "-"])
def test_polars_still_raises_the_allowlisted_list_length_line(
    operator: str, engine: str
) -> None:
    """Polars itself, with no gaspatchio in the way, writes the line the template reads.

    Run against Polars so that an upgrade which rewords the line fails here,
    by name, rather than silently taking the streaming block away again.
    """
    left, right = pl.col("x"), pl.col("short")
    product = {"*": left * right, "+": left + right, "-": left - right}[operator]
    plan = (
        pl.DataFrame(
            {
                "x": [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [1.0, 2.0, 3.0]],
                "short": [[1.0, 2.0, 3.0], [1.0, 2.0], [1.0, 2.0, 3.0]],
            }
        )
        .lazy()
        .select(out=product)
    )
    with pytest.raises(pl.exceptions.ShapeError) as refused:
        plan.collect(engine=engine)  # type: ignore[call-overload]

    first = str(refused.value).split("\n", 1)[0]
    assert POLARS_LIST_LENGTH_LINE.fullmatch(first), first


def _short_book() -> pl.DataFrame:
    """Three policies; P002, on frame row 1, is one period short."""
    return pl.DataFrame(
        {
            "policy_id": ["P001", "P002", "P003"],
            "x": [[1.0, 2.0, 3.0]] * 3,
            "short": [[10.0, 20.0, 30.0], [10.0, 20.0], [10.0, 20.0, 30.0]],
        }
    )


@pytest.mark.parametrize("engine", _ENGINES)
def test_the_raw_polars_escape_is_named_as_the_operators_are(engine: str) -> None:
    """``with_columns((pl.col("x") * pl.col("short")).alias("out"))`` is named too.

    The template reads the line, not the door it came through, so the raw
    Polars escape -- which no gaspatchio kernel of ours could reach -- is
    named in the streaming run as in memory. The locator does not lower a
    raw Polars record, so neither engine adds a ``Policy:`` line here; that
    is unchanged.
    """
    af = ActuarialFrame(_short_book())
    af = af.with_columns((pl.col("x") * pl.col("short")).alias("out"))
    with pytest.raises(pl.exceptions.ShapeError) as refused:
        af.collect(engine=engine)

    message = str(refused.value)
    assert "  Failing column: 'out'" in message, message


_ROWS = 20_000
_IN_HEAD, _PAST_CAP = 3, 15_000


def _two_breaks() -> ActuarialFrame:
    """Two genuine breaks: ``j1`` in the replay's head, ``j2`` past it."""
    full, short = [1.0, 2.0, 3.0], [1.0, 2.0]
    book = pl.DataFrame(
        {
            "policy_id": [f"P{i:05d}" for i in range(_ROWS)],
            "x": [full] * _ROWS,
            "a": [short if i == _IN_HEAD else full for i in range(_ROWS)],
            "b": [short if i == _PAST_CAP else full for i in range(_ROWS)],
        }
    )
    af = ActuarialFrame(book)
    af.j1 = af.x * af.a
    af.j2 = af.x * af.b
    return af


def test_two_breaks_name_the_one_in_the_head_whatever_the_digits_say() -> None:
    """The accepted cost: the block names ``j1`` while the line describes ``j2``.

    Which of two breaks Polars surfaces is not deterministic, even in
    memory; here it is fixed by handing the search ``j2``'s line, index
    15000. The replay's head never reaches row 15000, so ``j2`` reproduces
    nothing there; ``j1`` raises the same template at index 3 and is named,
    with its own policy. On the base this was bare. A genuinely broken
    calculation is named and no healthy one: healing still has to go
    through a structural operation and its exact confirmation. It is the
    standing our own policy-free lines already have, whose exact check
    matches across policies in just this way.
    """
    af = _two_breaks()
    j2s_line = pl.exceptions.ShapeError(
        f"list lengths differed at index {_PAST_CAP}: 3 != 2"
    )

    outcome = search_collect_failure(af, j2s_line)

    assert getattr(outcome.attribution, "column", None) == "j1"


@pytest.mark.parametrize("engine", _ENGINES)
def test_two_breaks_collected_name_the_one_in_the_head(engine: str) -> None:
    """Collected, either surfaced line names ``j1`` and its policy, P00003."""
    with pytest.raises(pl.exceptions.ShapeError) as refused:
        _two_breaks().collect(engine=engine)

    message = str(refused.value)
    assert "  Failing column: 'j1'" in message, message
    assert "  Policy:         policy_id=P00003 (row 3)" in message, message
