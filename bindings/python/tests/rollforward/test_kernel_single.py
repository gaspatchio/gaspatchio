"""End-to-end tests: builder -> compile -> Rust kernel -> result."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


def test_single_state_add_e2e() -> None:
    """Single add step through full pipeline."""
    af = ActuarialFrame({
        "av_init": [1000.0, 2000.0],
        "premium": [[100.0, 100.0, 100.0], [200.0, 200.0, 200.0]],
    })
    af.av = (
        af.projection.rollforward(initial=af.av_init)
        .add(af.premium, "Premium")
    )
    result = af.collect()

    av = result["av"].to_list()
    assert len(av) == 2
    assert abs(av[0][0] - 1100.0) < 1e-10
    assert abs(av[0][2] - 1300.0) < 1e-10
    assert abs(av[1][0] - 2200.0) < 1e-10

    # Hidden columns should be stripped
    assert "__rollforward_av" not in result.columns


def test_single_state_ul_rollforward() -> None:
    """UL rollforward: add, deduct_nar, charge, grow, floor."""
    af = ActuarialFrame({
        "av_init": [1000.0],
        "premium": [[100.0]],
        "coi_rate": [[0.001]],
        "sum_assured": [[5000.0]],
        "admin_rate": [[0.01]],
        "interest_rate": [[0.05]],
    })
    af.av = (
        af.projection.rollforward(initial=af.av_init)
        .add(af.premium, "Premium")
        .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
        .charge(af.admin_rate, "Admin")
        .grow(af.interest_rate, "Interest")
        .floor(0)
    )
    result = af.collect()
    av = result["av"].to_list()[0]

    # Manual: 1000+100=1100, COI: 1100-0.001*max(0,5000-1100)=1100-3.9=1096.1
    # Admin: 1096.1*0.99=1085.139, Interest: 1085.139*1.05=1139.39595
    assert abs(av[0] - 1139.39595) < 0.01


def test_hidden_columns_stripped_in_collect() -> None:
    """Verify __rollforward_ columns don't appear in output."""
    af = ActuarialFrame({
        "av_init": [1000.0],
        "premium": [[100.0]],
    })
    af.av = af.projection.rollforward(initial=af.av_init).add(af.premium, "P")
    result = af.collect()

    for col in result.columns:
        assert not col.startswith("__rollforward_")


def test_multiple_rollforwards_on_same_frame() -> None:
    """Two different rollforwards assigned to different columns."""
    af = ActuarialFrame({
        "av_init": [1000.0],
        "premium": [[100.0]],
        "interest_rate": [[0.05]],
    })
    af.av_no_interest = (
        af.projection.rollforward(initial=af.av_init)
        .add(af.premium, "Premium")
    )
    af.av_with_interest = (
        af.projection.rollforward(initial=af.av_init)
        .add(af.premium, "Premium")
        .grow(af.interest_rate, "Interest")
    )
    result = af.collect()

    assert abs(result["av_no_interest"].to_list()[0][0] - 1100.0) < 1e-10
    # 1100 * 1.05 = 1155
    assert abs(result["av_with_interest"].to_list()[0][0] - 1155.0) < 1e-10
