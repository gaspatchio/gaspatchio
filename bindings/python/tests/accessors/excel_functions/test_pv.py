# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.accessors.excel_functions.pv import pv as pv_expr


def test_pv_scalar_inputs():
    af = ActuarialFrame(
        {
            "rate": [0.05],
            "nper": [10.0],
            "pmt": [100.0],
        }
    )
    out = af.with_columns(
        af["rate"].excel.pv(af["nper"], af["pmt"], fv=0.0, typ=0).alias("pv")
    )
    res = out.collect()["pv"][0]
    assert isinstance(res, float)


def test_pv_list_inputs_pairwise():
    af = ActuarialFrame(
        {
            "rate": [[0.05, 0.06, 0.07]],
            "nper": [[10.0, 10.0, 10.0]],
            "pmt": [[100.0, 100.0, 100.0]],
        }
    )
    out = af.with_columns(
        af["rate"].excel.pv(af["nper"], af["pmt"], fv=0.0, typ=0).alias("pv")
    )
    s = out.collect()["pv"]
    assert s.dtype == pl.List(pl.Float64) or s.dtype == pl.Float64
    # Either list-of-floats or flattened Float64 depending on plugin behavior
    if s.dtype == pl.List(pl.Float64):
        inner = s[0]
        if isinstance(inner, pl.Series):
            vals = inner.to_list()
        else:
            vals = inner
        assert isinstance(vals, list)
        assert len(vals) == 3


def _hand_pv(r: float, n: float, p: float, fv: float = 0.0, typ: int = 0) -> float:
    """Excel PV, recomputed independently for assertions."""
    if abs(r) < 1e-12:
        return -(p * n + fv)
    typf = 1.0 if typ else 0.0
    pow_ = (1.0 + r) ** (-n)
    ann = (1.0 + r * typf) * (1.0 - pow_) / r
    return -(p * ann + fv * pow_)


def test_pv_list_rate_uses_per_policy_scalars() -> None:
    """F2: with a list rate column, per-policy nper/pmt must be used per row.

    Regression for the row-0 broadcast bug: every policy was computed with
    policy-0's nper/pmt. Uses the in-memory engine because the streaming
    engine masks the bug (one row per morsel makes ``get(0)`` coincide).
    """
    df = pl.DataFrame(
        {
            "rate": [[0.05], [0.05], [0.05]],
            "nper": [10.0, 20.0, 5.0],
            "pmt": [1000.0, 2000.0, 500.0],
        }
    )
    expr = pv_expr(pl.col("rate"), pl.col("nper"), pl.col("pmt")).alias("pv")
    out = df.lazy().with_columns(expr).collect(engine="in-memory")
    got = [row[0] for row in out["pv"].to_list()]
    assert got[0] == pytest.approx(_hand_pv(0.05, 10.0, 1000.0))
    assert got[1] == pytest.approx(_hand_pv(0.05, 20.0, 2000.0))
    assert got[2] == pytest.approx(_hand_pv(0.05, 5.0, 500.0))


def test_pv_scalar_unit_length_literal_broadcasts() -> None:
    """F2: a length-1 literal rate must broadcast to all rows, not truncate."""
    df = pl.DataFrame({"nper": [10.0, 20.0], "pmt": [1000.0, 2000.0]})
    expr = pv_expr(pl.lit(0.05), pl.col("nper"), pl.col("pmt")).alias("pv")
    out = df.lazy().with_columns(expr).collect(engine="in-memory")
    assert out.height == 2
    got = out["pv"].to_list()
    assert got[0] == pytest.approx(_hand_pv(0.05, 10.0, 1000.0))
    assert got[1] == pytest.approx(_hand_pv(0.05, 20.0, 2000.0))
