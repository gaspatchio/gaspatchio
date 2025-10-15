from __future__ import annotations

from gaspatchio_core import ActuarialFrame


def test_irr_basic_vector():
    af = ActuarialFrame(
        {
            "values": [[-100.0, 39.0, 59.0, 55.0, 20.0]],
        }
    )
    out = af.with_columns(af["values"].excel.irr().alias("irr"))
    res = out.collect()["irr"][0]
    assert abs(res - 0.28095) < 1e-3


def test_irr_with_guess_column():
    af = ActuarialFrame(
        {
            "values": [[-70000.0, 22000.0, 25000.0, 28000.0, 31000.0]],
            "guess": [0.1],
        }
    )
    out = af.with_columns(
        af["values"].excel.irr(guess=af["guess"], default_guess=0.05).alias("irr")
    )
    res = out.collect()["irr"][0]
    assert 0.15 < res < 0.30
