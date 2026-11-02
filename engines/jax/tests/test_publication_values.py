# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Publication preserves typed cells without Python work for every policy."""

from __future__ import annotations

import cProfile
from typing import TYPE_CHECKING

import jax
import jax.numpy as jnp
import numpy as np
import polars as pl
import pytest
from polars.testing import assert_series_equal

from gaspatchio_jax.horizon import Horizon
from gaspatchio_jax.interning import Dictionary
from gaspatchio_jax.plan import _as_series
from gaspatchio_jax.typed import JNP_OF, Value

if TYPE_CHECKING:
    from gaspatchio_jax.typed import Carrier


def _lists(cells: jax.Array, lengths: list[int], carrier: Carrier) -> Value:
    """Put known cells on their own axis, including empty policy timelines."""
    counts = np.asarray(lengths, dtype=np.int64)
    horizon = Horizon.over(jnp.asarray(counts), bucket=cells.shape[1], host=counts)
    return Value(cells, carrier, "list", f"list[{carrier}]", horizon)


@pytest.mark.parametrize("carrier", ["f64", "i64", "bool"])
def test_numeric_publication_does_not_scale_python_calls_with_policies(
    carrier: Carrier,
) -> None:
    """A hundred times the rows must not mean a hundred times Python dispatch.

    Counting calls avoids a wall-clock threshold that depends on the machine.
    Reintroducing nested Python sequences makes this fail, whether those
    sequences hold Python scalars or NumPy scalars. Array creation, device
    work and first-use library setup are outside the measurement.
    """
    calls = []
    for policies in (10, 1_000):
        value = _lists(
            jnp.ones((policies, 8), dtype=JNP_OF[carrier]), [7] * policies, carrier
        )
        value.array.block_until_ready()
        dictionary = Dictionary()
        _as_series("value", value, dictionary)
        with cProfile.Profile() as profile:
            actual = _as_series("value", value, dictionary)
        assert actual.len() == policies
        assert actual.list.len().unique().to_list() == [7]
        calls.append(sum(entry.callcount for entry in profile.getstats()))
    assert calls[1] < 5 * calls[0], calls


@pytest.mark.parametrize(
    ("carrier", "dtype", "cells"),
    [
        ("f64", pl.Float64, [-0.0, 1.25, -4.5, 8.0]),
        ("i64", pl.Int64, [-(2**63), 2**53 + 1, 2**63 - 1, 0]),
        ("bool", pl.Boolean, [True, False, True, False]),
    ],
)
def test_numeric_publication_preserves_carriers_and_each_policy_s_length(
    carrier: Carrier,
    dtype: pl.DataType,
    cells: list,
) -> None:
    """No float round-trip for integers, and no padding in the published lists."""
    scalar = Value(
        jnp.asarray(cells, dtype=JNP_OF[carrier]), carrier, "scalar", carrier
    )
    listed = _lists(jnp.tile(scalar.array, (4, 1)), [0, 1, 3, 4], carrier)
    assert_series_equal(
        _as_series("scalar", scalar, Dictionary()),
        pl.Series("scalar", cells, dtype=dtype),
        check_exact=True,
    )
    actual = _as_series("listed", listed, Dictionary())
    assert_series_equal(
        actual,
        pl.Series("listed", [[], cells[:1], cells[:3], cells], dtype=pl.List(dtype)),
        check_exact=True,
    )
    if carrier == "f64":
        assert np.signbit(actual[1].to_numpy()[0])


@pytest.mark.parametrize("carrier", ["f64", "i64", "bool"])
def test_an_empty_numeric_book_keeps_its_list_schema(carrier: Carrier) -> None:
    """A zero-row array must not turn into an untyped or one-row column."""
    value = _lists(jnp.empty((0, 4), dtype=JNP_OF[carrier]), [], carrier)
    dtype = {"f64": pl.Float64, "i64": pl.Int64, "bool": pl.Boolean}[carrier]
    assert_series_equal(
        _as_series("empty", value, Dictionary()),
        pl.Series("empty", [], dtype=pl.List(dtype)),
        check_exact=True,
    )


def test_publication_uses_each_values_axis_for_boundary_sequences() -> None:
    """Two columns in one rectangle can owe the reader different lengths."""
    cells = jnp.asarray([[10, 20, 30, 40], [50, 60, 70, 80]], dtype=jnp.int64)
    periods = _lists(cells, [0, 2], "i64")
    boundaries = _lists(cells, [1, 3], "i64")
    assert _as_series("periods", periods, Dictionary()).to_list() == [[], [50, 60]]
    assert _as_series("boundaries", boundaries, Dictionary()).to_list() == [
        [10],
        [50, 60, 70],
    ]


def test_publication_does_not_send_host_values_back_to_a_device() -> None:
    """Output conversion must not insert device work after computation ends.

    This runs on the available JAX device; CPU success is not a GPU gate.
    Host-to-device and device-to-device transfers are unnecessary here.
    """
    value = _lists(jnp.asarray([[1.0, 2.0], [3.0, 4.0]]), [1, 2], "f64")
    value.array.block_until_ready()
    with (
        jax.transfer_guard_host_to_device("disallow_explicit"),
        jax.transfer_guard_device_to_device("disallow_explicit"),
    ):
        actual = _as_series("value", value, Dictionary())
    assert actual.to_list() == [[1.0], [3.0, 4.0]]
