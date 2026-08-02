# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Scalar/list broadcast is order-independent for + and - (#53).

polars broadcasts a scalar into list arithmetic only when the scalar side
is a LEAF (bare column or literal) — a compound scalar expression fails
supertype derivation, and only for ``+``/``-`` (``*`` and ``/`` have
working kernels). The natural actuarial shape
``AnnPrem * ExpsPerPrem + (SA * ExpsPerSA + ExpsPol) * InflFactor``
therefore lived or died on operand order.

The proxy layer now compensates: when one operand of ``+``/``-`` is a
compound scalar expression and the other is list-shaped, the scalar side
is pre-broadcast with ``repeat_by`` to the list side's per-row lengths and
the operation proceeds as native list-list arithmetic. Shapes polars
already handles (bare columns, literals, ``*``, ``/``) keep their native
plans untouched.

These tests pin the contract: every operand order produces the same
numbers, on uniform and jagged frames alike.
"""

import datetime

import pytest

from gaspatchio_core import ActuarialFrame, when

pytest.importorskip("polars")

VALUATION = datetime.date(2025, 1, 1)


def _frame() -> ActuarialFrame:
    """Two policies on an annual axis with scalar and list columns."""
    af = ActuarialFrame(
        {
            "policy_id": [1, 2],
            "issue_age": [40, 40],
            "dur": [0, 1],
            "a": [100.0, 200.0],
            "b": [0.05, 0.10],
        }
    )
    af = af.projection.set(
        valuation_date=VALUATION,
        until="maximum_age",
        until_value=44,
        issue_age_column="issue_age",
        frequency="annual",
    )
    af.t = af.month // 12
    af.infl = (af.t * 0.0) + 1.01
    return af


def _collect_x(build):  # noqa: ANN202
    af = _frame()
    af.x = build(af)
    return af.collect()["x"].to_list()


class TestAdditionOrderIndependence:
    """compound_scalar + list works in every operand order."""

    def test_issue_repro_compound_scalar_left(self) -> None:
        """The exact #53 shape: compound scalar on the left of +."""
        result = _collect_x(lambda af: af.a * af.b + af.a * af.infl)
        assert result[0][0] == pytest.approx(100.0 * 0.05 + 100.0 * 1.01)

    def test_mirrored_order_matches(self) -> None:
        """Both orders produce identical numbers."""
        left = _collect_x(lambda af: af.a * af.b + af.a * af.infl)
        right = _collect_x(lambda af: af.a * af.infl + af.a * af.b)
        assert left == right

    def test_compound_scalar_plus_bare_list_column(self) -> None:
        """Compound scalar + a bare list column (field-test case q1)."""
        result = _collect_x(lambda af: af.a * af.b + af.infl)
        assert result[0][0] == pytest.approx(100.0 * 0.05 + 1.01)

    def test_bare_list_column_plus_compound_scalar(self) -> None:
        """Bare list column + compound scalar (the hidden fourth shape)."""
        result = _collect_x(lambda af: af.infl + af.a * af.b)
        assert result[0][0] == pytest.approx(1.01 + 100.0 * 0.05)

    def test_bare_scalar_column_still_works(self) -> None:
        """Native leaf broadcasting is untouched."""
        result = _collect_x(lambda af: af.b + af.infl)
        assert result[0][0] == pytest.approx(0.05 + 1.01)


class TestSubtractionOrderIndependence:
    """compound_scalar - list and list - compound_scalar both work."""

    def test_compound_scalar_minus_list(self) -> None:
        """Compound scalar on the left of - (field-test case q6)."""
        result = _collect_x(lambda af: af.a * af.b - af.a * af.infl)
        assert result[0][0] == pytest.approx(100.0 * 0.05 - 100.0 * 1.01)

    def test_list_minus_compound_scalar(self) -> None:
        """List on the left of - with a compound scalar right."""
        result = _collect_x(lambda af: af.infl - af.a * af.b)
        assert result[0][0] == pytest.approx(1.01 - 100.0 * 0.05)

    def test_subtraction_antisymmetry(self) -> None:
        """A - L == -(L - a), element-wise, exactly."""
        forward = _collect_x(lambda af: af.a * af.b - af.infl)
        backward = _collect_x(lambda af: af.infl - af.a * af.b)
        for f_row, b_row in zip(forward, backward, strict=True):
            for f, b in zip(f_row, b_row, strict=True):
                assert f == -b


class TestUnaffectedOperators:
    """* and / already have working kernels — plans stay native."""

    def test_compound_scalar_times_list(self) -> None:
        """Multiplication was never order-dependent."""
        result = _collect_x(lambda af: (af.a * af.b) * af.infl)
        assert result[0][0] == pytest.approx(100.0 * 0.05 * 1.01)

    def test_compound_scalar_divided_by_list(self) -> None:
        """Division was never order-dependent."""
        result = _collect_x(lambda af: (af.a * af.b) / af.infl)
        assert result[0][0] == pytest.approx(100.0 * 0.05 / 1.01)


class TestActuarialShape:
    """The natural expense formula runs as written in the spec."""

    def test_fixed_plus_inflating_expense(self) -> None:
        """AnnPrem*ExpsPerPrem + (SA*ExpsPerSA + ExpsPol)*InflFactor."""
        af = _frame()
        af.expense = af.a * af.b + (af.a * 0.001 + 10.0) * af.infl
        result = af.collect()["expense"].to_list()
        expected = 100.0 * 0.05 + (100.0 * 0.001 + 10.0) * 1.01
        assert result[0][0] == pytest.approx(expected)

    def test_inside_when_branch(self) -> None:
        """The #53 shape inside a when() branch (the #54 companion repro)."""
        af = _frame()
        af.x = when(af.dur == 0).then(af.a * af.b + af.a * af.infl).otherwise(0.0)
        result = af.collect()["x"].to_list()
        assert result[0][0] == pytest.approx(100.0 * 0.05 + 100.0 * 1.01)
        assert result[1][0] == 0.0


class TestJaggedFrames:
    """repeat_by matches each row's own list length."""

    def test_jagged_lists_broadcast_per_row(self) -> None:
        """Per-policy horizons get per-row broadcast lengths."""
        af = ActuarialFrame(
            {
                "policy_id": [1, 2],
                "a": [100.0, 200.0],
                "b": [0.05, 0.10],
                "cf": [[1.0, 2.0, 3.0], [4.0, 5.0]],
            }
        )
        af.x = af.a * af.b + af.cf
        result = af.collect()["x"].to_list()
        assert result[0] == pytest.approx([6.0, 7.0, 8.0])
        assert result[1] == pytest.approx([24.0, 25.0])
