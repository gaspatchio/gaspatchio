# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""GSP-110: list-broadcast ``when()`` supports string outputs.

The list-broadcast path was f64-only on the value side: string branches died
in the kernel's Float64 cast with a misleading ``then_val at row 0 is null``,
forcing model authors into raw ``pl.col(...).list.eval(...)`` or numeric-code
workarounds. The kernel now carries a Utf8 path (same comparison semantics,
string-valued selection, ``List(String)`` output), and
``broadcast_to_periods()`` covers the companion gap — broadcasting non-numeric
per-policy scalars to the projection axis, where the ``scalar + list * 0.0``
idiom has no string equivalent.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when


def _projected_codes() -> ActuarialFrame:
    """Two policies with per-period numeric codes on a real projection axis."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "code": [0.0, 1.0]}))
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=3,
        frequency="monthly",
    )
    af.code_list = af.code + af.month * 0.0
    return af


class TestStringOutputs:
    def test_ticket_repro_code_to_version_label(self) -> None:
        """The GSP-110 repro verbatim: numeric code list -> string labels."""
        af = _projected_codes()
        af.version = when(af.code_list == 0).then("PP23").otherwise("PP24")
        result = af.collect()

        assert result["version"].dtype == pl.List(pl.String)
        versions = result["version"].to_list()
        assert versions[0] == ["PP23"] * 4
        assert versions[1] == ["PP24"] * 4

    def test_element_wise_selection(self) -> None:
        """Selection is per element, not per row."""
        af = ActuarialFrame({"month": [[0, 1, 2, 3]], "term": [2]})
        af.phase = when(af.month < af.term).then("active").otherwise("expired")
        result = af.collect()

        assert result["phase"].to_list()[0] == [
            "active",
            "active",
            "expired",
            "expired",
        ]

    def test_per_row_string_column_branches(self) -> None:
        """then/otherwise can be per-policy string COLUMNS, not just literals."""
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2], [0, 1, 2]],
                "term": [2, 1],
                "active_label": ["inforce-A", "inforce-B"],
                "expired_label": ["lapsed-A", "lapsed-B"],
            },
        )
        af.status = (
            when(af.month < af.term).then(af.active_label).otherwise(af.expired_label)
        )
        result = af.collect()

        statuses = result["status"].to_list()
        assert statuses[0] == ["inforce-A", "inforce-A", "lapsed-A"]
        assert statuses[1] == ["inforce-B", "lapsed-B", "lapsed-B"]

    def test_list_string_branch(self) -> None:
        """A List(String) branch selects element-wise."""
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2]],
                "term": [2],
                "labels": [["y0", "y1", "y2"]],
            },
        )
        af.picked = when(af.month < af.term).then(af.labels).otherwise("n/a")
        result = af.collect()

        assert result["picked"].to_list()[0] == ["y0", "y1", "n/a"]

    def test_list_eq_list_condition(self) -> None:
        """List == list conditions work on the string path too."""
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2]],
                "maturity_month": [[2, 2, 2]],
            },
        )
        af.flag = (
            when(af.month == af.maturity_month).then("matures").otherwise("continues")
        )
        result = af.collect()

        assert result["flag"].to_list()[0] == ["continues", "continues", "matures"]

    def test_chained_when_with_string_branches(self) -> None:
        """Chained when() folds string branches through the list path."""
        af = ActuarialFrame({"month": [[0, 1, 2, 3]], "term": [2]})
        af.phase = (
            when(af.month == 0)
            .then("issue")
            .when(af.month < af.term)
            .then("active")
            .otherwise("expired")
        )
        result = af.collect()

        assert result["phase"].to_list()[0] == [
            "issue",
            "active",
            "expired",
            "expired",
        ]

    def test_categorical_branch_outputs_strings(self) -> None:
        """Categorical branch values are accepted and emitted as strings."""
        af = ActuarialFrame(
            pl.DataFrame(
                {
                    "month": [[0, 1, 2]],
                    "term": [2],
                    "label": pl.Series(["preferred"], dtype=pl.Categorical),
                },
            ),
        )
        af.cls = when(af.month < af.term).then(af.label).otherwise("standard")
        result = af.collect()

        assert result["cls"].to_list()[0] == ["preferred", "preferred", "standard"]

    def test_null_branch_value_propagates_as_null(self) -> None:
        """A null in the selected branch yields a null element, not an error."""
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2], [0, 1, 2]],
                "term": [2, 2],
                "label": ["known", None],
            },
        )
        af.out = when(af.month < af.term).then(af.label).otherwise("fallback")
        result = af.collect()

        outs = result["out"].to_list()
        assert outs[0] == ["known", "known", "fallback"]
        assert outs[1] == [None, None, "fallback"]

    def test_mixed_string_numeric_branches_raise(self) -> None:
        """A string branch against a numeric branch has no output dtype."""
        af = ActuarialFrame({"month": [[0, 1, 2]], "term": [2]})
        af.bad = when(af.month < af.term).then("active").otherwise(0.0)
        with pytest.raises(pl.exceptions.ComputeError, match="mixed branch dtypes"):
            af.collect()

    def test_numeric_path_unchanged(self) -> None:
        """The f64 path behaves exactly as before alongside the new one."""
        af = ActuarialFrame({"month": [[0, 1, 2, 3]], "term": [2]})
        af.factor = when(af.month < af.term).then(1.0).otherwise(0.0)
        result = af.collect()

        assert result["factor"].dtype == pl.List(pl.Float64)
        assert result["factor"].to_list()[0] == [1.0, 1.0, 0.0, 0.0]


class TestBroadcastToPeriods:
    def test_string_scalar_broadcasts_to_month_axis(self) -> None:
        af = ActuarialFrame(
            {
                "occupation_class": ["M", "H"],
                "month": [[0, 1, 2], [0, 1]],
            },
        )
        af.occ = af.occupation_class.projection.broadcast_to_periods()
        result = af.collect()

        occ = result["occ"].to_list()
        assert occ[0] == ["M", "M", "M"]
        assert occ[1] == ["H", "H"]
        assert result["occ"].dtype == pl.List(pl.String)

    def test_like_matches_jagged_lengths(self) -> None:
        af = ActuarialFrame(
            {
                "frequency": ["monthly", "annual"],
                "premiums": [[100.0, 100.0], [1200.0, 1200.0, 1200.0]],
            },
        )
        af.freq = af.frequency.projection.broadcast_to_periods(like=af.premiums)
        result = af.collect()

        freq = result["freq"].to_list()
        assert freq[0] == ["monthly", "monthly"]
        assert freq[1] == ["annual", "annual", "annual"]

    def test_numeric_and_bool_dtypes(self) -> None:
        af = ActuarialFrame(
            {
                "loading": [1.05, 1.10],
                "is_smoker": [True, False],
                "month": [[0, 1], [0, 1]],
            },
        )
        af.loading_pp = af.loading.projection.broadcast_to_periods()
        af.smoker_pp = af.is_smoker.projection.broadcast_to_periods()
        result = af.collect()

        assert result["loading_pp"].to_list() == [[1.05, 1.05], [1.1, 1.1]]
        assert result["smoker_pp"].to_list() == [[True, True], [False, False]]

    def test_broadcast_feeds_string_lookup(self) -> None:
        """The end-to-end motivation: string dimension -> per-period lookup."""
        from gaspatchio.assumptions import Table

        rates = Table(
            name="occ_rates_gsp110",
            source=pl.DataFrame(
                {
                    "occ": ["M", "M", "H", "H"],
                    "year": [0, 1, 0, 1],
                    "rate": [0.01, 0.02, 0.03, 0.04],
                },
            ),
            dimensions={"occ": "occ", "year": "year"},
            value="rate",
        )
        af = ActuarialFrame(
            {
                "occupation_class": ["M", "H"],
                "year": [[0, 1], [0, 1]],
            },
        )
        af.occ_pp = af.occupation_class.projection.broadcast_to_periods(like=af.year)
        af.rate = rates.lookup(occ=af.occ_pp, year=af.year)
        result = af.collect()

        assert result["rate"].to_list()[0] == pytest.approx([0.01, 0.02])
        assert result["rate"].to_list()[1] == pytest.approx([0.03, 0.04])

    def test_missing_month_without_like_raises(self) -> None:
        af = ActuarialFrame({"label": ["a"], "values": [[1.0, 2.0]]})
        with pytest.raises(ValueError, match="month"):
            af.label.projection.broadcast_to_periods()

    def test_bad_like_type_raises(self) -> None:
        af = ActuarialFrame({"label": ["a"], "month": [[0, 1]]})
        with pytest.raises(TypeError, match="broadcast_to_periods"):
            af.label.projection.broadcast_to_periods(like=3)
