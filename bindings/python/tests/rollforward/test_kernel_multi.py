"""End-to-end tests for multi-state rollforward via RollforwardStateProxy."""

from __future__ import annotations

import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward._builder import RollforwardBuilder, RollforwardStateProxy


class TestRollforwardStateProxy:
    """Test RollforwardStateProxy creation and error handling."""

    def test_getitem_returns_proxy(self) -> None:
        """Indexing a multi-state builder returns a RollforwardStateProxy."""
        af = ActuarialFrame({"a": [1.0], "b": [2.0]})
        rf = af.projection.rollforward(av=af.a, guarantee=af.b)
        proxy = rf["av"]
        assert isinstance(proxy, RollforwardStateProxy)
        assert proxy._state_name == "av"

    def test_getitem_single_state_raises(self) -> None:
        """Indexing a single-state builder raises TypeError."""
        af = ActuarialFrame({"a": [1.0]})
        rf = af.projection.rollforward(initial=af.a)
        with pytest.raises(TypeError, match="single-state|multi-state"):
            rf["av"]

    def test_getitem_unknown_state_raises(self) -> None:
        """Indexing with unknown state name raises KeyError."""
        af = ActuarialFrame({"a": [1.0], "b": [2.0]})
        rf = af.projection.rollforward(av=af.a, guarantee=af.b)
        with pytest.raises(KeyError, match="unknown_state"):
            rf["unknown_state"]

    def test_proxy_repr(self) -> None:
        """RollforwardStateProxy has a sensible repr."""
        af = ActuarialFrame({"a": [1.0], "b": [2.0]})
        rf = af.projection.rollforward(av=af.a, guarantee=af.b)
        proxy = rf["av"]
        assert "av" in repr(proxy)


class TestMultiStateVaGmdb:
    """VA/GMDB multi-state rollforward test."""

    def test_multi_state_va_gmdb(self) -> None:
        """Two-state rollforward: AV with premiums and guarantee with ratchet."""
        af = ActuarialFrame({
            "av_init": [1000.0],
            "g_init": [1000.0],
            "premium": [[100.0, 100.0]],
            "fund_return": [[0.10, -0.05]],
            "roll_up_rate": [[0.03, 0.03]],
        })
        rf = (
            af.projection.rollforward(av=af.av_init, guarantee=af.g_init)
            .on("av")
            .add(af.premium, "Premium")
            .grow(af.fund_return, "Fund Return")
            .floor(0)
            .on("guarantee")
            .ratchet_to("av", "GMDB Ratchet")
            .grow(af.roll_up_rate, "Roll-up")
            .lapse_when(all_non_positive=["av", "guarantee"])
        )
        af.av = rf["av"]
        af.guarantee = rf["guarantee"]
        result = af.collect()

        av = result["av"].to_list()[0]
        g = result["guarantee"].to_list()[0]

        # t=0: av = (1000+100)*1.10 = 1210.0
        # t=0: guarantee = max(1000, 1210)*1.03 = 1246.3
        assert abs(av[0] - 1210.0) < 1e-10
        assert abs(g[0] - 1246.3) < 1e-10

        # t=1: av = (1210+100)*0.95 = 1244.5
        # t=1: guarantee = max(1246.3, 1244.5)*1.03 = 1283.689
        assert abs(av[1] - 1244.5) < 1e-10
        assert abs(g[1] - 1283.689) < 1e-10


class TestMultiStateProRata:
    """Pro-rata multi-state rollforward test."""

    def test_multi_state_pro_rata(self) -> None:
        """Benefit base reduced pro-rata with AV withdrawal."""
        af = ActuarialFrame({
            "av_init": [1000.0],
            "bb_init": [500.0],
            "withdrawal": [[200.0]],
            "fund_return": [[0.05]],
        })
        rf = (
            af.projection.rollforward(av=af.av_init, benefit_base=af.bb_init)
            .on("av")
            .capture("av_pre_wd")
            .subtract(af.withdrawal, "Withdrawal")
            .on("benefit_base")
            .pro_rata_with("av_pre_wd", af.withdrawal, "ProRata")
            .on("av")
            .grow(af.fund_return, "Fund Return")
        )
        af.av = rf["av"]
        af.bb = rf["benefit_base"]
        result = af.collect()

        # av: capture(1000), subtract(200)=800, grow(0.05)=840
        # bb: pro_rata = 500 * (1 - 200/1000) = 400
        assert abs(result["av"].to_list()[0][0] - 840.0) < 1e-10
        assert abs(result["bb"].to_list()[0][0] - 400.0) < 1e-10


class TestMultiStateHiddenColumns:
    """Hidden columns from multi-state rollforwards are stripped on collect."""

    def test_hidden_columns_stripped(self) -> None:
        """No __rollforward_ columns in collected output."""
        af = ActuarialFrame({
            "av_init": [1000.0],
            "g_init": [1000.0],
            "premium": [[100.0]],
            "fund_return": [[0.10]],
            "roll_up_rate": [[0.03]],
        })
        rf = (
            af.projection.rollforward(av=af.av_init, guarantee=af.g_init)
            .on("av")
            .add(af.premium, "Premium")
            .grow(af.fund_return, "Fund Return")
            .on("guarantee")
            .ratchet_to("av", "Ratchet")
            .grow(af.roll_up_rate, "Roll-up")
        )
        af.av = rf["av"]
        af.guarantee = rf["guarantee"]
        result = af.collect()

        for col in result.columns:
            assert not col.startswith("__rollforward_")


class TestMultiStateMultiRow:
    """Multi-state rollforward across multiple rows."""

    def test_multi_row(self) -> None:
        """Multi-state works with more than one policy row."""
        af = ActuarialFrame({
            "av_init": [1000.0, 2000.0],
            "g_init": [1000.0, 1500.0],
            "premium": [[100.0], [200.0]],
            "fund_return": [[0.10], [0.05]],
            "roll_up_rate": [[0.03], [0.02]],
        })
        rf = (
            af.projection.rollforward(av=af.av_init, guarantee=af.g_init)
            .on("av")
            .add(af.premium, "Premium")
            .grow(af.fund_return, "Fund Return")
            .on("guarantee")
            .ratchet_to("av", "Ratchet")
            .grow(af.roll_up_rate, "Roll-up")
        )
        af.av = rf["av"]
        af.guarantee = rf["guarantee"]
        result = af.collect()

        av = result["av"].to_list()
        g = result["guarantee"].to_list()

        # Row 0: av = (1000+100)*1.10 = 1210.0
        assert abs(av[0][0] - 1210.0) < 1e-10
        # Row 0: guarantee = max(1000, 1210)*1.03 = 1246.3
        assert abs(g[0][0] - 1246.3) < 1e-10

        # Row 1: av = (2000+200)*1.05 = 2310.0
        assert abs(av[1][0] - 2310.0) < 1e-10
        # Row 1: guarantee = max(1500, 2310)*1.02 = 2356.2
        assert abs(g[1][0] - 2356.2) < 1e-10
