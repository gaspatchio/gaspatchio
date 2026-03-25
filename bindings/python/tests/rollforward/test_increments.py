"""Tests for increment and capture access via ColumnProxy."""

from __future__ import annotations

from gaspatchio_core import ActuarialFrame


def test_increment_access() -> None:
    """Increment fields can be extracted via af.av.increments[label]."""
    af = ActuarialFrame({
        "av_init": [1000.0],
        "premium": [[100.0]],
        "admin_rate": [[0.01]],
        "interest_rate": [[0.05]],
    })
    af.av = (
        af.projection.rollforward(initial=af.av_init, track_increments=True)
        .add(af.premium, "Premium")
        .charge(af.admin_rate, "Admin")
        .grow(af.interest_rate, "Interest")
    )

    af.premium_inc = af.av.increments["Premium"]
    af.admin_inc = af.av.increments["Admin"]
    af.interest_inc = af.av.increments["Interest"]

    result = af.collect()

    # Premium increment = 100
    assert abs(result["premium_inc"].to_list()[0][0] - 100.0) < 1e-10
    # Admin increment should be negative (charge reduces AV)
    assert result["admin_inc"].to_list()[0][0] < 0
    # Interest increment should be positive (grow increases AV)
    assert result["interest_inc"].to_list()[0][0] > 0


def test_increments_sum_to_total_change() -> None:
    """Sum of all increments equals total AV change from initial."""
    af = ActuarialFrame({
        "av_init": [1000.0],
        "premium": [[100.0]],
        "admin_rate": [[0.01]],
        "interest_rate": [[0.05]],
    })
    af.av = (
        af.projection.rollforward(initial=af.av_init, track_increments=True)
        .add(af.premium, "Premium")
        .charge(af.admin_rate, "Admin")
        .grow(af.interest_rate, "Interest")
    )
    af.prem_inc = af.av.increments["Premium"]
    af.admin_inc = af.av.increments["Admin"]
    af.int_inc = af.av.increments["Interest"]

    result = af.collect()
    av_final = result["av"].to_list()[0][0]
    total_change = av_final - 1000.0
    increment_sum = (
        result["prem_inc"].to_list()[0][0]
        + result["admin_inc"].to_list()[0][0]
        + result["int_inc"].to_list()[0][0]
    )
    assert abs(total_change - increment_sum) < 1e-10


def test_increments_multi_timestep() -> None:
    """Increments are tracked per timestep."""
    af = ActuarialFrame({
        "av_init": [1000.0],
        "premium": [[100.0, 100.0]],
        "interest_rate": [[0.05, 0.05]],
    })
    af.av = (
        af.projection.rollforward(initial=af.av_init, track_increments=True)
        .add(af.premium, "Premium")
        .grow(af.interest_rate, "Interest")
    )
    af.prem_inc = af.av.increments["Premium"]

    result = af.collect()
    prem_incs = result["prem_inc"].to_list()[0]

    # Both timesteps should have premium increment of 100
    assert abs(prem_incs[0] - 100.0) < 1e-10
    assert abs(prem_incs[1] - 100.0) < 1e-10


def test_increments_multi_row() -> None:
    """Increments work correctly across multiple rows."""
    af = ActuarialFrame({
        "av_init": [1000.0, 2000.0],
        "premium": [[100.0], [200.0]],
        "interest_rate": [[0.05], [0.10]],
    })
    af.av = (
        af.projection.rollforward(initial=af.av_init, track_increments=True)
        .add(af.premium, "Premium")
        .grow(af.interest_rate, "Interest")
    )
    af.prem_inc = af.av.increments["Premium"]

    result = af.collect()
    prem_incs = result["prem_inc"].to_list()

    # Row 0: premium = 100, Row 1: premium = 200
    assert abs(prem_incs[0][0] - 100.0) < 1e-10
    assert abs(prem_incs[1][0] - 200.0) < 1e-10
