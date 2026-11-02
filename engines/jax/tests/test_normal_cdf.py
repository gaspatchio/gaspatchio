# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The standard normal distribution function on this engine, and beside Polars.

Section 11.1.12 states ``norm_cdf`` with the transcendental family: Φ held to
1e-12 relative to the mathematical value wherever Φ is a normal double, and
exact at a NaN and the two infinities. This engine lowers it to XLA's
``ndtr``, the complementary form that keeps the lower tail's digits; Polars
runs a native ``0.5 * erfc(-x / sqrt 2)``. The two are different functions of
one double and part company in the last place, so a GMDB put written with
them is held to the section's agreement rule rather than to the bit.
"""

from __future__ import annotations

import math
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from tests.test_lowerings_projection import _call, _column, answered

# Φ at exact doubles: the double nearest the value worked to 60 digits by
# spec/graph-artifact/conformance/make_normal_cdf_vectors.py.
_PHI: dict[float, float] = {
    -37.5: 4.605353009581955e-308,
    -30.0: 4.906713927148187e-198,
    -8.36: 3.1359128294842655e-17,
    -3.0: 0.0013498980316300946,
    -1.96: 0.024997895148220435,
    0.0: 0.5,
    1.96: 0.9750021048517795,
    6.0: 0.9999999990134123,
}

# Section 11.1.12: the family's relative tolerance, and the agreement rule's
# 1e-12 of the line's scale.
_CONTRACT = 1e-12
_AGREEMENT = 1e-12

_PHI_OF_X = _call("norm_cdf", [_column("x")])


def test_phi_on_this_engine_is_within_the_contract_the_lower_tail_included() -> None:
    points = sorted(_PHI)
    got = answered(_PHI_OF_X, {"x": {"dtype": "f64", "values": points}}, "f64")
    for point, value in zip(points, got, strict=True):
        assert value == pytest.approx(_PHI[point], rel=_CONTRACT, abs=0.0), point


def test_the_special_values_are_exact_on_this_engine() -> None:
    got = answered(
        _PHI_OF_X,
        {
            "x": {
                "dtype": "f64",
                "values": [
                    {"nonfinite": "nan"},
                    {"nonfinite": "+inf"},
                    {"nonfinite": "-inf"},
                    0.0,
                ],
            }
        },
        "f64",
    )
    assert math.isnan(got[0])
    assert got[1:] == [1.0, 0.0, 0.5]


def test_each_policy_s_own_periods_are_answered_in_a_padded_bucket() -> None:
    """A ragged book: the padding a short policy stands in reaches no answer."""
    got = answered(
        _PHI_OF_X,
        {"x": {"dtype": "list[f64]", "values": [[-1.96, 0.0, 1.96], [6.0], []]}},
        "list[f64]",
    )
    assert [len(row) for row in got] == [3, 1, 0]
    assert got[0] == pytest.approx(
        [_PHI[-1.96], 0.5, _PHI[1.96]], rel=_CONTRACT, abs=0.0
    )
    assert got[1] == pytest.approx([_PHI[6.0]], rel=_CONTRACT, abs=0.0)


def _a_gmdb_put() -> ActuarialFrame:
    """Return a GMDB valued as a Black-Scholes put at each projection period."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2, 3],
                "fund": [100_000.0, 80_000.0, 120_000.0],
                "guarantee": [100_000.0, 100_000.0, 100_000.0],
                "rate": [0.03, 0.03, 0.025],
                "vol": [0.18, 0.2, 0.15],
                "remaining": [[10.0, 9.0, 8.0], [5.0, 4.0], [8.0, 7.0, 6.0, 5.0]],
            }
        )
    )
    frame.sd = frame.vol * frame.remaining.sqrt()
    frame.d1 = (
        (frame.fund / frame.guarantee).log()
        + (frame.rate + frame.vol**2 / 2) * frame.remaining
    ) / frame.sd
    frame.d2 = frame.d1 - frame.sd
    frame.n_minus_d2 = (-frame.d2).norm_cdf()
    frame.n_minus_d1 = (-frame.d1).excel.norm_s_dist()
    frame.put = (
        frame.guarantee * (-frame.rate * frame.remaining).exp() * frame.n_minus_d2
        - frame.fund * frame.n_minus_d1
    )
    return frame


def test_a_gmdb_put_reads_as_portable_to_this_engine() -> None:
    document = GraphExporter(_a_gmdb_put()).export(profile="executable")
    report = validate_artifact(document, engine="jax", deep=True)
    assert report.ok, report.findings


@pytest.mark.parametrize("column", ["n_minus_d2", "n_minus_d1", "put"])
def test_a_gmdb_put_agrees_with_polars_under_the_agreement_rule(column: str) -> None:
    """Each line within 1e-12 of its scale, per policy, over what it reads."""
    on_polars = _a_gmdb_put().collect()
    on_jax = _a_gmdb_put().collect(engine="jax")
    reads: dict[str, tuple[str, ...]] = {
        "n_minus_d2": ("d2",),
        "n_minus_d1": ("d1",),
        "put": ("n_minus_d2", "n_minus_d1", "guarantee", "fund"),
    }
    for policy in range(on_polars.height):
        mine: list[Any] = on_jax[column][policy].to_list()
        theirs: list[Any] = on_polars[column][policy].to_list()
        read_values: list[float] = []
        for name in reads[column]:
            cell = on_polars[name][policy]
            read_values.extend(
                cell.to_list() if isinstance(cell, pl.Series) else [cell]
            )
        scale = max(abs(x) for x in [*theirs, *read_values])
        assert len(mine) == len(theirs)
        assert all(
            abs(a - b) <= _AGREEMENT * scale for a, b in zip(mine, theirs, strict=True)
        ), (column, policy)
