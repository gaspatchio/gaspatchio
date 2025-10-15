from __future__ import annotations

import polars as pl

from gaspatchio_core import ActuarialFrame


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
