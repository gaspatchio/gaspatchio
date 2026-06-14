# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for polars_backend.masks — boolean-mask arithmetic."""

from __future__ import annotations

from gaspatchio_core import ActuarialFrame, when


class TestScalarPath:
    def test_and_scalar(self) -> None:
        af = ActuarialFrame({"x": [1, 2, 3, 4]})
        af.r = when((af.x > 1) & (af.x < 4)).then(1.0).otherwise(0.0)
        assert af.collect()["r"].to_list() == [0.0, 1.0, 1.0, 0.0]

    def test_or_scalar(self) -> None:
        af = ActuarialFrame({"x": [1, 2, 3, 4]})
        af.r = when((af.x == 1) | (af.x == 4)).then(1.0).otherwise(0.0)
        assert af.collect()["r"].to_list() == [1.0, 0.0, 0.0, 1.0]

    def test_invert_scalar(self) -> None:
        af = ActuarialFrame({"x": [1, 2, 3, 4]})
        af.r = when(~(af.x > 2)).then(1.0).otherwise(0.0)
        assert af.collect()["r"].to_list() == [1.0, 1.0, 0.0, 0.0]

    def test_or_then_invert_scalar(self) -> None:
        """Combining ``~`` over an ``|`` result should still produce Boolean."""
        af = ActuarialFrame({"x": [1, 2, 3, 4]})
        af.r = when(~((af.x == 1) | (af.x == 4))).then(1.0).otherwise(0.0)
        assert af.collect()["r"].to_list() == [0.0, 1.0, 1.0, 0.0]

    def test_or_with_boolean_column(self) -> None:
        """Scalar OR with a Boolean ColumnProxy operand."""
        af = ActuarialFrame({"x": [1, 2, 3, 4], "flag": [True, False, False, True]})
        af.r = when((af.x == 2) | af.flag).then(1.0).otherwise(0.0)
        assert af.collect()["r"].to_list() == [1.0, 1.0, 0.0, 1.0]


class TestListPath:
    def test_and_list(self) -> None:
        af = ActuarialFrame({"month": [[0, 1, 2, 3, 4]], "term": [3]})
        af.r = when((af.month > 0) & (af.month < 4)).then(1.0).otherwise(0.0)
        result = af.collect()["r"][0].to_list()
        assert result == [0.0, 1.0, 1.0, 1.0, 0.0]

    def test_or_list(self) -> None:
        af = ActuarialFrame({"month": [[0, 1, 2, 3, 4]]})
        af.r = when((af.month == 0) | (af.month == 4)).then(1.0).otherwise(0.0)
        result = af.collect()["r"][0].to_list()
        assert result == [1.0, 0.0, 0.0, 0.0, 1.0]

    def test_invert_list(self) -> None:
        af = ActuarialFrame({"month": [[0, 1, 2, 3, 4]]})
        af.r = when(~(af.month > 2)).then(1.0).otherwise(0.0)
        result = af.collect()["r"][0].to_list()
        assert result == [1.0, 1.0, 1.0, 0.0, 0.0]


class TestDirectModuleImports:
    """Verify the module's public surface is reachable."""

    def test_to_boolean_expr_importable(self) -> None:
        from gaspatchio_core.polars_backend.masks import to_boolean_expr  # noqa: F401

    def test_boolean_and_or_not_importable(self) -> None:
        from gaspatchio_core.polars_backend.masks import (  # noqa: F401
            boolean_and,
            boolean_not,
            boolean_or,
        )
