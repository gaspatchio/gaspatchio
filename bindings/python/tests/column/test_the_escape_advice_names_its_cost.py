# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every refusal that advises ``.polars_native()`` says what the escape costs.

The escape runs, and on Polars its answer is right. What it does not say on
its own is that the record now marks the line, and every calculation reading
it, as one engine's own: only ``validate --engine`` showed that, after the
model was built. So each message that advises the escape names the cost and
where to see it, and where the vocabulary declares the calculation under
another spelling -- ``is_between`` is two comparisons -- that spelling comes
first. The cost is measured too: the line advised is engine_native, and a
declared line reading it is not portable either.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_COST = (
    "A line written through .polars_native() records as engine_native: it "
    "runs only on Polars, and so does every calculation that reads it -- "
    "af.graph.tiers() (or gspio graph tiers) names the line, and gspio "
    "validate --engine jax names it and every calculation that reads it."
)


def _timeline() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame({"policy_id": ["A"], "d": [dt.date(2020, 3, 1)], "s": ["x"]})
    )
    af = af.projection.set(
        start_date=dt.date(2025, 1, 31), n_periods=3, frequency="annual"
    )
    af.q = 0.01 + af.month * 0.0001
    return af


@pytest.mark.parametrize(
    "write",
    [
        lambda af: af.q.list.head(2),
        lambda af: af.s.str.to_uppercase(),
        lambda af: af.d.dt.year(),
        lambda af: af.q.is_between(0.0, 1.0),
        lambda af: af.q.round(1.5),
    ],
    ids=["list-namespace", "str-namespace", "undeclared-name", "is_between", "form"],
)
def test_a_refusal_advising_the_escape_names_its_cost(write: object) -> None:
    af = _timeline()
    with pytest.raises((AttributeError, TypeError)) as refused:
        write(af)  # type: ignore[operator]
    message = str(refused.value)
    assert ".polars_native()" in message
    assert _COST in message


def test_is_between_names_the_declared_comparisons_before_the_escape() -> None:
    af = ActuarialFrame(pl.DataFrame({"x": [0.5, 0.75, 1.0, 1.25, 1.5]}))
    with pytest.raises(AttributeError) as refused:
        af.x.is_between(0.75, 1.25)
    message = str(refused.value)
    declared = "(af.<column> >= lower) & (af.<column> <= upper)"
    assert declared in message
    assert message.index(declared) < message.index(".polars_native().is_between")


def test_the_declared_spelling_agrees_with_is_between_and_records_as_core() -> None:
    af = ActuarialFrame(pl.DataFrame({"x": [0.5, 0.75, 1.0, 1.25, 1.5]}))
    af.in_band = (af.x >= 0.75) & (af.x <= 1.25)
    af.in_band_escape = af.x.polars_native().is_between(0.75, 1.25)
    out = af.collect()
    assert out["in_band"].to_list() == out["in_band_escape"].to_list()
    census = af.graph.tiers()
    assert census.core == ("in_band@1",)
    assert census.engine_native == ("in_band_escape@1",)


def test_tiers_names_the_escaped_line_as_the_message_says() -> None:
    """The census names the line itself; a declared line reading it stays core.

    That is why the message sends the reader to ``validate --engine`` for
    the calculations downstream: the census tiers each line by how it is
    written, and only the portability check follows the reads.
    """
    af = ActuarialFrame(pl.DataFrame({"x": [1.0, 2.0]}))
    af.escaped = af.x.polars_native().cum_max()
    af.reads_it = af.escaped * 2.0
    census = af.graph.tiers()
    assert census.engine_native == ("escaped@1",)
    assert census.core == ("reads_it@1",)


def test_a_reserved_name_is_not_routed_to_the_escape() -> None:
    af = ActuarialFrame(pl.DataFrame({"x": [0.5]}))
    with pytest.raises(AttributeError) as refused:
        af.x.norm_inv()
    assert _COST not in str(refused.value)
